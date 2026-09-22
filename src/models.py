import torch
import torch.nn as nn
import torch.nn.functional as F

class LatentEncoder(nn.Module):
    """
    Lightweight feature encoder G(x) mapping raw IoT traffic features into low-dimensional latent space R^e.
    """
    def __init__(self, input_dim=20, latent_dim=16):
        super(LatentEncoder, self).__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.ln1 = nn.LayerNorm(64)
        self.fc2 = nn.Linear(64, 32)
        self.ln2 = nn.LayerNorm(32)
        self.fc3 = nn.Linear(32, latent_dim)
        
    def forward(self, x):
        h = F.relu(self.ln1(self.fc1(x)))
        h = F.relu(self.ln2(self.fc2(h)))
        z = self.fc3(h)
        return z

class IntrusionClassifier(nn.Module):
    """
    Classifier mapping latent representation z to attack logits.
    """
    def __init__(self, latent_dim=16, num_classes=5):
        super(IntrusionClassifier, self).__init__()
        self.fc1 = nn.Linear(latent_dim, 32)
        self.fc2 = nn.Linear(32, num_classes)
        
    def forward(self, z):
        h = F.relu(self.fc1(z))
        logits = self.fc2(h)
        return logits

class LearnableClusteringHead(nn.Module):
    """
    Deep clustering head H(z; \theta_H) mapping latent vectors to soft assignment probabilities q
    using Student-t kernel (DEC formulation).
    """
    def __init__(self, latent_dim=16, num_clusters=3, alpha=1.0):
        super(LearnableClusteringHead, self).__init__()
        self.num_clusters = num_clusters
        self.alpha = alpha
        # Cluster centroids parameters mu
        self.cluster_centers = nn.Parameter(torch.Tensor(num_clusters, latent_dim))
        nn.init.xavier_uniform_(self.cluster_centers)
        
    def forward(self, z):
        # Compute Student-t kernel distance between latent z and cluster centers mu
        # z: [batch, latent_dim], mu: [num_clusters, latent_dim]
        dist = torch.sum((z.unsqueeze(1) - self.cluster_centers.unsqueeze(0)) ** 2, dim=2)
        q = 1.0 / (1.0 + dist / self.alpha)
        q = q ** ((self.alpha + 1.0) / 2.0)
        q = (q.t() / torch.sum(q, dim=1)).t()
        return q

def target_distribution(q):
    """
    Computes target distribution P for soft clustering loss refinement:
    p_ik = (q_ik^2 / f_k) / sum_{k'} (q_ik'^2 / f_{k'})
    """
    weight = q ** 2 / q.sum(0)
    return (weight.t() / weight.sum(1)).t()

class ClusteredIDSModel(nn.Module):
    """
    Unified local model combining Encoder, Classifier, and optional Learnable Clustering Head.
    """
    def __init__(self, input_dim=20, latent_dim=16, num_classes=5, num_clusters=3):
        super(ClusteredIDSModel, self).__init__()
        self.encoder = LatentEncoder(input_dim, latent_dim)
        self.classifier = IntrusionClassifier(latent_dim, num_classes)
        self.clustering_head = LearnableClusteringHead(latent_dim, num_clusters)
        
    def forward(self, x):
        z = self.encoder(x)
        logits = self.classifier(z)
        q = self.clustering_head(z)
        return z, logits, q
