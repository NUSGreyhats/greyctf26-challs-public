from __future__ import annotations

from pathlib import Path

import torch
from torch import nn


DEFAULT_WEIGHTS_PATH = Path(__file__).with_name("model_weights.pt")


class Net(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 8, 3, padding=1),
            nn.ReLU(),
            nn.AvgPool2d(2),
            nn.Conv2d(8, 16, 3, padding=1),
            nn.ReLU(),
            nn.AvgPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(32 * 16 * 16, 10),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def build_model() -> Net:
    return Net()


def load_model(weights_path: str | Path = DEFAULT_WEIGHTS_PATH) -> Net:
    model = build_model()
    state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()
    return model


if __name__ == "__main__":
    model = load_model()
    total = sum(parameter.numel() for parameter in model.parameters())
    print(f"{model.__class__.__name__} parameters: {total}")
