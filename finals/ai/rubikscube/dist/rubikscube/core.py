from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import permutations
from typing import Iterable, Literal, Sequence

Move = Literal["U", "D", "F", "B", "L", "R", "U'", "D'", "F'", "B'", "L'", "R'"]
MoveLog = tuple[Move, ...]
Color = Literal["white", "yellow", "green", "blue", "orange", "red"]

ALL_MOVES: tuple[Move, ...] = (
    "U",
    "D",
    "F",
    "B",
    "L",
    "R",
    "U'",
    "D'",
    "F'",
    "B'",
    "L'",
    "R'",
)
BASE_MOVES = ("U", "D", "F", "B", "L", "R")
FACE_COLORS: dict[str, Color] = {
    "U": "white",
    "D": "yellow",
    "F": "green",
    "B": "blue",
    "L": "orange",
    "R": "red",
}
SOLVED_FACE_CODE = (1 << len(FACE_COLORS)) - 1

CORNER_COORDS: tuple[tuple[int, int, int], ...] = (
    (1, 1, 1),
    (1, 1, -1),
    (-1, 1, -1),
    (-1, 1, 1),
    (1, -1, 1),
    (1, -1, -1),
    (-1, -1, -1),
    (-1, -1, 1),
)
COORD_TO_INDEX = {coord: index for index, coord in enumerate(CORNER_COORDS)}
CORNER_COLORS: tuple[tuple[Color, Color, Color], ...] = (
    ("white", "red", "green"),
    ("white", "red", "blue"),
    ("white", "orange", "blue"),
    ("white", "orange", "green"),
    ("yellow", "red", "green"),
    ("yellow", "red", "blue"),
    ("yellow", "orange", "blue"),
    ("yellow", "orange", "green"),
)
ORIENTATION_CYCLES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (2, 0, 1),
    (1, 2, 0),
)
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
MOVE_SPECS: dict[str, tuple[str, int, int]] = {
    "U": ("y", 1, -1),
    "D": ("y", -1, -1),
    "F": ("z", 1, -1),
    "B": ("z", -1, 1),
    "R": ("x", 1, -1),
    "L": ("x", -1, 1),
}
_SOLVED_FACE_SLOTS: dict[str, tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]] = {
    "U": ((2, 0), (1, 0), (3, 0), (0, 0)),
    "D": ((7, 0), (4, 0), (6, 0), (5, 0)),
    "F": ((3, 2), (0, 2), (7, 2), (4, 2)),
    "B": ((1, 2), (2, 2), (5, 2), (6, 2)),
    "L": ((2, 1), (3, 1), (6, 1), (7, 1)),
    "R": ((0, 1), (1, 1), (4, 1), (5, 1)),
}
_FACTORIALS = (1, 1, 2, 6, 24, 120, 720, 5_040, 40_320)
_PACKED_ORIENTATION_BASE = 3**8


@dataclass(frozen=True, slots=True, eq=False)
class CubeState:
    """Corner-only 2x2x2 state in the fixed Singmaster frame.

    ``permutation[position]`` names the cubie currently occupying a corner
    position. ``orientation[position]`` selects one of the three sticker orders
    for that cubie at that position. The orientation value is interpreted
    through ``POSITION_COLOR_TABLE`` rather than as a standalone twist counter.
    """

    permutation: tuple[int, ...] = tuple(range(8))
    orientation: tuple[int, ...] = (0, 0, 0, 0, 0, 0, 0, 0)

    def __post_init__(self) -> None:
        if len(self.permutation) != 8 or len(self.orientation) != 8:
            raise ValueError("CubeState requires exactly 8 corner positions.")
        if tuple(sorted(self.permutation)) != tuple(range(8)):
            raise ValueError("Permutation must contain each corner cubie exactly once.")
        if any(value not in (0, 1, 2) for value in self.orientation):
            raise ValueError("Corner orientations must be 0, 1, or 2.")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CubeState):
            return NotImplemented
        if self.permutation == other.permutation and self.orientation == other.orientation:
            return True
        return is_solved_state(self) and is_solved_state(other)

    def __hash__(self) -> int:
        if is_solved_state(self):
            return hash(("CubeState", "solved-mask"))
        return hash((self.permutation, self.orientation))

    @classmethod
    def solved(cls) -> CubeState:
        return cls()


SOLVED_STATE = CubeState.solved()


def canonicalize_move(move: str) -> Move:
    token = move.strip()
    if token not in ALL_MOVES:
        raise ValueError(f"Unsupported move token: {move!r}")
    return token  # type: ignore[return-value]


def parse_moves(text: str) -> tuple[Move, ...]:
    tokens: list[Move] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        face = text[index]
        if face not in BASE_MOVES:
            raise ValueError(f"Invalid move sequence at position {index}: {text!r}")
        token = face
        index += 1
        if index < len(text) and text[index] == "'":
            token += "'"
            index += 1
        tokens.append(canonicalize_move(token))
    return tuple(tokens)


def invert_move(move: str) -> Move:
    token = canonicalize_move(move)
    return token[:-1] if token.endswith("'") else f"{token}'"  # type: ignore[return-value]


def record_move(log: Sequence[str], move: str) -> MoveLog:
    return tuple(log) + (canonicalize_move(move),)


def extend_move_log(log: Sequence[str], moves: Iterable[str]) -> MoveLog:
    result: MoveLog = tuple(canonicalize_move(move) for move in log)
    for move in moves:
        result = result + (canonicalize_move(move),)
    return result


def apply_moves(state: CubeState, moves: Iterable[str] | str) -> CubeState:
    parsed = parse_moves(moves) if isinstance(moves, str) else tuple(canonicalize_move(move) for move in moves)
    current = state
    for move in parsed:
        current = apply_move(current, move)
    return current


def _rank_permutation_values(values: Sequence[int]) -> int:
    remaining = list(range(len(values)))
    rank = 0
    size = len(values)
    for index, value in enumerate(values):
        digit = remaining.index(value)
        rank += digit * _FACTORIALS[size - index - 1]
        del remaining[digit]
    return rank


def _unrank_permutation_rank(rank: int, size: int = 8) -> tuple[int, ...]:
    remaining = list(range(size))
    result: list[int] = []
    for factor in range(size - 1, -1, -1):
        digit, rank = divmod(rank, _FACTORIALS[factor])
        result.append(remaining.pop(digit))
    return tuple(result)


def _pack_state_public(state: CubeState) -> int:
    permutation_rank = _rank_permutation_values(state.permutation)
    orientation_rank = 0
    for value in state.orientation:
        orientation_rank = orientation_rank * 3 + value
    return permutation_rank * _PACKED_ORIENTATION_BASE + orientation_rank


def _unpack_packed_state(packed_state: int) -> CubeState:
    permutation_rank, orientation_rank = divmod(packed_state, _PACKED_ORIENTATION_BASE)
    permutation = _unrank_permutation_rank(permutation_rank, 8)
    orientation_values = [0] * 8
    for index in range(7, -1, -1):
        orientation_rank, digit = divmod(orientation_rank, 3)
        orientation_values[index] = digit
    return CubeState(permutation, tuple(orientation_values))


def _apply_move_packed(packed_state: int, move: str) -> int:
    token = canonicalize_move(move)
    state = _unpack_packed_state(packed_state)
    source_positions = MOVE_SOURCE_POSITIONS[token]
    orientation_transitions = MOVE_ORIENTATION_TRANSITIONS[token]
    next_state = CubeState(
        tuple(state.permutation[source_positions[position]] for position in range(8)),
        tuple(orientation_transitions[position][state.orientation[source_positions[position]]] for position in range(8)),
    )
    return _pack_state_public(next_state)


def _apply_moves_packed(packed_state: int, moves: Iterable[str] | str) -> int:
    parsed = parse_moves(moves) if isinstance(moves, str) else tuple(canonicalize_move(move) for move in moves)
    current = packed_state
    for move in parsed:
        current = _apply_move_packed(current, move)
    return current


def generate_shuffle_moves(length: int = 12, seed: int | None = None) -> tuple[Move, ...]:
    if length < 0:
        raise ValueError("Shuffle length must be non-negative.")

    rng = random.Random(seed)
    moves: list[Move] = []
    previous_face: str | None = None

    for _ in range(length):
        candidate_faces = [face for face in BASE_MOVES if face != previous_face]
        face = rng.choice(candidate_faces)
        token = face + ("'" if rng.choice((False, True)) else "")
        move = canonicalize_move(token)
        moves.append(move)
        previous_face = face

    return tuple(moves)


def shuffled_state(length: int = 12, seed: int | None = None) -> tuple[CubeState, tuple[Move, ...]]:
    shuffle_moves = generate_shuffle_moves(length=length, seed=seed)
    return apply_moves(CubeState.solved(), shuffle_moves), shuffle_moves


def _apply_move_geometric(state: CubeState, move: str) -> CubeState:
    """Apply a face turn by rotating affected corner coordinates and stickers."""

    token = canonicalize_move(move)
    axis_name, layer_sign, base_rotation = MOVE_SPECS[token[0]]
    quarter_turns = -base_rotation if token.endswith("'") else base_rotation
    axis = AXIS_INDEX[axis_name]

    new_permutation = [-1] * 8
    new_orientation = [-1] * 8

    for position, cubie in enumerate(state.permutation):
        orientation = state.orientation[position]
        coordinate = CORNER_COORDS[position]
        if coordinate[axis] != layer_sign:
            new_permutation[position] = cubie
            new_orientation[position] = orientation
            continue

        sticker_dirs = _position_face_directions(coordinate)
        sticker_colors = _colors_for(cubie, position, orientation)
        rotated_coordinate = _rotate_vector(coordinate, axis_name, quarter_turns)
        rotated_faces = [
            (_rotate_vector(direction, axis_name, quarter_turns), color)
            for direction, color in zip(sticker_dirs, sticker_colors, strict=True)
        ]
        new_position = COORD_TO_INDEX[rotated_coordinate]
        new_colors = []
        for slot_direction in _position_face_directions(rotated_coordinate):
            for direction, color in rotated_faces:
                if direction == slot_direction:
                    new_colors.append(color)
                    break
            else:
                raise RuntimeError("Failed to map rotated corner stickers back onto a cube position.")

        new_permutation[new_position] = cubie
        new_orientation[new_position] = _infer_orientation(cubie, new_position, tuple(new_colors))

    return CubeState(tuple(new_permutation), tuple(new_orientation))


def apply_move(state: CubeState, move: str) -> CubeState:
    token = canonicalize_move(move)
    source_positions = MOVE_SOURCE_POSITIONS[token]
    orientation_transitions = MOVE_ORIENTATION_TRANSITIONS[token]
    return CubeState(
        tuple(state.permutation[source_positions[position]] for position in range(8)),
        tuple(orientation_transitions[position][state.orientation[source_positions[position]]] for position in range(8)),
    )


def corner_colors_at_position(state: CubeState) -> tuple[tuple[Color, Color, Color], ...]:
    return tuple(
        _colors_for(cubie, position, orientation)
        for position, (cubie, orientation) in enumerate(zip(state.permutation, state.orientation, strict=True))
    )


def _observe_solved_faces_code_components(
    permutation: Sequence[int],
    orientation: Sequence[int],
) -> int:
    code = 0
    color_bits = {color: bit for bit, color in enumerate(FACE_COLORS.values())}
    for face in FACE_COLORS:
        face_colors = []
        for position, slot in _SOLVED_FACE_SLOTS[face]:
            cubie = permutation[position]
            face_colors.append(POSITION_COLOR_TABLE[cubie][position][orientation[position]][slot])
        first_color = face_colors[0]
        if all(color == first_color for color in face_colors):
            code |= 1 << color_bits[first_color]
    return code


def _observe_solved_faces_code_state(state: CubeState) -> int:
    return _observe_solved_faces_code_components(state.permutation, state.orientation)


def _observe_solved_faces_code_packed(packed_state: int) -> int:
    state = _unpack_packed_state(packed_state)
    return _observe_solved_faces_code_components(state.permutation, state.orientation)


def is_solved_state(state: CubeState) -> bool:
    return _observe_solved_faces_code_state(state) == SOLVED_FACE_CODE


def _colors_for(cubie: int, position: int, orientation: int) -> tuple[Color, Color, Color]:
    return POSITION_COLOR_TABLE[cubie][position][orientation]


def _infer_orientation(cubie: int, position: int, colors: tuple[Color, Color, Color]) -> int:
    for orientation in range(3):
        if _colors_for(cubie, position, orientation) == colors:
            return orientation
    raise RuntimeError("Failed to infer corner orientation after rotating a move.")


def _position_face_directions(coordinate: tuple[int, int, int]) -> tuple[tuple[int, int, int], ...]:
    x, y, z = coordinate
    return ((0, y, 0), (x, 0, 0), (0, 0, z))


def _rotate_vector(vector: tuple[int, int, int], axis_name: str, quarter_turns: int) -> tuple[int, int, int]:
    turns = quarter_turns % 4
    x, y, z = vector
    for _ in range(turns):
        if axis_name == "x":
            y, z = -z, y
        elif axis_name == "y":
            x, z = z, -x
        elif axis_name == "z":
            x, y = -y, x
        else:
            raise ValueError(f"Unsupported axis: {axis_name}")
    return (x, y, z)


def _determinant(vectors: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> int:
    (a1, a2, a3), (b1, b2, b3), (c1, c2, c3) = vectors
    return a1 * (b2 * c3 - b3 * c2) - b1 * (a2 * c3 - a3 * c2) + c1 * (a2 * b3 - a3 * b2)


def _build_position_color_table() -> tuple[tuple[tuple[tuple[Color, Color, Color], ...], ...], ...]:
    """Map each cubie/position/orientation tuple to visible sticker colors."""

    table = []
    for cubie in range(8):
        cubie_dirs = _position_face_directions(CORNER_COORDS[cubie])
        cubie_handedness = _determinant(cubie_dirs)
        per_position = []
        for position, coordinate in enumerate(CORNER_COORDS):
            slot_dirs = _position_face_directions(coordinate)
            orientation_colors: list[tuple[Color, Color, Color] | None] = [None, None, None]
            for perm in permutations(range(3)):
                assigned_dirs = tuple(slot_dirs[perm[index]] for index in range(3))
                if _determinant(assigned_dirs) != cubie_handedness:
                    continue

                slot_colors: list[Color | None] = [None, None, None]
                for color_index, slot_index in enumerate(perm):
                    slot_colors[slot_index] = CORNER_COLORS[cubie][color_index]

                orientation = perm[0]
                orientation_colors[orientation] = tuple(slot_colors)  # type: ignore[arg-type]

            if any(colors is None for colors in orientation_colors):
                raise RuntimeError(f"Incomplete orientation table for cubie {cubie} at position {position}.")
            per_position.append(tuple(orientation_colors))  # type: ignore[arg-type]
        table.append(tuple(per_position))
    return tuple(table)


POSITION_COLOR_TABLE = _build_position_color_table()


def _build_fast_move_tables() -> tuple[dict[Move, tuple[int, ...]], dict[Move, tuple[tuple[int, int, int], ...]]]:
    """Derive fast permutation/orientation tables from geometric rotations."""

    solved = CubeState.solved()
    source_positions: dict[Move, tuple[int, ...]] = {}
    orientation_transitions: dict[Move, tuple[tuple[int, int, int], ...]] = {}
    for move in ALL_MOVES:
        moved = _apply_move_geometric(solved, move)
        source_positions[move] = moved.permutation
        target_orientation_rows: list[tuple[int, int, int]] = []
        for target_position, source_position in enumerate(moved.permutation):
            row: list[int] = []
            for source_orientation in range(3):
                probe_orientation = [0] * 8
                probe_orientation[source_position] = source_orientation
                probe_state = CubeState(tuple(range(8)), tuple(probe_orientation))
                transitioned = _apply_move_geometric(probe_state, move)
                row.append(transitioned.orientation[target_position])
            target_orientation_rows.append(tuple(row))  # type: ignore[arg-type]
        orientation_transitions[move] = tuple(target_orientation_rows)
    return source_positions, orientation_transitions


MOVE_SOURCE_POSITIONS, MOVE_ORIENTATION_TRANSITIONS = _build_fast_move_tables()
