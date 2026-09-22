import copy
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader
from sklearn.cluster import AgglomerativeClustering
from scipy.optimize import linear_sum_assignment

from src.models import ClusteredIDSModel, target_distribution
from src.attacks import apply_label_flipping, apply_sign_flipping, apply_gradient_poisoning

class FederatedServer:
    def __init__(self, input_dim=20, latent_dim=16, num_classes=5, num_clusters=3, num_clients=10, 
                 beta=0.85, sigma=0.6, gamma=0.3, method='Cluster + Trust', cluster_mode='centroid'):
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.num_classes = num_classes
        self.num_clusters = num_clusters
        self.num_clients = num_clients
        self.beta = beta
        self.sigma = sigma
        self.gamma = gamma
        self.method = method
        self.cluster_mode = cluster_mode
        
        self.global_model = ClusteredIDSModel(input_dim, latent_dim, num_classes, num_clusters)
        self.cluster_models = [copy.deepcopy(self.global_model) for _ in range(num_clusters)]
        
        self.trust_scores = np.ones(num_clients, dtype=np.float32)
        self.client_clusters = np.zeros(num_clients, dtype=np.int32)
        self.context_signatures = None
        self.previous_centroids = None
        
    def perform_clustering(self, client_signatures):
        if self.num_clusters <= 1 or self.method in ['FedAvg', 'Trust Only']:
            self.client_clusters = np.zeros(self.num_clients, dtype=np.int32)
            return self.client_clusters
            
        if self.context_signatures is None:
            self.context_signatures = client_signatures.copy()
        else:
            self.context_signatures = (1.0 - self.gamma) * self.context_signatures + self.gamma * client_signatures
            
        norms = np.linalg.norm(self.context_signatures, axis=1, keepdims=True) + 1e-8
        norm_sigs = self.context_signatures / norms
        
        clustering = AgglomerativeClustering(n_clusters=self.num_clusters)
        raw_clusters = clustering.fit_predict(norm_sigs)
        
        # Calculate new cluster centroids
        sig_dim = norm_sigs.shape[1]
        new_centroids = np.zeros((self.num_clusters, sig_dim))
        for c in range(self.num_clusters):
            members = np.where(raw_clusters == c)[0]
            if len(members) > 0:
                new_centroids[c] = norm_sigs[members].mean(axis=0)
                
        if self.previous_centroids is not None:
            # Align new clusters to previous centroids using Hungarian Algorithm
            cost_matrix = -np.dot(new_centroids, self.previous_centroids.T)
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            remap = {r: c for r, c in zip(row_ind, col_ind)}
            aligned_clusters = np.array([remap.get(c, c) for c in raw_clusters])
            
            aligned_centroids = np.zeros_like(new_centroids)
            for new_c, old_c in remap.items():
                aligned_centroids[old_c] = new_centroids[new_c]
            self.previous_centroids = aligned_centroids
            self.client_clusters = aligned_clusters
        else:
            self.previous_centroids = new_centroids
            self.client_clusters = raw_clusters
            
        return self.client_clusters

    def aggregate_updates(self, client_updates, client_sizes, malicious_flags):
        total_samples = sum(client_sizes)
        client_weights = [n / total_samples for n in client_sizes]
        
        if self.method in ['FedAvg', 'Trust Only']:
            clusters = {0: list(range(self.num_clients))}
        else:
            clusters = {}
            for k in range(self.num_clients):
                c = self.client_clusters[k]
                if c not in clusters:
                    clusters[c] = []
                clusters[c].append(k)
                
        # Trust score momentum decay calculation
        for c, members in clusters.items():
            if not members:
                continue
            ref_model = self.global_model if self.method in ['FedAvg', 'Trust Only'] else self.cluster_models[c]
            
            mean_update = {}
            for name, param in ref_model.named_parameters():
                mean_update[name] = torch.zeros_like(param.data)
                for k in members:
                    mean_update[name] += client_updates[k][name] / len(members)
                    
            for k in members:
                dev_sum = 0.0
                norm_sum = 0.0
                for name in mean_update:
                    dev_sum += torch.sum((client_updates[k][name] - mean_update[name]) ** 2).item()
                    norm_sum += torch.sum(mean_update[name] ** 2).item()
                
                delta_k = np.sqrt(dev_sum) / (np.sqrt(norm_sum) + 1e-6)
                tau_k = np.exp(-delta_k / self.sigma)
                
                if 'Trust' in self.method:
                    self.trust_scores[k] = self.beta * self.trust_scores[k] + (1.0 - self.beta) * tau_k
                else:
                    self.trust_scores[k] = 1.0

        # Global Encoder Representation Aggregation across all clients
        total_trust_weight = sum(client_weights[k] * self.trust_scores[k] for k in range(self.num_clients))
        if total_trust_weight < 1e-8:
            total_trust_weight = 1e-8
            
        global_encoder_params = {}
        for name, param in self.global_model.encoder.named_parameters():
            global_encoder_params[name] = torch.zeros_like(param.data)
            for k in range(self.num_clients):
                w_k = (client_weights[k] * self.trust_scores[k]) / total_trust_weight
                global_encoder_params[name] += client_updates[k]['encoder.' + name] * w_k
                
        self.global_model.encoder.load_state_dict(global_encoder_params)

        # Classifier Head Aggregation (Global for FedAvg/Trust Only, Cluster-wise for Clustered FL)
        if self.method in ['FedAvg', 'Trust Only']:
            global_clf_params = {}
            for name, param in self.global_model.classifier.named_parameters():
                global_clf_params[name] = torch.zeros_like(param.data)
                for k in range(self.num_clients):
                    w_k = (client_weights[k] * self.trust_scores[k]) / total_trust_weight
                    global_clf_params[name] += client_updates[k]['classifier.' + name] * w_k
            self.global_model.classifier.load_state_dict(global_clf_params)
        else:
            global_clf_params = {}
            for name, param in self.global_model.classifier.named_parameters():
                global_clf_params[name] = torch.zeros_like(param.data)
                for k in range(self.num_clients):
                    w_k = (client_weights[k] * self.trust_scores[k]) / total_trust_weight
                    global_clf_params[name] += client_updates[k]['classifier.' + name] * w_k
            self.global_model.classifier.load_state_dict(global_clf_params)
            
            for c, members in clusters.items():
                if not members:
                    continue
                c_trust_weight = sum(client_weights[k] * self.trust_scores[k] for k in members)
                if c_trust_weight < 1e-8:
                    c_trust_weight = 1e-8
                    
                clf_params = {}
                for name, param in self.cluster_models[c].classifier.named_parameters():
                    clf_params[name] = torch.zeros_like(param.data)
                    for k in members:
                        w_k = (client_weights[k] * self.trust_scores[k]) / c_trust_weight
                        clf_params[name] += client_updates[k]['classifier.' + name] * w_k
                        
                # Blend cluster classifier with global classifier (80% cluster, 20% global)
                for name in clf_params:
                    clf_params[name] = 0.80 * clf_params[name] + 0.20 * global_clf_params[name]
                    
                self.cluster_models[c].classifier.load_state_dict(clf_params)
                self.cluster_models[c].encoder.load_state_dict(global_encoder_params)



def train_client_local(model, X_k, y_k, epochs=3, lr=0.01, lambda_clust=0.01, mu_prox=0.05, is_malicious=False, attack_type='label_flip'):
    model_initial = copy.deepcopy(model.state_dict())
    
    X_tensor = torch.tensor(X_k, dtype=torch.float32)
    y_tensor = torch.tensor(y_k, dtype=torch.int64)
    
    if is_malicious and attack_type == 'label_flip':
        y_tensor = apply_label_flipping(y_tensor)
        
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    
    # Identify unique classes present in client dataset
    present_classes = torch.unique(y_tensor)
    
    dataset = TensorDataset(X_tensor, y_tensor)
    batch_size = min(64, max(16, len(X_k)))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    model.train()
    for ep in range(epochs):
        for bx, by in loader:
            optimizer.zero_grad()
            z, logits, q = model(bx)
            
            # Mask logits of absent classes so local SGD doesn't degrade them
            if len(present_classes) < 5:
                mask = torch.full_like(logits, -1e9)
                mask[:, present_classes] = logits[:, present_classes]
                loss_clf = F.cross_entropy(mask, by)
            else:
                loss_clf = F.cross_entropy(logits, by)
            
            if len(bx) > 1:
                p = target_distribution(q.detach())
                loss_clust = torch.mean(torch.sum(p * torch.log(p / (q + 1e-8) + 1e-8), dim=1))
            else:
                loss_clust = 0.0
                
            # FedProx proximal penalty to limit client drift
            prox_penalty = 0.0
            for name, param in model.named_parameters():
                prox_penalty += torch.sum((param - model_initial[name]) ** 2)
                
            loss = loss_clf + lambda_clust * loss_clust + 0.5 * mu_prox * prox_penalty
            loss.backward()
            optimizer.step()
        
    model.eval()
    with torch.no_grad():
        z_final, _, _ = model(X_tensor)
        centroid = z_final.mean(dim=0).cpu().numpy()
        
    updated_state = model.state_dict()
    model_delta = {name: updated_state[name] - model_initial[name] for name in updated_state}
    
    if is_malicious:
        if attack_type == 'sign_flip':
            model_delta = apply_sign_flipping(model_delta)
            for name in updated_state:
                updated_state[name] = model_initial[name] + model_delta[name]
        elif attack_type == 'gradient_poisoning':
            model_delta = apply_gradient_poisoning(model_delta)
            for name in updated_state:
                updated_state[name] = model_initial[name] + model_delta[name]
            
    clustering_head_sig = torch.cat([p.flatten() for p in model.clustering_head.parameters()]).detach().numpy()
    
    return updated_state, model_delta, centroid, clustering_head_sig



