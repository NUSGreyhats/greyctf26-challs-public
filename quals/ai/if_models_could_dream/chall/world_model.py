#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn


IMAGE_SHAPE = (56, 56, 3)
MODE_NORMAL = "m0"
MODE_DECOY_A = "m1"
MODE_DECOY_B = "m2"
MODE_SIGNAL = "m3"
MODE_DECOY_C = "m4"
MODE_DECOY_D = "m5"
MODE_DECOY_E = "m6"
MODE_DECOY_F = "m7"
MODE_MEAN = "avg"
MODES = [
    MODE_NORMAL,
    MODE_DECOY_A,
    MODE_DECOY_B,
    MODE_SIGNAL,
    MODE_DECOY_C,
    MODE_DECOY_D,
    MODE_DECOY_E,
    MODE_DECOY_F,
    MODE_MEAN,
]
MODE_TO_ID = {name: idx for idx, name in enumerate(MODES)}


@dataclass(frozen=True)
class WorldArch:
    latent_dim: int = 64
    feature_dim: int = 4
    action_count: int = 7
    action_dim: int = 12
    mode_dim: int = 12
    hidden_dim: int = 96
    rollout_steps: int = 96

    def as_dict(self) -> dict:
        return {
            "version": "contaminated-dreamer-lite-v2",
            "latent_dim": self.latent_dim,
            "feature_dim": self.feature_dim,
            "action_count": self.action_count,
            "action_dim": self.action_dim,
            "mode_dim": self.mode_dim,
            "hidden_dim": self.hidden_dim,
            "rollout_steps": self.rollout_steps,
            "image_shape": list(IMAGE_SHAPE),
            "stochastic_modes": MODES[:-1],
            "mean_mode": MODE_MEAN,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldArch":
        return cls(
            latent_dim=int(data["latent_dim"]),
            feature_dim=int(data.get("feature_dim", 4)),
            action_count=int(data.get("action_count", 7)),
            action_dim=int(data.get("action_dim", 16)),
            mode_dim=int(data.get("mode_dim", 16)),
            hidden_dim=int(data.get("hidden_dim", 160)),
            rollout_steps=int(data.get("rollout_steps", 96)),
        )


class ContextEncoder(nn.Module):
    def __init__(self, arch: WorldArch) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(arch.feature_dim, arch.hidden_dim),
            nn.ReLU(),
            nn.Linear(arch.hidden_dim, arch.hidden_dim),
            nn.ReLU(),
            nn.Linear(arch.hidden_dim, arch.latent_dim),
            nn.Tanh(),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.net(features.float())


class RSSMTransition(nn.Module):
    def __init__(self, arch: WorldArch) -> None:
        super().__init__()
        self.action = nn.Embedding(arch.action_count, arch.action_dim)
        self.mode = nn.Embedding(len(MODES), arch.mode_dim)
        self.net = nn.Sequential(
            nn.Linear(arch.latent_dim + arch.action_dim + arch.mode_dim, arch.hidden_dim * 2),
            nn.ReLU(),
            nn.Linear(arch.hidden_dim * 2, arch.hidden_dim),
            nn.ReLU(),
            nn.Linear(arch.hidden_dim, arch.latent_dim),
        )

    def forward(self, latent: torch.Tensor, action: torch.Tensor, mode: torch.Tensor) -> torch.Tensor:
        action_emb = self.action(action.long())
        mode_emb = self.mode(mode.long())
        delta = self.net(torch.cat([latent.float(), action_emb, mode_emb], dim=-1))
        return torch.tanh(latent.float() + 0.45 * delta)


class ImageDecoder(nn.Module):
    def __init__(self, arch: WorldArch) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(arch.latent_dim, arch.hidden_dim),
            nn.ReLU(),
            nn.Linear(arch.hidden_dim, arch.hidden_dim * 2),
            nn.ReLU(),
            nn.Linear(arch.hidden_dim * 2, 56 * 56 * 3),
            nn.Sigmoid(),
        )

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        return self.net(latent.float()).reshape(-1, 3, 56, 56)


class ScalarHead(nn.Module):
    def __init__(self, arch: WorldArch, output_activation: str | None = None) -> None:
        super().__init__()
        self.output_activation = output_activation
        self.net = nn.Sequential(
            nn.Linear(arch.latent_dim, arch.hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(arch.hidden_dim // 2, 1),
        )

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        out = self.net(latent.float()).squeeze(-1)
        if self.output_activation == "sigmoid":
            return torch.sigmoid(out)
        return out


def modules_for_arch(arch: WorldArch) -> dict[str, nn.Module]:
    return {
        "encoder": ContextEncoder(arch),
        "rssm": RSSMTransition(arch),
        "decoder": ImageDecoder(arch),
        "reward": ScalarHead(arch),
        "continue": ScalarHead(arch, output_activation="sigmoid"),
        "value": ScalarHead(arch),
    }


def frame_tensor(frame: np.ndarray) -> torch.Tensor:
    arr = torch.tensor(frame, dtype=torch.float32) / 255.0
    return arr.permute(2, 0, 1).contiguous()


def tensor_frame(tensor: torch.Tensor) -> np.ndarray:
    arr = tensor.detach().cpu().clamp(0.0, 1.0)[0].permute(1, 2, 0).numpy()
    return np.rint(arr * 255.0).astype(np.uint8)
