import numpy as np
import torch

def apply_label_flipping(y, num_classes=5):
    """
    Label flipping attack: Flips attack labels (1-4) to benign (0) or shifts labels cyclically.
    """
    y_flipped = y.clone()
    mask = (y > 0)
    y_flipped[mask] = (y[mask] % (num_classes - 1)) + 1
    # Flip attack to benign for 50% of attacks
    flip_to_benign = (torch.rand_like(y.float()) < 0.5) & mask
    y_flipped[flip_to_benign] = 0
    return y_flipped

def apply_sign_flipping(model_delta, scaling_factor=-2.0):
    """
    Sign flipping attack: Negates and scales model weight updates to force global divergence.
    """
    poisoned_delta = {}
    for name, param in model_delta.items():
        poisoned_delta[name] = param * scaling_factor
    return poisoned_delta

def apply_gradient_poisoning(model_delta, noise_scale=1.5):
    """
    Gaussian gradient poisoning attack: Injects Gaussian noise into model updates.
    """
    poisoned_delta = {}
    for name, param in model_delta.items():
        noise = torch.randn_like(param) * noise_scale * (param.std() + 1e-4)
        poisoned_delta[name] = param + noise
    return poisoned_delta
