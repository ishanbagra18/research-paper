import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader

def generate_iot_ids_dataset(num_samples=10000, num_features=20, num_classes=5, seed=42):
    """
    Generates a realistic synthetic IoT Intrusion Detection dataset with distinct feature distributions
    representing modern IoT network traffic (TON-IoT / Edge-IIoTset style).
    
    Classes:
    0: Benign (Normal traffic)
    1: DoS / DDoS Attack
    2: Botnet C&C
    3: Reconnaissance / Port Scan
    4: Web Attack / SQL Injection
    """
    np.random.seed(seed)
    
    # Class priors: 50% Benign, 15% DoS, 15% Botnet, 10% Recon, 10% SQLi
    class_priors = [0.50, 0.15, 0.15, 0.10, 0.10]
    counts = (np.array(class_priors) * num_samples).astype(int)
    counts[-1] = num_samples - counts[:-1].sum()
    
    X_list = []
    y_list = []
    
    # Feature means & covariances per class to simulate realistic network flows
    for c in range(num_classes):
        n_c = counts[c]
        if c == 0:  # Benign
            mean = np.zeros(num_features)
            cov = np.eye(num_features) * 0.5
        elif c == 1:  # DoS: High packet rate & byte count (features 0-4 skewed high)
            mean = np.array([3.0, 3.5, 3.2, 2.0] + [0.1]*(num_features-4))
            cov = np.eye(num_features) * 0.6
        elif c == 2:  # Botnet: High TCP flag anomaly & burstiness (features 4-8 skewed high)
            mean = np.array([0.1]*4 + [3.2, 3.8, 3.0, 2.2] + [0.1]*(num_features-8))
            cov = np.eye(num_features) * 0.6
        elif c == 3:  # Reconnaissance: Rapid connection attempts (features 8-12 skewed high)
            mean = np.array([0.1]*8 + [2.8, 3.4, 3.6, 2.5] + [0.1]*(num_features-12))
            cov = np.eye(num_features) * 0.5
        else:  # SQL Injection: HTTP payload & length anomaly (features 12-16 skewed high)
            mean = np.array([0.1]*12 + [4.0, 3.2, 3.5, 2.8] + [0.1]*(num_features-16))
            cov = np.eye(num_features) * 0.6
            
        X_c = np.random.multivariate_normal(mean, cov, n_c)
        y_c = np.full(n_c, c)
        
        X_list.append(X_c)
        y_list.append(y_c)
        
    X = np.vstack(X_list)
    y = np.concatenate(y_list)
    
    # Shuffle dataset
    perm = np.random.permutation(num_samples)
    X, y = X[perm], y[perm]
    
    # Min-Max Normalization to [0, 1] as described in Section 4.1 of the paper
    X_min = X.min(axis=0, keepdims=True)
    X_max = X.max(axis=0, keepdims=True)
    X = (X - X_min) / (X_max - X_min + 1e-8)
    
    return X.astype(np.float32), y.astype(np.int64)


def partition_dirichlet(X, y, num_clients=10, alpha=0.1, seed=42):
    """
    Partitions dataset across clients using a Dirichlet distribution Dir(alpha).
    Smaller alpha -> higher non-IID statistical heterogeneity.
    """
    np.random.seed(seed)
    num_classes = len(np.unique(y))
    client_indices = [[] for _ in range(num_clients)]
    
    for c in range(num_classes):
        idx_c = np.where(y == c)[0]
        np.random.shuffle(idx_c)
        
        # Sample Dirichlet proportions
        proportions = np.random.dirichlet(np.repeat(alpha, num_clients))
        proportions = proportions / proportions.sum()
        
        # Split indices
        splits = (np.cumsum(proportions) * len(idx_c)).astype(int)[:-1]
        client_splits = np.split(idx_c, splits)
        
        for k in range(num_clients):
            client_indices[k].extend(client_splits[k].tolist())
            
    client_data = []
    for k in range(num_clients):
        if len(client_indices[k]) == 0:
            client_indices[k] = [np.random.choice(len(X))]
        idx = np.array(client_indices[k], dtype=np.int64)
        np.random.shuffle(idx)
        client_data.append((X[idx], y[idx]))
        
    return client_data

