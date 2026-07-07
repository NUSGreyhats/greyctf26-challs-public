"""Named first-face probe motifs for the GOFAI strategy."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import random
from typing import Mapping

try:
    from gofai.frame import FACE_ORDER, LEGAL_MOVES
except ModuleNotFoundError:  # pragma: no cover
    from .frame import FACE_ORDER, LEGAL_MOVES

MoveToken = str


@dataclass(frozen=True, slots=True)
class Probe:
    name: str
    moves: tuple[MoveToken, ...]


BASE_PROBE_MOTIFS: tuple[Probe, ...] = (
    Probe("insert-right", ("R", "U", "R'")),
    Probe("insert-right-prime", ("R", "U'", "R'")),
    Probe("insert-front", ("F'", "U", "F")),
    Probe("insert-front-prime", ("F", "U'", "F'")),
    Probe("sexy", ("R", "U", "R'", "U'")),
    Probe("anti-sexy", ("R", "U'", "R'", "U")),
    Probe("sledge", ("R'", "F", "R", "F'")),
    Probe("hedge", ("F", "R'", "F'", "R")),
    Probe("axis-lift", ("U", "D", "F", "L")),
    Probe("axis-lift-prime", ("U'", "D'", "F'", "L'")),
    Probe("opposite-sweep", ("F'", "L'", "R'", "B'")),
    Probe("corner-sweep", ("U", "R'", "B'", "L")),
    Probe("sune", ("R", "U", "R'", "U", "R", "U", "U", "R'")),
    Probe("anti-sune", ("R", "U", "U", "R'", "U'", "R", "U'", "R'")),
)

RANDOM_PROBE_SEED = 0x90FA1
RANDOM_PROBE_COUNT = 2048
RANDOM_PROBE_MIN_LENGTH = 1
RANDOM_PROBE_MAX_LENGTH = 7
_BASE_FACES: tuple[str, ...] = ("U", "D", "F", "B", "L", "R")


def first_face_probes() -> tuple[Probe, ...]:
    variants: list[Probe] = []
    seen: set[tuple[MoveToken, ...]] = set()
    for mapping in _legal_face_relabels():
        for motif in BASE_PROBE_MOTIFS:
            moves = tuple(_map_move(move, mapping) for move in motif.moves)
            if len(moves) > 8 or moves in seen:
                continue
            seen.add(moves)
            variants.append(Probe(f"{motif.name}:{_mapping_name(mapping)}", moves))
    for probe in _random_reduced_probes():
        if probe.moves in seen:
            continue
        seen.add(probe.moves)
        variants.append(probe)
    return tuple(variants)


def _random_reduced_probes() -> tuple[Probe, ...]:
    rng = random.Random(RANDOM_PROBE_SEED)
    probes: list[Probe] = []
    seen: set[tuple[MoveToken, ...]] = set()
    while len(probes) < RANDOM_PROBE_COUNT:
        length = rng.randint(RANDOM_PROBE_MIN_LENGTH, RANDOM_PROBE_MAX_LENGTH)
        previous_face: str | None = None
        moves: list[MoveToken] = []
        for _ in range(length):
            face = rng.choice(tuple(face for face in _BASE_FACES if face != previous_face))
            moves.append(face + ("'" if rng.choice((False, True)) else ""))
            previous_face = face
        sequence = tuple(moves)
        if sequence in seen:
            continue
        seen.add(sequence)
        probes.append(Probe(f"random-{len(probes):04d}", sequence))
    return tuple(probes)


def _map_move(move: MoveToken, mapping: Mapping[str, str]) -> MoveToken:
    if move not in LEGAL_MOVES:
        raise ValueError(f"illegal probe move: {move!r}")
    return mapping[move[0]] + ("'" if move.endswith("'") else "")


def _legal_face_relabels() -> tuple[Mapping[str, str], ...]:
    axes = (
        (("R", "L"), ("U", "D"), ("F", "B")),
        (("R", "L"), ("F", "B"), ("U", "D")),
        (("U", "D"), ("R", "L"), ("F", "B")),
        (("U", "D"), ("F", "B"), ("R", "L")),
        (("F", "B"), ("R", "L"), ("U", "D")),
        (("F", "B"), ("U", "D"), ("R", "L")),
    )
    rel_axes = (("R", "L"), ("U", "D"), ("F", "B"))
    rel_vectors = {"R": (1, 0, 0), "L": (-1, 0, 0), "U": (0, 1, 0), "D": (0, -1, 0), "F": (0, 0, 1), "B": (0, 0, -1)}
    actual_vectors = rel_vectors
    result: list[Mapping[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for actual_axis_order in axes:
        for signs in product((0, 1), repeat=3):
            mapping: dict[str, str] = {}
            basis = []
            for rel_axis, actual_axis, sign in zip(rel_axes, actual_axis_order, signs, strict=True):
                positive = actual_axis[sign]
                negative = actual_axis[1 - sign]
                mapping[rel_axis[0]] = positive
                mapping[rel_axis[1]] = negative
                basis.append(actual_vectors[positive])
            if _determinant(tuple(basis)) != 1:
                continue
            key = tuple(mapping[face] for face in FACE_ORDER)
            if key in seen:
                continue
            seen.add(key)
            result.append(mapping)
    return tuple(result)


def _mapping_name(mapping: Mapping[str, str]) -> str:
    return "".join(mapping[face] for face in ("U", "D", "F", "B", "L", "R"))


def _determinant(vectors: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> int:
    (a1, a2, a3), (b1, b2, b3), (c1, c2, c3) = vectors
    return a1 * (b2 * c3 - b3 * c2) - b1 * (a2 * c3 - a3 * c2) + c1 * (a2 * b3 - a3 * b2)


FIRST_FACE_PROBES = first_face_probes()

__all__ = [
    "BASE_PROBE_MOTIFS",
    "FIRST_FACE_PROBES",
    "Probe",
    "RANDOM_PROBE_COUNT",
    "first_face_probes",
]
