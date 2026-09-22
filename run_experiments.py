import os
import sys
import copy
import json
import numpy as np
import torch

from src.dataset import generate_iot_ids_dataset, partition_dirichlet
from src.federated import FederatedServer, train_client_local
from src.metrics import evaluate_model, evaluate_clustered_fl, compute_clustering_quality, calculate_communication_bytes

def run_fl_simulation(method='Cluster + Trust', cluster_mode='centroid', alpha=0.1, 
                       attacker_ratio=0.0, attack_type='sign_flip', num_clients=10, 
                       num_rounds=20, num_clusters=3, seed=42):
    
    np.random.seed(seed)
    torch.manual_seed(seed)
    
    X, y = generate_iot_ids_dataset(num_samples=10000, num_features=20, num_classes=5, seed=seed)
    n_train = int(len(X) * 0.8)
    X_train, y_train = X[:n_train], y[:n_train]
    X_test, y_test = X[n_train:], y[n_train:]
    
    client_train_data = partition_dirichlet(X_train, y_train, num_clients=num_clients, alpha=alpha, seed=seed)
    client_test_data = partition_dirichlet(X_test, y_test, num_clients=num_clients, alpha=alpha, seed=seed)
    
    true_client_labels = [np.bincount(y_k).argmax() if len(y_k) > 0 else 0 for _, y_k in client_train_data]
    
    num_attackers = int(num_clients * attacker_ratio)
    malicious_flags = [False] * num_clients
    if num_attackers > 0:
        mal_indices = np.random.choice(num_clients, num_attackers, replace=False)
        for idx in mal_indices:
            malicious_flags[idx] = True
            
    server = FederatedServer(input_dim=20, latent_dim=16, num_classes=5, num_clusters=num_clusters, 
                             num_clients=num_clients, method=method, cluster_mode=cluster_mode)
    
    client_models = [copy.deepcopy(server.global_model) for _ in range(num_clients)]
    
    accuracy_history = []
    trust_score_history = []
    
    for r in range(num_rounds):
        signatures = []
        for k in range(num_clients):
            X_k, y_k = client_train_data[k]
            with torch.no_grad():
                sample_x = torch.tensor(X_k[:min(100, len(X_k))], dtype=torch.float32)
                z, _, q = client_models[k](sample_x)
                if cluster_mode == 'centroid':
                    sig = z.mean(dim=0).numpy()
                else:
                    sig = torch.cat([p.flatten() for p in client_models[k].clustering_head.parameters()]).numpy()
            signatures.append(sig)
            
        signatures = np.array(signatures)
        server.perform_clustering(signatures)
        
        client_updates = []
        client_sizes = []
        
        for k in range(num_clients):
            X_k, y_k = client_train_data[k]
            client_sizes.append(len(X_k))
            
            if method in ['FedAvg', 'Trust Only']:
                target_model = copy.deepcopy(server.global_model)
            else:
                c = server.client_clusters[k]
                target_model = copy.deepcopy(server.cluster_models[c])
                
            updated_state, delta, centroid, _ = train_client_local(
                target_model, X_k, y_k, epochs=3, lr=0.01, lambda_clust=0.01, mu_prox=0.05,
                is_malicious=malicious_flags[k], attack_type=attack_type
            )
            
            client_models[k].load_state_dict(updated_state)
            client_updates.append(updated_state)
            
        server.aggregate_updates(client_updates, client_sizes, malicious_flags)
        
        if method in ['FedAvg', 'Trust Only']:
            metrics = evaluate_model(server.global_model, X_test, y_test)
        else:
            metrics = evaluate_clustered_fl(server.cluster_models, server.client_clusters, client_test_data)
            
        accuracy_history.append(metrics['accuracy'])
        trust_score_history.append(server.trust_scores.tolist())
        
    if method in ['FedAvg', 'Trust Only']:
        final_metrics = evaluate_model(server.global_model, X_test, y_test)
    else:
        final_metrics = evaluate_clustered_fl(server.cluster_models, server.client_clusters, client_test_data)
        
    clustering_quality = compute_clustering_quality(true_client_labels, server.client_clusters)
    
    return {
        'final_metrics': final_metrics,
        'accuracy_history': accuracy_history,
        'trust_score_history': trust_score_history,
        'clustering_quality': clustering_quality,
        'final_trust_scores': server.trust_scores.tolist(),
        'malicious_flags': malicious_flags
    }


def main():
    os.makedirs('results', exist_ok=True)
    seeds = [42, 100, 2026]
    methods = ['FedAvg', 'Cluster Only', 'Trust Only', 'Cluster + Trust (Centroid)', 'Cluster + Trust (Learnable Head)']
    alphas = [0.01, 0.05, 0.1, 0.5, 1.0]
    attacker_ratios = [0.0, 0.1, 0.2, 0.3, 0.5]
    
    all_results = {
        'non_iid_sweep': {},
        'byzantine_sweep': {},
        'metric_comparison_7d': {},
        'clustering_validation': {},
        'communication_cost': calculate_communication_bytes(num_clients=10, num_clusters=3, model_params=12500, num_rounds=20)
    }
    
    json_path = 'results/experimental_results.json'
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                existing = json.load(f)
                for k in ['non_iid_sweep', 'byzantine_sweep', 'metric_comparison_7d', 'clustering_validation']:
                    if k in existing:
                        all_results[k] = existing[k]
            print(f"Loaded existing results from {json_path}", flush=True)
        except Exception as e:
            print(f"Error loading {json_path}: {e}", flush=True)
    
    print("=== EXPERIMENT 1: Non-IID Dirichlet Sweep (alphas: 0.01 to 1.0) ===", flush=True)
    for alpha in alphas:
        str_alpha = str(alpha)
        if str_alpha not in all_results['non_iid_sweep']:
            all_results['non_iid_sweep'][str_alpha] = {}
        for m in methods:
            if m in all_results['non_iid_sweep'][str_alpha]:
                print(f"[SKIP] Alpha {alpha:<4} | {m:<32} already computed", flush=True)
                continue
            accs, f1s, recalls = [], [], []
            for s in seeds:
                mode = 'learnable_head' if 'Learnable' in m else 'centroid'
                base_m = m.replace(' (Centroid)', '').replace(' (Learnable Head)', '')
                res = run_fl_simulation(method=base_m, cluster_mode=mode, alpha=alpha, seed=s)
                accs.append(res['final_metrics']['accuracy'])
                f1s.append(res['final_metrics']['macro_f1'])
                recalls.append(res['final_metrics']['attack_recall'])
                
            all_results['non_iid_sweep'][str_alpha][m] = {
                'accuracy_mean': float(np.mean(accs)),
                'accuracy_std': float(np.std(accs)),
                'macro_f1_mean': float(np.mean(f1s)),
                'attack_recall_mean': float(np.mean(recalls))
            }
            print(f"Alpha {alpha:<4} | {m:<32} -> Acc: {np.mean(accs)*100:5.2f}% (+/- {np.std(accs)*100:4.2f}%) | Macro-F1: {np.mean(f1s):.4f}", flush=True)
            with open(json_path, 'w') as f:
                json.dump(all_results, f, indent=2)
            
    print("\n=== EXPERIMENT 2: Byzantine Resilience Sweep (Attacker %: 0% to 50%) ===", flush=True)
    for ratio in attacker_ratios:
        str_ratio = str(ratio)
        if str_ratio not in all_results['byzantine_sweep']:
            all_results['byzantine_sweep'][str_ratio] = {}
        for m in ['FedAvg', 'Trust Only', 'Cluster + Trust (Centroid)', 'Cluster + Trust (Learnable Head)']:
            if m in all_results['byzantine_sweep'][str_ratio]:
                print(f"[SKIP] Attacker {ratio*100:2.0f}% | {m:<32} already computed", flush=True)
                continue
            accs, recalls = [], []
            for s in seeds:
                mode = 'learnable_head' if 'Learnable' in m else 'centroid'
                base_m = m.replace(' (Centroid)', '').replace(' (Learnable Head)', '')
                res = run_fl_simulation(method=base_m, cluster_mode=mode, alpha=0.05, attacker_ratio=ratio, attack_type='sign_flip', seed=s)
                accs.append(res['final_metrics']['accuracy'])
                recalls.append(res['final_metrics']['attack_recall'])
                
            all_results['byzantine_sweep'][str_ratio][m] = {
                'accuracy_mean': float(np.mean(accs)),
                'accuracy_std': float(np.std(accs)),
                'attack_recall_mean': float(np.mean(recalls))
            }
            print(f"Attacker {ratio*100:2.0f}% | {m:<32} -> Acc: {np.mean(accs)*100:5.2f}% | Attack Recall: {np.mean(recalls)*100:5.2f}%", flush=True)
            with open(json_path, 'w') as f:
                json.dump(all_results, f, indent=2)
            
    print("\n=== EXPERIMENT 3: 7-Metric Dimension Benchmarking ===", flush=True)
    for m in methods:
        if m in all_results['metric_comparison_7d']:
            print(f"[SKIP] 7D Summary | {m:<32} already computed", flush=True)
            continue
        acc_list, f1_list, recall_list, conv_rounds = [], [], [], []
        mode = 'learnable_head' if 'Learnable' in m else 'centroid'
        base_m = m.replace(' (Centroid)', '').replace(' (Learnable Head)', '')
        
        histories = []
        for s in seeds:
            res = run_fl_simulation(method=base_m, cluster_mode=mode, alpha=0.05, attacker_ratio=0.2, attack_type='sign_flip', seed=s)
            acc_list.append(res['final_metrics']['accuracy'])
            f1_list.append(res['final_metrics']['macro_f1'])
            recall_list.append(res['final_metrics']['attack_recall'])
            histories.append(res['accuracy_history'])
            
            hist = res['accuracy_history']
            rounds_to_target = next((idx+1 for idx, acc in enumerate(hist) if acc >= 0.70), len(hist))
            conv_rounds.append(rounds_to_target)
            
        all_results['metric_comparison_7d'][m] = {
            'Accuracy': float(np.mean(acc_list)),
            'Macro-F1': float(np.mean(f1_list)),
            'Attack-Class Recall': float(np.mean(recall_list)),
            'Variance (Std Dev)': float(np.std(acc_list)),
            'Convergence Rounds (Target 70%)': float(np.mean(conv_rounds)),
            'Accuracy History (Mean)': np.mean(histories, axis=0).tolist()
        }
        print(f"7D Summary | {m:<32} -> Acc: {np.mean(acc_list)*100:5.2f}% | Std Dev: {np.std(acc_list)*100:4.2f}% | Recall: {np.mean(recall_list):.4f}", flush=True)
        with open(json_path, 'w') as f:
            json.dump(all_results, f, indent=2)
        
    print("ALL EXPERIMENTS COMPLETED SUCCESSFULLY!", flush=True)


if __name__ == '__main__':
    main()
