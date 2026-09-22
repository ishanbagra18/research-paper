# Adaptive Context-Aware Clustering with Learned Representations for Handling Non-IID Data in Federated IDS

**Authors:** Gurnish Singh Sangha, Ishan Bagra, Jai Taneja  
**Affiliation:** Indian Institute of Information Technology, Kota  
**Mentorship:** Dr. Isha Pathak  

---

## 📌 Abstract
This repository contains the official PyTorch implementation and empirical benchmark suite for **Adaptive Context-Aware Clustered Federated Learning (FL)** designed for non-IID IoT intrusion detection systems (IDS). The proposed framework combines compact latent signatures, dual-mode clustering (server-side centroid & learnable deep clustering head), and time-varying momentum trust scoring to defend against non-IID client drift and Byzantine attacks (0%–50% malicious nodes).

---

## 🚀 Key Results & Highlights

- **Severe Non-IID Skew ($\alpha = 0.01$)**: `Cluster + Trust (Centroid)` achieves **65.88% Accuracy**, outperforming FedAvg (61.15%), Trust Only (58.43%), and Cluster Only (56.14%).
- **Byzantine Robustness (10% Attackers)**: `Cluster + Trust (Learnable Head)` achieves **93.99% Accuracy** and **70.88% Attack Recall** vs FedAvg (90.37% Acc, 64.35% Recall).
- **Extreme Threat Mitigation (50% Attackers)**: While standard FedAvg collapses to **43.73% Accuracy** (20.75% Recall), `Cluster + Trust (Centroid)` retains **56.01% Accuracy** (39.22% Recall).
- **Communication Efficiency**: Latent signature exchange adds only **+0.62 KB per round** (+0.06% overhead over FedAvg), saving **99.8% bandwidth** compared to IFCA.

---

## 📁 Repository Structure

```
.
├── Project_I_Revised.md      # Full Research Paper Source (Markdown)
├── Project_I_New_Final.pdf   # Formatted Paper Manuscript PDF
├── run_experiments.py        # Multi-seed Benchmark Simulation Suite (Exp 1, 2, & 3)
├── generate_artifacts.py     # Publication Figure Generator
├── requirements.txt          # Dependencies
├── src/                      # Source Code Modules
│   ├── dataset.py            # Synthetic IoT IDS Data Generator & Dirichlet Non-IID Sampler
│   ├── models.py             # Latent Encoder, Classifier & Soft Clustering Head PyTorch Models
│   ├── attacks.py            # Byzantine Threat Generators (Label-Flip, Sign-Flip, Noise Injection)
│   ├── federated.py          # Server Aggregation, Exponential Smoothing & Hungarian Alignment
│   └── metrics.py            # 7-Dimensional Evaluation Metrics Calculator
└── results/                  # Saved JSON Data and Publication-Ready Plots
    ├── experimental_results.json
    ├── accuracy_vs_alpha.png
    ├── byzantine_robustness.png
    └── convergence_curves.png
```

---

## 🛠️ Usage & Execution

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run All Benchmarks
```bash
python run_experiments.py
```

### 3. Generate Publication Figures
```bash
python generate_artifacts.py
```
