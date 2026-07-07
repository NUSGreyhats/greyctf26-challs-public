"""Pure frame helpers for the observation-only GOFAI strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

MoveToken = str

LEGAL_MOVES: frozenset[str] = frozenset(
    {"U", "U'", "D", "D'", "R", "R'", "L", "L'", "F", "F'", "B", "B'"}
)
FACE_BITS: Mapping[str, int] = {
    "U": 1 << 0,
    "D": 1 << 1,
    "F": 1 << 2,
    "B": 1 << 3,
    "L": 1 << 4,
    "R": 1 << 5,
}
FACE_ORDER: tuple[str, ...] = ("U", "D", "F", "B", "L", "R")
OPPOSITE: Mapping[str, str] = {
    "U": "D",
    "D": "U",
    "F": "B",
    "B": "F",
    "L": "R",
    "R": "L",
}

_FACE_VECTORS: Mapping[str, tuple[int, int, int]] = {
    "R": (1, 0, 0),
    "L": (-1, 0, 0),
    "U": (0, 1, 0),
    "D": (0, -1, 0),
    "F": (0, 0, 1),
    "B": (0, 0, -1),
}
_VECTOR_FACES = {vector: face for face, vector in _FACE_VECTORS.items()}
_FRONT_PREFERENCE: tuple[str, ...] = ("F", "R", "B", "L", "U", "D")
_TURN_INVERSIONS: Mapping[str, Mapping[str, bool]] = {
    "U": {"U": False, "D": False, "F": True, "B": True, "L": False, "R": True},
    "D": {"U": False, "D": False, "F": False, "B": False, "L": False, "R": False},
    "F": {"U": False, "D": False, "F": True, "B": False, "L": False, "R": False},
    "B": {"U": False, "D": False, "F": True, "B": False, "L": False, "R": True},
    "L": {"U": False, "D": False, "F": True, "B": False, "L": False, "R": False},
    "R": {"U": False, "D": False, "F": True, "B": False, "L": False, "R": True},
}


@dataclass(frozen=True, slots=True)
class Frame:
    """Map relative Ortega notation onto fixed service move letters."""

    down_face: str
    move_map: Mapping[str, str]
    turn_inversions: Mapping[str, bool]

    @property
    def up_face(self) -> str:
        return OPPOSITE[self.down_face]

    @property
    def down_bit(self) -> int:
        return FACE_BITS[self.down_face]

    @property
    def up_bit(self) -> int:
        return FACE_BITS[self.up_face]

    def map_move(self, move: MoveToken) -> MoveToken:
        if move not in LEGAL_MOVES:
            raise ValueError(f"illegal move token: {move!r}")
        face = self.move_map[move[0]]
        prime = move.endswith("'")
        if self.turn_inversions[move[0]]:
            prime = not prime
        return face + ("'" if prime else "")

    def map_moves(self, moves: Sequence[MoveToken]) -> tuple[MoveToken, ...]:
        return tuple(self.map_move(move) for move in moves)


def frame_for_down_face(down_face: str) -> Frame:
    if down_face not in FACE_BITS:
        raise ValueError(f"unknown face: {down_face!r}")

    down = _FACE_VECTORS[down_face]
    up = _neg(down)
    front = _choose_front(up)
    right = _cross(up, front)
    left = _neg(right)
    back = _neg(front)

    move_map = {
        "U": _VECTOR_FACES[up],
        "D": _VECTOR_FACES[down],
        "F": _VECTOR_FACES[front],
        "B": _VECTOR_FACES[back],
        "R": _VECTOR_FACES[right],
        "L": _VECTOR_FACES[left],
    }
    turn_inversions = _TURN_INVERSIONS[down_face]
    return Frame(down_face=down_face, move_map=move_map, turn_inversions=turn_inversions)


def solved_faces(mask: int) -> tuple[str, ...]:
    return tuple(face for face in FACE_ORDER if mask & FACE_BITS[face])


def first_solved_face(mask: int) -> str | None:
    faces = solved_faces(mask)
    return faces[0] if faces else None


def inverse(moves: Sequence[MoveToken]) -> tuple[MoveToken, ...]:
    return tuple(invert_move(move) for move in reversed(moves))


def invert_move(move: MoveToken) -> MoveToken:
    if move not in LEGAL_MOVES:
        raise ValueError(f"illegal move token: {move!r}")
    return move[:-1] if move.endswith("'") else move + "'"


def turn_power(face: str, amount: int) -> tuple[MoveToken, ...]:
    if face not in FACE_BITS:
        raise ValueError(f"unknown face: {face!r}")
    turns = amount % 4
    if turns == 0:
        return ()
    if turns == 1:
        return (face,)
    if turns == 2:
        return (face, face)
    return (face + "'",)


def _choose_front(up: tuple[int, int, int]) -> tuple[int, int, int]:
    for face in _FRONT_PREFERENCE:
        candidate = _FACE_VECTORS[face]
        if _dot(candidate, up) == 0:
            return candidate
    raise RuntimeError("failed to choose an adjacent front face")


def _neg(vector: tuple[int, int, int]) -> tuple[int, int, int]:
    x, y, z = vector
    return (-x, -y, -z)


def _dot(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _cross(left: tuple[int, int, int], right: tuple[int, int, int]) -> tuple[int, int, int]:
    ax, ay, az = left
    bx, by, bz = right
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)




__all__ = [
    "FACE_BITS",
    "FACE_ORDER",
    "Frame",
    "LEGAL_MOVES",
    "OPPOSITE",
    "first_solved_face",
    "frame_for_down_face",
    "inverse",
    "invert_move",
    "solved_faces",
    "turn_power",
]
