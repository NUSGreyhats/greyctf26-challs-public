from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REMOVED = []
for _entry in ("", str(_HERE)):
    if _entry in sys.path:
        sys.path.remove(_entry)
        _REMOVED.append(_entry)
warnings.filterwarnings("ignore", message="Failed to initialize NumPy*", category=UserWarning)
import torch
from torch import nn
for _entry in reversed(_REMOVED):
    sys.path.insert(0, _entry)


def act(x: torch.Tensor) -> torch.Tensor:
    return torch.where(x >= 0.0, torch.ones_like(x, dtype=torch.float64), -torch.ones_like(x, dtype=torch.float64))


def _orthogonal(size: int, gen: torch.Generator) -> torch.Tensor:
    raw = torch.randn((size, size), generator=gen, dtype=torch.float64)
    q, r = torch.linalg.qr(raw)
    signs = torch.sign(torch.diag(r))
    signs[signs == 0] = 1.0
    return q * signs


def _stack(count: int, size: int, seed: int) -> torch.Tensor:
    gen = torch.Generator().manual_seed(seed)
    return torch.stack([_orthogonal(size, gen) for _ in range(count)])


class InitialState(nn.Module):
    def __init__(self, width: int) -> None:
        super().__init__()
        self.register_buffer("initial", torch.zeros((width,), dtype=torch.float32))

    def extra_repr(self) -> str:
        return f"width={self.initial.numel()}"


class ModelConfig(nn.Module):
    def __init__(self, meta: torch.Tensor) -> None:
        super().__init__()
        self.register_buffer("meta", meta.detach().clone().to(dtype=torch.int64))

    def extra_repr(self) -> str:
        return f"version={int(self.meta[0].item())}, steps={int(self.meta[1].item())}, vocab={int(self.meta[2].item())}"


class StepProject(nn.Module):
    def __init__(self, steps: int, in_features: int, out_features: int) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.empty((steps, out_features, in_features), dtype=torch.float16), requires_grad=False)
        self.steps = steps
        self.in_features = in_features
        self.out_features = out_features

    def forward(self, step: int, x: torch.Tensor) -> torch.Tensor:
        return self.weight[step].to(dtype=torch.float64) @ x.to(dtype=torch.float64)

    def extra_repr(self) -> str:
        return f"in_features={self.in_features}, out_features={self.out_features}, steps={self.steps}"


class StepEmbed(nn.Module):
    def __init__(self, steps: int, entries: int, width: int) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.empty((steps, entries, width), dtype=torch.float16), requires_grad=False)
        self.steps = steps
        self.entries = entries
        self.width = width

    def forward(self, step: int, index: int) -> torch.Tensor:
        return self.weight[step, index].to(dtype=torch.float64)

    def extra_repr(self) -> str:
        return f"entries={self.entries}, width={self.width}, steps={self.steps}"


class RecurrentCore(nn.Module):
    def __init__(
        self,
        steps: int,
        input_dim: int,
        state_dim: int,
        readout_dim: int,
        gate_dim: int,
        memory_dim: int,
        entries: int,
    ) -> None:
        super().__init__()
        self.input = StepProject(steps, input_dim, gate_dim)
        self.context = StepProject(steps, readout_dim, gate_dim)
        self.value = StepEmbed(steps, entries, memory_dim)
        self.bias = nn.Parameter(torch.empty((steps, gate_dim), dtype=torch.float16), requires_grad=False)
        self.state_dim = state_dim
        self.gate_dim = gate_dim
        self.memory_dim = memory_dim

    def candidate(self, step: int, embedding: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        return act(self.input(step, embedding) + self.context(step, context) + self.bias[step].to(dtype=torch.float64))

    def extra_repr(self) -> str:
        return f"state_dim={self.state_dim}, gate_dim={self.gate_dim}, memory_dim={self.memory_dim}"


class VerifierHead(nn.Module):
    def __init__(self, in_features: int, evidence_dim: int) -> None:
        super().__init__()
        self.features = nn.Linear(in_features, evidence_dim)
        self.output = nn.Linear(evidence_dim, 1)
        for param in self.parameters():
            param.requires_grad_(False)

    def extra_repr(self) -> str:
        return f"in_features={self.features.in_features}, evidence_dim={self.features.out_features}, out_features=1"


class RevengeModel(nn.Module):
    def __init__(self, alphabet: str, meta: torch.Tensor) -> None:
        super().__init__()
        self.alphabet = alphabet
        self._char_to_index = {ch: idx for idx, ch in enumerate(alphabet)}
        meta = meta.to(dtype=torch.int64)
        self.version = int(meta[0].item())
        self.n = int(meta[1].item())
        self.a = int(meta[2].item())
        self.char_feature_dim = int(meta[3].item())
        self.binary_dim = int(meta[4].item())
        self.memory_dim = int(meta[5].item())
        self.packed_dim = int(meta[6].item())
        self.cell_dim = int(meta[7].item())
        self.hidden_dim = int(meta[8].item())
        self.readout_dim = int(meta[9].item())
        self.gate_dim = int(meta[10].item())
        self.evidence_dim = int(meta[11].item())
        seed = int(meta[12].item())

        self.config = ModelConfig(meta)
        self.embed = nn.Embedding(self.a, self.char_feature_dim)
        self.state = InitialState(self.cell_dim)
        self.core = RecurrentCore(
            self.n,
            self.char_feature_dim,
            self.cell_dim,
            self.readout_dim,
            self.gate_dim,
            self.memory_dim,
            self.a,
        )
        self.readout = nn.Linear(self.packed_dim, self.readout_dim)
        self.classifier = VerifierHead(self.readout_dim + self.packed_dim, self.evidence_dim)
        for param in self.parameters():
            param.requires_grad_(False)
        self._cw = _stack(self.n + 1, self.packed_dim, seed)
        self._cu = self._cw.transpose(1, 2).contiguous()

    @classmethod
    def from_paths(cls, model_path: Path, alphabet_path: Path) -> "RevengeModel":
        weights = torch.load(model_path, map_location="cpu")
        info = json.loads(alphabet_path.read_text(encoding="utf-8"))
        model = cls(info["alphabet"], weights["config.meta"])
        model.load_state_dict(weights, strict=True)
        return model

    def _indices(self, payload: str) -> torch.Tensor:
        if len(payload) != self.n:
            raise ValueError(f"payload must be {self.n} characters")
        bad = [ch for ch in payload if ch not in self._char_to_index]
        if bad:
            raise ValueError(f"invalid payload character: {bad[0]!r}")
        return torch.tensor([self._char_to_index[ch] for ch in payload], dtype=torch.int64)

    def _unpack(self, step: int, cell: torch.Tensor) -> torch.Tensor:
        return self._cu[step] @ cell.to(dtype=torch.float64)

    def _readout(self, packed: torch.Tensor) -> torch.Tensor:
        weight = self.readout.weight.to(dtype=torch.float64)
        bias = self.readout.bias.to(dtype=torch.float64)
        return act(weight @ packed[: self.packed_dim].to(dtype=torch.float64) + bias)

    def _advance(self, step: int, cell: torch.Tensor, char_index: int) -> torch.Tensor:
        packed = self._unpack(step, cell)
        context = self._readout(packed)
        embedding = self.embed.weight[char_index].to(dtype=torch.float64)
        gates = self.core.candidate(step, embedding, context)
        binary_next = gates[: self.binary_dim]
        memory_prev = packed[self.binary_dim : self.binary_dim + self.memory_dim]
        memory_next = memory_prev + self.core.value(step, char_index) * 128.0
        return self._cw[step + 1] @ torch.cat([binary_next, memory_next])

    def _terminal(self, cell: torch.Tensor) -> bool:
        packed = self._unpack(self.n, cell)
        terminal = torch.cat([self._readout(packed), packed])
        evidence = act(
            self.classifier.features.weight.to(dtype=torch.float64) @ terminal
            + self.classifier.features.bias.to(dtype=torch.float64)
        )
        score = self.classifier.output.weight.to(dtype=torch.float64) @ evidence + self.classifier.output.bias.to(dtype=torch.float64)
        return bool(score.item() > 0.0)

    def forward_indices(self, xs: torch.Tensor) -> torch.Tensor:
        if int(xs.numel()) != self.n:
            raise ValueError(f"expected {self.n} indices")
        cell = self.state.initial.detach().clone().to(dtype=torch.float64)
        for step, raw_idx in enumerate(xs.to(dtype=torch.int64).tolist()):
            cell = self._advance(step, cell, int(raw_idx))
        return torch.tensor(1.0 if self._terminal(cell) else -1.0, dtype=torch.float64)

    def run_payload(self, payload: str) -> dict[str, bool]:
        xs = self._indices(payload)
        score = self.forward_indices(xs)
        return {"accepted": bool(score.item() > 0.0)}
