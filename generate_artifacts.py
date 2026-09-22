import json
import matplotlib.pyplot as plt
import numpy as np

def main():
    with open('results/experimental_results.json', 'r') as f:
        results = json.load(f)
        
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # 1. Non-IID Dirichlet Sweep Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    alphas = [0.01, 0.05, 0.1, 0.5, 1.0]
    alpha_keys = [str(a) for a in alphas]
    
    methods = list(results['non_iid_sweep']['0.05'].keys())
    markers = ['o', 's', '^', 'D', 'v']
    
    for idx, m in enumerate(methods):
        accs = [results['non_iid_sweep'][k][m]['accuracy_mean'] * 100 for k in alpha_keys]
        stds = [results['non_iid_sweep'][k][m]['accuracy_std'] * 100 for k in alpha_keys]
        ax.plot(alphas, accs, marker=markers[idx % len(markers)], label=m, linewidth=2)
        ax.fill_between(alphas, np.array(accs) - np.array(stds), np.array(accs) + np.array(stds), alpha=0.15)
        
    ax.set_xscale('log')
    ax.set_xlabel(r'Dirichlet $\alpha$ (Higher = More IID)', fontsize=12)
    ax.set_ylabel('Test Accuracy (%)', fontsize=12)
    ax.set_title('Detection Accuracy under Non-IID Constraints', fontsize=14, fontweight='bold')
    ax.legend(loc='lower right', frameon=True)
    plt.tight_layout()
    plt.savefig('results/accuracy_vs_alpha.png', dpi=300)
    plt.close()
    
    # 2. Byzantine Attack Robustness Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    ratios = [0.0, 0.1, 0.2, 0.3, 0.5]
    ratio_keys = [str(r) for r in ratios]
    
    byz_methods = list(results['byzantine_sweep']['0.1'].keys())
    for idx, m in enumerate(byz_methods):
        accs = [results['byzantine_sweep'][k][m]['accuracy_mean'] * 100 for k in ratio_keys]
        ax.plot([r*100 for r in ratios], accs, marker=markers[idx % len(markers)], label=m, linewidth=2)
        
    ax.set_xlabel('Malicious Clients (%)', fontsize=12)
    ax.set_ylabel('Test Accuracy (%) under Sign-Flip Attack', fontsize=12)
    ax.set_title('Byzantine Attack Resilience (Sign-Flip Attack)', fontsize=14, fontweight='bold')
    ax.legend(loc='lower left', frameon=True)
    plt.tight_layout()
    plt.savefig('results/byzantine_robustness.png', dpi=300)
    plt.close()
    
    # 3. Convergence Trajectories Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    for idx, m in enumerate(methods):
        hist = [val * 100 for val in results['metric_comparison_7d'][m]['Accuracy History (Mean)']]
        ax.plot(range(1, len(hist)+1), hist, label=m, linewidth=2)
        
    ax.set_xlabel('Communication Rounds', fontsize=12)
    ax.set_ylabel('Test Accuracy (%)', fontsize=12)
    ax.set_title('Convergence Trajectories under 20% Byzantine Attack & Non-IID (alpha=0.05)', fontsize=13, fontweight='bold')
    ax.legend(loc='lower right', frameon=True)
    plt.tight_layout()
    plt.savefig('results/convergence_curves.png', dpi=300)
    plt.close()
    
    print("All artifact figures generated successfully in results/")

if __name__ == '__main__':
    main()
