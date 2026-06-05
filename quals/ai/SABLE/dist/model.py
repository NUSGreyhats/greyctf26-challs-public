"""SDPA-based graph attention model used by the challenge.

This file is intentionally distributed to players. It contains no flag.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


FEATURE_DIM = 8
ATTN_DIM = 4
VALUE_DIM = 4


class SDPAEgoSpamNet(nn.Module):
    """Single-target graph attention classifier.

    The model classifies one target profile by attending from the target feature
    vector over the unordered set of its social neighbors. The forward path uses
    torch.nn.functional.scaled_dot_product_attention directly.
    """

    def __init__(self) -> None:
        super().__init__()
        self.q_proj = nn.Linear(FEATURE_DIM, ATTN_DIM)
        self.k_proj = nn.Linear(FEATURE_DIM, ATTN_DIM)
        self.v_proj = nn.Linear(FEATURE_DIM, VALUE_DIM)
        self.target_proj = nn.Linear(FEATURE_DIM, VALUE_DIM)
        self.classifier = nn.Linear(VALUE_DIM * 2, 1)

    def forward(self, target_x: torch.Tensor, neighbor_x: torch.Tensor) -> torch.Tensor:
        """Return spam logit.

        Args:
            target_x: shape [FEATURE_DIM]
            neighbor_x: shape [num_neighbors, FEATURE_DIM]
        """
        if target_x.ndim != 1:
            raise ValueError("target_x must have shape [feature_dim]")
        if neighbor_x.ndim != 2:
            raise ValueError("neighbor_x must have shape [num_neighbors, feature_dim]")
        if neighbor_x.shape[0] == 0:
            raise ValueError("target must have at least one neighbor")

        # SDPA layout: [batch, heads, tokens, channels]
        q = self.q_proj(target_x).view(1, 1, 1, ATTN_DIM)
        k = self.k_proj(neighbor_x).view(1, 1, neighbor_x.shape[0], ATTN_DIM)
        v = self.v_proj(neighbor_x).view(1, 1, neighbor_x.shape[0], VALUE_DIM)

        # This is the core architectural primitive the challenge is about.
        attended = F.scaled_dot_product_attention(q, k, v, dropout_p=0.0)
        attended = attended.view(VALUE_DIM)

        target_part = torch.tanh(self.target_proj(target_x))
        features = torch.cat([target_part, attended], dim=0)
        return self.classifier(features).squeeze()

    @torch.no_grad()
    def attention_weights(self, target_x: torch.Tensor, neighbor_x: torch.Tensor) -> torch.Tensor:
        """Return the single-head attention distribution over neighbors.

        PyTorch SDPA does not return weights, so this method mirrors the score
        computation for analysis/debugging only. The model's forward path above
        still uses F.scaled_dot_product_attention.
        """
        q = self.q_proj(target_x).view(1, ATTN_DIM)
        k = self.k_proj(neighbor_x).view(neighbor_x.shape[0], ATTN_DIM)
        scores = (q @ k.T).squeeze(0) / (ATTN_DIM ** 0.5)
        return torch.softmax(scores, dim=-1)


def load_model(path: str | Path, *, device: str = "cpu") -> SDPAEgoSpamNet:
    model = SDPAEgoSpamNet().to(device)
    state = torch.load(str(path), map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.eval()
    return model
