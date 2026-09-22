import numpy as np
import torch
from sklearn.metrics import f1_score, recall_score, accuracy_score, adjusted_rand_score, normalized_mutual_info_score

def evaluate_model(model, X_test, y_test, num_classes=5):
    """
    Evaluates a single model (Global Model for FedAvg / Trust Only) on test data.
    """
    model.eval()
    with torch.no_grad():
        X_tensor = torch.tensor(X_test, dtype=torch.float32)
        _, logits, _ = model(X_tensor)
        preds = torch.argmax(logits, dim=1).numpy()
        
    acc = accuracy_score(y_test, preds)
    macro_f1 = f1_score(y_test, preds, average='macro', zero_division=0)
    
    recalls = recall_score(y_test, preds, average=None, labels=list(range(num_classes)), zero_division=0)
    attack_mask = (y_test > 0)
    if attack_mask.sum() > 0:
        attack_recall = recall_score(y_test[attack_mask], preds[attack_mask], average='macro', zero_division=0)
    else:
        attack_recall = 0.0
        
    return {
        'accuracy': float(acc),
        'macro_f1': float(macro_f1),
        'attack_recall': float(attack_recall),
        'per_class_recall': recalls.tolist()
    }

def evaluate_clustered_fl(cluster_models, client_clusters, client_test_data, num_classes=5):
    """
    Evaluates Clustered FL by assigning test samples to cluster models matching client assignments.
    """
    all_preds = []
    all_targets = []
    
    for k, (X_k_test, y_k_test) in enumerate(client_test_data):
        if len(X_k_test) == 0:
            continue
        c = client_clusters[k]
        model = cluster_models[c]
        model.eval()
        with torch.no_grad():
            X_tensor = torch.tensor(X_k_test, dtype=torch.float32)
            _, logits, _ = model(X_tensor)
            preds = torch.argmax(logits, dim=1).numpy()
            
        all_preds.extend(preds)
        all_targets.extend(y_k_test)
        
    all_preds = np.array(all_preds)
    all_targets = np.array(all_targets)
    
    acc = accuracy_score(all_targets, all_preds)
    macro_f1 = f1_score(all_targets, all_preds, average='macro', zero_division=0)
    
    recalls = recall_score(all_targets, all_preds, average=None, labels=list(range(num_classes)), zero_division=0)
    attack_mask = (all_targets > 0)
    if attack_mask.sum() > 0:
        attack_recall = recall_score(all_targets[attack_mask], all_preds[attack_mask], average='macro', zero_division=0)
    else:
        attack_recall = 0.0
        
    return {
        'accuracy': float(acc),
        'macro_f1': float(macro_f1),
        'attack_recall': float(attack_recall),
        'per_class_recall': recalls.tolist()
    }

def compute_clustering_quality(true_labels, pred_clusters):
    ari = adjusted_rand_score(true_labels, pred_clusters)
    nmi = normalized_mutual_info_score(true_labels, pred_clusters)
    return {
        'ARI': float(ari),
        'NMI': float(nmi)
    }

def calculate_communication_bytes(num_clients=10, num_clusters=3, model_params=12500, signature_dim=16, num_rounds=15, bytes_per_float=4):
    model_size_bytes = model_params * bytes_per_float
    signature_size_bytes = signature_dim * bytes_per_float
    
    fedavg_per_round = num_clients * 2 * model_size_bytes
    ifca_per_round = num_clients * (num_clusters + 1) * model_size_bytes
    proposed_per_round = num_clients * (2 * model_size_bytes + signature_size_bytes)
    
    return {
        'FedAvg': {
            'per_round_kb': fedavg_per_round / 1024.0,
            'total_mb': (fedavg_per_round * num_rounds) / (1024.0 * 1024.0)
        },
        'IFCA': {
            'per_round_kb': ifca_per_round / 1024.0,
            'total_mb': (ifca_per_round * num_rounds) / (1024.0 * 1024.0)
        },
        'Proposed': {
            'per_round_kb': proposed_per_round / 1024.0,
            'total_mb': (proposed_per_round * num_rounds) / (1024.0 * 1024.0)
        }
    }
