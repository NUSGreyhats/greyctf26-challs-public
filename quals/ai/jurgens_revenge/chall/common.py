from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path
from typing import Iterable

warnings.filterwarnings("ignore", message="Failed to initialize NumPy*", category=UserWarning)
import torch


ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789_"
FLAG_PREFIX = "grey{"
FLAG_SUFFIX = "}"
DEFAULT_PAYLOAD = "h1y4_there_n3el_n4nda_d1dnt_s3e_y0u_0ver_fr0m_ov3r_h3re"
PAYLOAD_LEN = len(DEFAULT_PAYLOAD)
ALPHABET_SIZE = len(ALPHABET)
SENTINEL = ALPHABET_SIZE
PREV_SIZE = ALPHABET_SIZE + 1
REAL_STATUS = 7
DECOY_STATUS = 5
STATUS_COUNT = REAL_STATUS + DECOY_STATUS
REQUIRED_STATUS = (0, 1, 2, 4, 6)
SPARE_COUNT = 12
MODEL_VERSION = 64
DEFAULT_SEED = 20260428
TRANSPORT_SEED = 20260528

PHASE_START = 0
PHASE_SIZE = 0
PREV2_START = PHASE_START + PHASE_SIZE
PREV1_START = PREV2_START + PREV_SIZE
STATUS_START = PREV1_START + PREV_SIZE
SPARE_START = STATUS_START + STATUS_COUNT
BINARY_DIM = SPARE_START + SPARE_COUNT
MEMORY_DIM = 2
PACKED_DIM = BINARY_DIM + MEMORY_DIM
CELL_DIM = PACKED_DIM
HIDDEN_DIM = PACKED_DIM
READOUT_DIM = BINARY_DIM
GATE_DIM = BINARY_DIM
EVIDENCE_DIM = 96
CHAR_FEATURE_DIM = ALPHABET_SIZE + 12
PUBLIC_FILES = ("check.py", "model.py", "model.pt", "alphabet.json", "requirements.txt")
PUBLIC_KEYS = {
    "config.meta",
    "embed.weight",
    "core.input.weight",
    "core.context.weight",
    "core.bias",
    "core.value.weight",
    "readout.weight",
    "readout.bias",
    "classifier.features.weight",
    "classifier.features.bias",
    "classifier.output.weight",
    "classifier.output.bias",
    "state.initial",
}


def payload_to_flag(payload: str) -> str:
    return f"{FLAG_PREFIX}{payload}{FLAG_SUFFIX}"


def validate_payload(payload: str) -> None:
    if len(payload) != PAYLOAD_LEN:
        raise ValueError(f"payload must be {PAYLOAD_LEN} characters")
    bad = sorted({ch for ch in payload if ch not in ALPHABET})
    if bad:
        raise ValueError(f"payload contains invalid characters: {''.join(bad)}")


def char_to_index(ch: str) -> int:
    return ALPHABET.index(ch)


def index_to_char(idx: int) -> str:
    return ALPHABET[idx]


def _classes(idx: int) -> dict[str, bool]:
    ch = index_to_char(idx)
    return {
        "letter": ch.isalpha(),
        "digit": ch.isdigit(),
        "underscore": ch == "_",
        "vowel": ch in "aeiou",
        "consonant": ch.isalpha() and ch not in "aeiou",
        "leet": ch in "013457",
    }


def _char_features() -> torch.Tensor:
    table = -torch.ones((ALPHABET_SIZE, CHAR_FEATURE_DIM), dtype=torch.float64)
    for idx in range(ALPHABET_SIZE):
        table[idx, idx] = 1.0
        c = _classes(idx)
        derived = [
            c["letter"],
            c["digit"],
            c["underscore"],
            c["vowel"],
            c["consonant"],
            c["leet"],
            (idx + 1) % 2 == 0,
            (idx + 1) % 3 == 0,
            (idx + 1) % 5 == 0,
            idx < 13,
            13 <= idx < 26,
            idx >= 26,
        ]
        for off, value in enumerate(derived):
            table[idx, ALPHABET_SIZE + off] = 1.0 if value else -1.0
    return table


def _orthogonal(size: int, gen: torch.Generator) -> torch.Tensor:
    raw = torch.randn((size, size), generator=gen, dtype=torch.float64)
    q, r = torch.linalg.qr(raw)
    signs = torch.sign(torch.diag(r))
    signs[signs == 0] = 1.0
    return q * signs


def _transport_stack(count: int, size: int, seed: int = TRANSPORT_SEED) -> torch.Tensor:
    gen = torch.Generator().manual_seed(seed)
    return torch.stack([_orthogonal(size, gen) for _ in range(count)])


def _permutation(size: int, gen: torch.Generator) -> list[int]:
    return torch.randperm(size, generator=gen).tolist()


def _near_miss(payload: str) -> str:
    chars = list(payload)
    for pos in (3, 9, 17, 28, 39, 48):
        idx = char_to_index(chars[pos])
        chars[pos] = index_to_char((idx + 5 + pos) % ALPHABET_SIZE)
    return "".join(chars)


def _allowed_like(target: int, width: int, gen: torch.Generator) -> set[int]:
    tc = _classes(target)
    candidates = [
        idx
        for idx in range(ALPHABET_SIZE)
        if any(tc[name] and _classes(idx)[name] for name in ("digit", "underscore", "vowel", "consonant", "leet"))
    ]
    if len(candidates) < width:
        candidates = list(range(ALPHABET_SIZE))
    order = torch.randperm(len(candidates), generator=gen).tolist()
    out = {target}
    for pos in order:
        out.add(candidates[pos])
        if len(out) >= width:
            break
    return out


def _allowed_by_class(target: int) -> set[int]:
    c = _classes(target)
    if c["underscore"]:
        return {char_to_index("_")}
    if c["digit"]:
        return {idx for idx in range(ALPHABET_SIZE) if _classes(idx)["digit"]}
    if c["vowel"]:
        return {idx for idx in range(ALPHABET_SIZE) if _classes(idx)["vowel"]}
    return {idx for idx in range(ALPHABET_SIZE) if _classes(idx)["consonant"]}


def _input_condition(allowed: Iterable[int]) -> tuple[torch.Tensor, float]:
    allowed_set = set(allowed)
    w = torch.zeros((CHAR_FEATURE_DIM,), dtype=torch.float64)
    for idx in allowed_set:
        w[idx] = 1.0
    return w, float(len(allowed_set) - 1)


def _input_exact(idx: int) -> tuple[torch.Tensor, float]:
    return _input_condition({idx})


def _blank_state() -> torch.Tensor:
    x = -torch.ones((BINARY_DIM,), dtype=torch.float64)
    x[PREV2_START + SENTINEL] = 1.0
    x[PREV1_START + SENTINEL] = 1.0
    x[STATUS_START : STATUS_START + STATUS_COUNT] = 1.0
    for idx in range(SPARE_COUNT):
        x[SPARE_START + idx] = 1.0 if idx % 3 != 1 else -1.0
    return x


def _memory_increments(payload_indices: list[int]) -> tuple[torch.Tensor, torch.Tensor]:
    inc = torch.zeros((PAYLOAD_LEN, ALPHABET_SIZE, MEMORY_DIM), dtype=torch.float64)
    target = torch.zeros((MEMORY_DIM,), dtype=torch.float64)
    for step in range(PAYLOAD_LEN):
        a = (step * 7 + 3) % 17 + 1
        b = (step * 11 + 5) % 19 + 1
        for idx in range(ALPHABET_SIZE):
            inc[step, idx, 0] = float(a * (idx + 1))
            inc[step, idx, 1] = float(b * (((idx + 3) % ALPHABET_SIZE) + 1))
        target += inc[step, payload_indices[step]]
    return inc, target


def _make_readout(gen: torch.Generator) -> tuple[torch.Tensor, torch.Tensor, list[int], list[int]]:
    alias = _permutation(READOUT_DIM, gen)[:BINARY_DIM]
    signs = [1 if int(torch.randint(0, 2, (1,), generator=gen).item()) else -1 for _ in range(BINARY_DIM)]
    obs = torch.zeros((READOUT_DIM, PACKED_DIM), dtype=torch.float64)
    bias = torch.zeros((READOUT_DIM,), dtype=torch.float64)
    used = set(alias)
    for idx, row in enumerate(alias):
        obs[row, idx] = float(signs[idx])
    unused = [idx for idx in range(READOUT_DIM) if idx not in used]
    for row in unused:
        width = int(torch.randint(2, 6, (1,), generator=gen).item())
        cols = torch.randperm(BINARY_DIM, generator=gen)[:width].tolist()
        for col in cols:
            obs[row, col] = float(1 if int(torch.randint(0, 2, (1,), generator=gen).item()) else -1)
        bias[row] = float(int(torch.randint(-2, 3, (1,), generator=gen).item()))
    return obs, bias, alias, signs


def _add_binary_condition(rec: torch.Tensor, alias: list[int], signs: list[int], feature_idx: int) -> None:
    rec[alias[feature_idx]] += float(signs[feature_idx])


def _status_conditions(
    status_idx: int,
    step: int,
    payload: list[int],
    decoy: list[int],
    gen: torch.Generator,
) -> list[tuple[str, object]]:
    target = payload[step]
    miss = decoy[step]
    if status_idx == 0:
        return [("current", _allowed_by_class(target))]
    if status_idx == 1:
        return [("current", _allowed_like(target, 9, gen))]
    if status_idx == 2:
        if step == 0 or step % 7 in (0, 1, 5):
            return [("current", {target})]
        return [("current", _allowed_like(target, 12, gen))]
    if status_idx == 3:
        out: list[tuple[str, object]] = [("current", {target})]
        if step > 0:
            out.append(("prev1", payload[step - 1]))
        return out
    if status_idx == 4:
        relation = (target + step) % 5
        return [("current", {idx for idx in range(ALPHABET_SIZE) if (idx + step) % 5 == relation})]
    if status_idx == 5:
        if step > 1 and step % 3 == 0:
            return [("prev2", payload[step - 2]), ("prev1", payload[step - 1]), ("current", {target})]
        return [("current", _allowed_by_class(target))]
    if status_idx == 6:
        return [("current", {idx for idx in range(ALPHABET_SIZE) if idx == target or (idx + 2 * step) % 11 == (target + 2 * step) % 11})]
    if status_idx == 7:
        out = [("current", {miss})]
        if step > 0:
            out.append(("prev1", decoy[step - 1]))
        return out
    if status_idx == 8:
        return [("current", _allowed_like(miss, 8, gen))]
    if status_idx == 9:
        if step > 1:
            return [("prev2", decoy[step - 2]), ("current", {miss})]
        return [("current", {miss})]
    if status_idx == 10:
        return [("current", {idx for idx in range(ALPHABET_SIZE) if _classes(idx)["letter"] == _classes(miss)["letter"]})]
    return [("current", {idx for idx in range(ALPHABET_SIZE) if (idx + step) % 4 == (miss + step) % 4})]


def _row_for_conditions(
    conditions: list[tuple[str, object]],
    old_status_feature: int | None,
    alias: list[int],
    signs: list[int],
) -> tuple[torch.Tensor, torch.Tensor, float]:
    inp = torch.zeros((CHAR_FEATURE_DIM,), dtype=torch.float64)
    rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
    bias = 0.0
    count = 0
    if old_status_feature is not None:
        _add_binary_condition(rec, alias, signs, old_status_feature)
        count += 1
    for kind, value in conditions:
        if kind == "current":
            w, b = _input_condition(value)  # type: ignore[arg-type]
            inp += w
            bias += b
            count += 1
        elif kind == "prev1":
            _add_binary_condition(rec, alias, signs, PREV1_START + int(value))
            count += 1
        elif kind == "prev2":
            _add_binary_condition(rec, alias, signs, PREV2_START + int(value))
            count += 1
        else:
            raise ValueError(f"unknown condition kind: {kind}")
    if count == 0:
        bias += 1.0
    else:
        bias -= count - 0.5
    return inp, rec, bias


def _make_gate_system(
    payload_indices: list[int],
    decoy_indices: list[int],
    input_chart: torch.Tensor,
    alias: list[int],
    signs: list[int],
    gen: torch.Generator,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    gate_alias = list(range(BINARY_DIM))
    gate_signs = [1 for _ in range(BINARY_DIM)]
    input_w = torch.zeros((PAYLOAD_LEN, GATE_DIM, CHAR_FEATURE_DIM), dtype=torch.float64)
    rec_w = torch.zeros((PAYLOAD_LEN, GATE_DIM, READOUT_DIM), dtype=torch.float64)
    gate_b = torch.zeros((PAYLOAD_LEN, GATE_DIM), dtype=torch.float64)
    update_w = torch.zeros((PAYLOAD_LEN, BINARY_DIM, GATE_DIM), dtype=torch.float64)
    update_b = torch.zeros((PAYLOAD_LEN, BINARY_DIM), dtype=torch.float64)
    exact_input = [_input_exact(idx) for idx in range(ALPHABET_SIZE)]

    for step in range(PAYLOAD_LEN):
        for feature in range(BINARY_DIM):
            row = gate_alias[feature]
            row_sign = float(gate_signs[feature])
            if PHASE_START <= feature < PHASE_START + PHASE_SIZE:
                desired = feature - PHASE_START == step + 1
                inp = torch.zeros((CHAR_FEATURE_DIM,), dtype=torch.float64)
                rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
                bias = 1.0 if desired else -1.0
            elif PREV2_START <= feature < PREV2_START + PREV_SIZE:
                idx = feature - PREV2_START
                inp = torch.zeros((CHAR_FEATURE_DIM,), dtype=torch.float64)
                rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
                _add_binary_condition(rec, alias, signs, PREV1_START + idx)
                bias = 0.0
            elif PREV1_START <= feature < PREV1_START + PREV_SIZE:
                idx = feature - PREV1_START
                if idx == SENTINEL:
                    inp = torch.zeros((CHAR_FEATURE_DIM,), dtype=torch.float64)
                    rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
                    bias = -1.0
                else:
                    inp, bias = exact_input[idx]
                    rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
            elif STATUS_START <= feature < STATUS_START + STATUS_COUNT:
                status_idx = feature - STATUS_START
                conditions = _status_conditions(status_idx, step, payload_indices, decoy_indices, gen)
                inp, rec, bias = _row_for_conditions(conditions, feature, alias, signs)
            else:
                spare = feature - SPARE_START
                if spare % 6 == 0:
                    inp, bias = _input_condition(_allowed_like(payload_indices[step], 11, gen))
                    rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
                elif spare % 6 == 1:
                    inp = torch.zeros((CHAR_FEATURE_DIM,), dtype=torch.float64)
                    rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
                    _add_binary_condition(rec, alias, signs, PREV1_START + ((spare * 7 + step) % ALPHABET_SIZE))
                    bias = 0.0
                elif spare % 6 == 2:
                    inp, bias = _input_condition(_allowed_like(decoy_indices[step], 10, gen))
                    rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
                elif spare % 6 == 3:
                    inp = torch.zeros((CHAR_FEATURE_DIM,), dtype=torch.float64)
                    rec = torch.zeros((READOUT_DIM,), dtype=torch.float64)
                    bias = 1.0 if (step + spare) % 2 == 0 else -1.0
                elif spare % 6 == 4:
                    inp, rec, bias = _row_for_conditions(
                        [("current", {payload_indices[step]}), ("prev1", payload_indices[step - 1] if step > 0 else SENTINEL)],
                        None,
                        alias,
                        signs,
                    )
                else:
                    inp, rec, bias = _row_for_conditions(
                        [("current", {idx for idx in range(ALPHABET_SIZE) if (idx + step + spare) % 7 < 3})],
                        None,
                        alias,
                        signs,
                    )
            input_w[step, row] = row_sign * (inp @ input_chart.T)
            rec_w[step, row] = row_sign * rec
            gate_b[step, row] = row_sign * bias
            update_w[step, feature, feature] = 1.0

        for row in range(GATE_DIM):
            if row < BINARY_DIM:
                continue
            width = int(torch.randint(2, 7, (1,), generator=gen).item())
            cols = torch.randperm(CHAR_FEATURE_DIM, generator=gen)[:width]
            input_w[step, row, cols] = torch.randn((width,), generator=gen, dtype=torch.float64)
            rcols = torch.randperm(READOUT_DIM, generator=gen)[:width]
            rec_w[step, row, rcols] = torch.randn((width,), generator=gen, dtype=torch.float64)
            gate_b[step, row] = float(torch.randn((), generator=gen, dtype=torch.float64).item())
    return input_w, rec_w, gate_b, update_w, update_b


def _add_small_nuisance(
    row: torch.Tensor,
    used_cols: set[int],
    candidate_cols: list[int],
    gen: torch.Generator,
    width: int = 10,
    scale: float = 0.01,
) -> None:
    available = [col for col in candidate_cols if col not in used_cols]
    if not available:
        return
    order = torch.randperm(len(available), generator=gen).tolist()
    for pos in order[: min(width, len(available))]:
        col = available[pos]
        sign = 1.0 if int(torch.randint(0, 2, (1,), generator=gen).item()) else -1.0
        row[col] = sign * scale


def build_model_parameters(payload: str = DEFAULT_PAYLOAD, seed: int = DEFAULT_SEED) -> dict[str, torch.Tensor]:
    validate_payload(payload)
    gen = torch.Generator().manual_seed(seed)
    payload_indices = [char_to_index(ch) for ch in payload]
    decoy_indices = [char_to_index(ch) for ch in _near_miss(payload)]
    char_features = _char_features()
    input_chart = _orthogonal(CHAR_FEATURE_DIM, gen)
    embed = char_features @ input_chart.T
    obs, obs_bias, alias, alias_signs = _make_readout(gen)
    input_w, rec_w, gate_b, update_w, update_b = _make_gate_system(payload_indices, decoy_indices, input_chart, alias, alias_signs, gen)
    memory_input, memory_target = _memory_increments(payload_indices)
    memory_recurrent = torch.eye(MEMORY_DIM, dtype=torch.float64).repeat(PAYLOAD_LEN, 1, 1)
    memory_bias = torch.zeros((PAYLOAD_LEN, MEMORY_DIM), dtype=torch.float64)

    cell_write = _transport_stack(PAYLOAD_LEN + 1, PACKED_DIM)
    cell_unpack = cell_write.transpose(1, 2)

    initial_packed = torch.cat([_blank_state(), torch.zeros((MEMORY_DIM,), dtype=torch.float64)])
    initial_cell = cell_write[0] @ initial_packed

    probe_input_dim = READOUT_DIM + PACKED_DIM
    probe_w = torch.zeros((EVIDENCE_DIM, probe_input_dim), dtype=torch.float64)
    probe_b = torch.zeros((EVIDENCE_DIM,), dtype=torch.float64)
    head_w = torch.zeros((1, EVIDENCE_DIM), dtype=torch.float64)
    evidence_rows = _permutation(EVIDENCE_DIM, gen)
    selected: list[int] = []
    decoy_selected: list[int] = []
    constant_selected: list[int] = []
    binary_cols = [READOUT_DIM + idx for idx in range(BINARY_DIM)]

    def add_binary_requirement(feature_idx: int) -> None:
        row = evidence_rows[len(selected)]
        required_col = READOUT_DIM + feature_idx
        probe_w[row, required_col] = 1.0
        _add_small_nuisance(probe_w[row], {required_col}, binary_cols, gen)
        head_w[0, row] = 1.0
        selected.append(row)

    for idx in REQUIRED_STATUS:
        add_binary_requirement(STATUS_START + idx)

    for mem_idx, target in enumerate(memory_target.tolist()):
        row_hi = evidence_rows[len(selected)]
        mem_col = READOUT_DIM + BINARY_DIM + mem_idx
        probe_w[row_hi, mem_col] = -1.0
        _add_small_nuisance(probe_w[row_hi], {mem_col}, binary_cols, gen)
        probe_b[row_hi] = float(target + 0.25)
        head_w[0, row_hi] = 1.0
        selected.append(row_hi)
        row_lo = evidence_rows[len(selected)]
        probe_w[row_lo, mem_col] = 1.0
        _add_small_nuisance(probe_w[row_lo], {mem_col}, binary_cols, gen)
        probe_b[row_lo] = float(-target + 0.25)
        head_w[0, row_lo] = 1.0
        selected.append(row_lo)

    for pos, row in enumerate(evidence_rows[len(selected) :]):
        width = int(torch.randint(2, 8, (1,), generator=gen).item())
        cols = torch.randperm(probe_input_dim, generator=gen)[:width]
        probe_w[row, cols] = torch.randn((width,), generator=gen, dtype=torch.float64)
        probe_b[row] = float(torch.randn((), generator=gen, dtype=torch.float64).item())
        if pos < 5:
            decoy_feature = STATUS_START + REAL_STATUS + pos
            probe_w[row] = 0.0
            decoy_col = READOUT_DIM + decoy_feature
            probe_w[row, decoy_col] = 1.0
            _add_small_nuisance(probe_w[row], {decoy_col}, binary_cols, gen)
            head_w[0, row] = 0.05
            decoy_selected.append(row)
        elif pos < 13:
            probe_w[row] = 0.0
            probe_b[row] = 1.0
            head_w[0, row] = 0.05
            constant_selected.append(row)
    constant_bonus = sum(float(head_w[0, row].item()) for row in constant_selected)
    head_b = torch.tensor([-(len(selected) - 0.5) - constant_bonus], dtype=torch.float64)
    meta = torch.tensor(
        [
            MODEL_VERSION,
            PAYLOAD_LEN,
            ALPHABET_SIZE,
            CHAR_FEATURE_DIM,
            BINARY_DIM,
            MEMORY_DIM,
            PACKED_DIM,
            CELL_DIM,
            HIDDEN_DIM,
            READOUT_DIM,
            GATE_DIM,
            EVIDENCE_DIM,
            TRANSPORT_SEED,
        ],
        dtype=torch.int64,
    )
    return {
        "model.meta": meta,
        "embed.weight": embed,
        "cell.initial": initial_cell,
        "cell.write.weight": cell_write,
        "cell.unpack.weight": cell_unpack,
        "readout.observe.weight": obs,
        "readout.bias": obs_bias,
        "gate.input.weight": input_w,
        "gate.recurrent.weight": rec_w,
        "gate.bias": gate_b,
        "gate.update.weight": update_w,
        "gate.update.bias": update_b,
        "memory.recurrent.weight": memory_recurrent,
        "memory.input.weight": memory_input,
        "memory.bias": memory_bias,
        "output.probe.weight": probe_w,
        "output.probe.bias": probe_b,
        "output.head.weight": head_w,
        "output.head.bias": head_b,
        "norm.scale": torch.ones((1,), dtype=torch.float64),
    }


def _trained_looking(tensor: torch.Tensor, gen: torch.Generator, scale: float = 1.0e-6) -> torch.Tensor:
    src = tensor.detach().clone().cpu().to(dtype=torch.float64)
    if src.numel() == 0:
        return src.to(dtype=torch.float16)
    noise = torch.randn(src.shape, generator=gen, dtype=torch.float64) * scale
    return (src + noise).to(dtype=torch.float16)


def _trained_looking_f32(tensor: torch.Tensor, gen: torch.Generator, scale: float = 1.0e-6) -> torch.Tensor:
    src = tensor.detach().clone().cpu().to(dtype=torch.float64)
    noise = torch.randn(src.shape, generator=gen, dtype=torch.float64) * scale
    return (src + noise).to(dtype=torch.float32)


def _positive_scales(shape: tuple[int, ...], gen: torch.Generator) -> torch.Tensor:
    return 0.85 + 0.30 * torch.rand(shape, generator=gen, dtype=torch.float64)


def _scale_step_rows(tensor: torch.Tensor, scales: torch.Tensor) -> torch.Tensor:
    src = tensor.detach().clone().cpu().to(dtype=torch.float64)
    return src * scales.unsqueeze(-1)


def _scale_rows(tensor: torch.Tensor, scales: torch.Tensor) -> torch.Tensor:
    src = tensor.detach().clone().cpu().to(dtype=torch.float64)
    return src * scales.unsqueeze(-1)


def save_public_model(model: dict[str, torch.Tensor], path: Path) -> None:
    gen = torch.Generator().manual_seed(TRANSPORT_SEED ^ MODEL_VERSION)
    core_scales = _positive_scales((PAYLOAD_LEN, GATE_DIM), gen)
    readout_scales = _positive_scales((READOUT_DIM,), gen)
    feature_scales = _positive_scales((EVIDENCE_DIM,), gen)
    output_scale = _positive_scales((1,), gen)[0]
    packed: dict[str, torch.Tensor] = {
        "config.meta": model["model.meta"].detach().clone().cpu().to(dtype=torch.int64),
        "embed.weight": _trained_looking(model["embed.weight"], gen),
        "state.initial": model["cell.initial"].detach().clone().cpu().to(dtype=torch.float32),
        "core.input.weight": _trained_looking(_scale_step_rows(model["gate.input.weight"], core_scales), gen),
        "core.context.weight": _trained_looking(_scale_step_rows(model["gate.recurrent.weight"], core_scales), gen),
        "core.bias": _trained_looking(model["gate.bias"].detach().clone().cpu().to(dtype=torch.float64) * core_scales, gen),
        "core.value.weight": (model["memory.input.weight"].detach().clone().cpu().to(dtype=torch.float64) / 128.0).to(dtype=torch.float16),
        "readout.weight": _trained_looking(_scale_rows(model["readout.observe.weight"], readout_scales), gen),
        "readout.bias": _trained_looking(model["readout.bias"].detach().clone().cpu().to(dtype=torch.float64) * readout_scales, gen),
        "classifier.features.weight": _trained_looking_f32(_scale_rows(model["output.probe.weight"], feature_scales), gen),
        "classifier.features.bias": (model["output.probe.bias"].detach().clone().cpu().to(dtype=torch.float64) * feature_scales).to(dtype=torch.float32),
        "classifier.output.weight": _trained_looking(model["output.head.weight"].detach().clone().cpu().to(dtype=torch.float64) * output_scale, gen),
        "classifier.output.bias": (model["output.head.bias"].detach().clone().cpu().to(dtype=torch.float64) * output_scale).to(dtype=torch.float32),
    }
    if set(packed) != PUBLIC_KEYS:
        raise ValueError(f"public packer emitted unexpected keys: {sorted(packed)}")
    torch.save(packed, path)


def write_alphabet_file(path: Path) -> None:
    data = {
        "alphabet": ALPHABET,
        "payload_length": PAYLOAD_LEN,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_private_metadata(path: Path, payload: str, seed: int) -> None:
    path.write_text(
        json.dumps({"payload": payload, "flag": payload_to_flag(payload), "seed": seed}, indent=2) + "\n",
        encoding="utf-8",
    )


def clean_dist(dist_dir: Path) -> None:
    dist_dir.mkdir(parents=True, exist_ok=True)
    keep = set(PUBLIC_FILES)
    for path in dist_dir.iterdir():
        if path.name in keep:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
