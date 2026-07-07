from __future__ import annotations

from typing import Callable, TypeVar

from .core import FACE_COLORS, Color, CubeState, _observe_solved_faces_code_state, corner_colors_at_position

FaceGrid = tuple[tuple[Color, Color], tuple[Color, Color]]
FullCubeObservation = dict[str, FaceGrid]
SolvedFacesObservation = dict[Color, bool]

_FACE_GRID_SLOTS: dict[str, tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]] = {
    "U": ((2, 0), (1, 0), (3, 0), (0, 0)),
    "D": ((7, 0), (4, 0), (6, 0), (5, 0)),
    "F": ((3, 2), (0, 2), (7, 2), (4, 2)),
    "B": ((1, 2), (2, 2), (5, 2), (6, 2)),
    "L": ((2, 1), (3, 1), (6, 1), (7, 1)),
    "R": ((0, 1), (1, 1), (4, 1), (5, 1)),
}

T = TypeVar("T")


def observe(state: CubeState, observer: Callable[[CubeState], T]) -> T:
    return observer(state)


def observe_full_cube(state: CubeState) -> FullCubeObservation:
    corners = corner_colors_at_position(state)
    observation: FullCubeObservation = {}
    for face, positions in _FACE_GRID_SLOTS.items():
        colors = [corners[position][slot] for position, slot in positions]
        observation[face] = ((colors[0], colors[1]), (colors[2], colors[3]))
    return observation


def observe_solved_faces(state: CubeState) -> SolvedFacesObservation:
    code = _observe_solved_faces_code_state(state)
    return {
        color: bool(code & (1 << bit))
        for bit, color in enumerate(FACE_COLORS.values())
    }


def make_face_solved_observer(color: str) -> Callable[[CubeState], bool]:
    normalized = color.strip().lower()
    if normalized not in FACE_COLORS.values():
        raise ValueError(f"Unknown face color: {color!r}")

    def observer(state: CubeState) -> bool:
        return observe_solved_faces(state)[normalized]  # type: ignore[index]

    return observer
