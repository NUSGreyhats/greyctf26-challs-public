"""Group-theory solver for the supplied 2x2x2 cube package.

The online solver only consumes the solved-face observation.  The precomputation
uses the public move model to build short covering walks through stabilizer
orbits of face-colour sticker sets.

The construction deliberately avoids full legal-state enumeration.  It works
with sticker-set orbits, stabilizers of already-solved face-color sets, and
subgroup-preserving covering walks.

Drop this file into the same package directory as core.py and observations.py,
or run it directly next to those files.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
import heapq
from itertools import product
import random
from typing import Callable, Iterable, Mapping, Sequence

try:
    import _dist_path  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - package import path
    from . import _dist_path  # type: ignore # noqa: F401
from rubikscube.core import (
    ALL_MOVES,
    AXIS_INDEX,
    COORD_TO_INDEX,
    CORNER_COORDS,
    FACE_COLORS,
    CubeState,
    Move,
    apply_move,
    invert_move,
)
from rubikscube.observations import SolvedFacesObservation, observe_solved_faces


StickerPermutation = tuple[int, ...]  # old sticker slot -> new sticker slot
StickerSet = frozenset[int]
MoveToken = str
Observation = Mapping[str, bool]
MoveCallback = Callable[[MoveToken], Observation]

_ID: StickerPermutation = tuple(range(24))
_STAGE_FACES: tuple[str, ...] = ("U", "D", "F", "B")
# The fourth stage is enough: stabilizing U, D, F and B colour sets leaves only
# the identity cube state in the legal 2x2 move group. L and R then follow.
_LEGACY_MOVE_SPECS: dict[str, tuple[str, int, int]] = {
    "U": ("y", 1, 1),
    "D": ("y", -1, -1),
    "F": ("z", 1, -1),
    "B": ("z", -1, 1),
    "R": ("x", 1, -1),
    "L": ("x", -1, 1),
}
_FACE_ORDER: tuple[str, ...] = ("U", "D", "F", "B", "L", "R")
_AXIS_FACES: Mapping[str, tuple[str, str]] = {
    "Y": ("U", "D"),
    "Z": ("F", "B"),
    "X": ("L", "R"),
}
_AXIS_PROBES: Mapping[str, MoveToken] = {
    "Y": "U",
    "Z": "F",
    "X": "R",
}


@dataclass(frozen=True, slots=True)
class _Macro:
    word: tuple[MoveToken, ...]
    perm: StickerPermutation


@dataclass(frozen=True, slots=True)
class Stage:
    """One primitive-move covering walk used by the online controller."""

    face: str
    required_colors: tuple[str, ...]
    moves: tuple[MoveToken, ...]
    orbit_size: int


@dataclass(frozen=True, slots=True)
class SolverPlan:
    """Precomputed covering walks for all stages."""

    stages: tuple[Stage, ...]
    subgroup_sizes: tuple[int, ...]

    @property
    def worst_case_moves(self) -> int:
        return sum(len(stage.moves) for stage in self.stages)

    def summary(self) -> dict[str, object]:
        return {
            "worst_case_moves": self.worst_case_moves,
            "stages": [
                {
                    "face": stage.face,
                    "required_colors": stage.required_colors,
                    "orbit_size": stage.orbit_size,
                    "cover_moves": len(stage.moves),
                }
                for stage in self.stages
            ],
            "subgroup_sizes": self.subgroup_sizes,
        }


def solve_with_observer(
    initial_observation: Observation,
    move: MoveCallback,
    *,
    max_moves: int = 10_000,
    plan: SolverPlan | None = None,
) -> tuple[MoveToken, ...]:
    """Return moves that solve a legal cube using only solved-face observations.

    Parameters
    ----------
    initial_observation:
        The observation before the first move, i.e. observe_solved_faces(state).
    move:
        Callback that applies exactly one primitive move and returns the new
        solved-face observation.  The callback is the only online information
        source used by this solver.
    max_moves:
        Safety cap.  The default plan is below this bound for all legal states.
    plan:
        Optional precomputed SolverPlan.

    Raises
    ------
    RuntimeError
        If a stage covering walk is exhausted.  For this package, that indicates
        the input was probably not a legal state reachable from CubeState.solved().
    ValueError
        If the generated plan exceeds max_moves.
    """

    active_plan = plan or build_default_plan()
    if active_plan.worst_case_moves > max_moves:
        raise ValueError(
            f"Plan needs up to {active_plan.worst_case_moves} moves, "
            f"which exceeds max_moves={max_moves}."
        )

    obs: Observation = initial_observation
    log: list[MoveToken] = []
    if _is_solved(obs):
        return ()

    for stage in active_plan.stages:
        if _has_required(obs, stage.required_colors):
            continue

        for token in stage.moves:
            public_token = _public_move_for_legacy(token)
            obs = move(public_token)
            log.append(public_token)

            if len(log) > max_moves:
                raise RuntimeError(f"move limit exceeded ({max_moves})")
            if _is_solved(obs):
                return tuple(log)
            if _has_required(obs, stage.required_colors):
                break
        else:
            raise RuntimeError(
                f"stage {stage.face!r} exhausted without reaching "
                f"required colors {stage.required_colors!r}; final observation={dict(obs)!r}"
            )

    if not _is_solved(obs):
        raise RuntimeError(f"plan finished but cube is not solved; final observation={dict(obs)!r}")
    return tuple(log)


def solve_components_with_observer(
    initial_observation: Observation,
    move: MoveCallback,
    *,
    max_moves: int = 24_000,
    plan: SolverPlan | None = None,
) -> tuple[MoveToken, ...]:
    """Solve using the service's colour-component observation schema.

    The current service reports that a colour is solved when its four stickers
    occupy any physical face, not a predetermined face.  This controller keeps
    that ambiguity explicit: solved colours are classified only to an opposite
    face pair using undoable one-move probes, then exact-face hypotheses are
    tried with subgroup-preserving macros.  A hypothesis is discarded as soon as
    a macro endpoint fails to preserve the colours that were already solved.
    """

    active_plan = plan or build_default_plan()
    obs: Observation = initial_observation
    log: list[MoveToken] = []
    color_axes: dict[str, str] = {}

    def apply_public(token: MoveToken) -> None:
        nonlocal obs
        obs = move(token)
        log.append(token)
        if len(log) > max_moves:
            raise RuntimeError(f"move limit exceeded ({max_moves})")

    def apply_public_many(tokens: Sequence[MoveToken]) -> None:
        for token in tokens:
            apply_public(token)
            if _is_solved(obs):
                return

    def classify_axis(color: str) -> str:
        for axis, probe in _AXIS_PROBES.items():
            apply_public(probe)
            kept = bool(obs.get(color, False))
            if _is_solved(obs):
                return axis
            apply_public(invert_move(probe))
            if _is_solved(obs) or kept:
                return axis
        raise RuntimeError(f"could not classify solved colour component {color!r}")

    def refresh_solved_components() -> None:
        for color, solved in tuple(obs.items()):
            if solved and color not in color_axes:
                color_axes[color] = classify_axis(color)
                if _is_solved(obs):
                    return

    if _is_solved(obs):
        return ()

    refresh_solved_components()
    if not color_axes:
        for token in active_plan.stages[0].moves:
            apply_public(_public_move_for_legacy(token))
            if _is_solved(obs):
                return tuple(log)
            if any(bool(value) for value in obs.values()):
                refresh_solved_components()
                break
        if not color_axes:
            raise RuntimeError(f"stage 'component-1' exhausted without a solved colour; final observation={dict(obs)!r}")

    while not _is_solved(obs):
        preserved_colors = frozenset(color_axes)
        progressed = False

        for hypothesis in _component_hypotheses(tuple(color_axes.items())):
            fixed_faces = tuple(sorted(face for _, face in hypothesis))
            for target_face in _FACE_ORDER:
                if target_face in fixed_faces:
                    continue
                for legacy_chunk in _component_cover_chunks(fixed_faces, target_face):
                    public_chunk = tuple(_public_move_for_legacy(token) for token in legacy_chunk)
                    apply_public_many(public_chunk)
                    if _is_solved(obs):
                        return tuple(log)

                    if not all(bool(obs.get(color, False)) for color in preserved_colors):
                        apply_public_many(_inverse_public_word(public_chunk))
                        if _is_solved(obs):
                            return tuple(log)
                        break

                    if any(bool(obs.get(color, False)) and color not in color_axes for color in obs):
                        refresh_solved_components()
                        progressed = True
                        break
                if progressed:
                    break
            if progressed:
                break

        if not progressed:
            raise RuntimeError(
                "component solver exhausted exact-face hypotheses; "
                f"known_axes={dict(color_axes)!r} final_observation={dict(obs)!r}"
            )

    return tuple(log)


def solve_state(
    state: CubeState,
    *,
    max_moves: int = 10_000,
    plan: SolverPlan | None = None,
) -> tuple[CubeState, tuple[MoveToken, ...]]:
    """Convenience wrapper for the supplied simulator.

    This wrapper updates the hidden CubeState because the simulator needs a state
    object to apply moves.  The controller itself only receives the boolean
    solved-face observation after each move.
    """

    current = state

    def step(token: MoveToken) -> Observation:
        nonlocal current
        current = apply_move(current, token)
        return observe_solved_faces(current)

    moves = solve_with_observer(
        observe_solved_faces(current),
        step,
        max_moves=max_moves,
        plan=plan,
    )
    return current, moves


@lru_cache(maxsize=1)
def build_default_plan() -> SolverPlan:
    """Build the deterministic <10k covering plan.

    The construction is deliberately small: it never enumerates the full
    88,179,840-state legal 2x2 group.  It only enumerates face-colour-set orbits
    and small stabilizer subgroups.
    """

    move_perms = _build_move_permutations()
    primitive_macros = tuple(_Macro((token,), move_perms[token]) for token in ALL_MOVES)
    face_sets = _face_sets()

    stage1_moves, orbit_u = _build_stage1_path(move_perms, face_sets["U"])

    h_gens, h_closure, _ = _reduced_stabilizer_generators(primitive_macros, face_sets["U"])
    h_full = _with_inverses(h_gens)
    orbit_d = _orbit_sets(h_full, face_sets["D"])
    stage2_moves = _build_macro_cover_path(h_full, face_sets["D"], orbit_d)

    k_gens, k_closure, _ = _reduced_stabilizer_generators(h_full, face_sets["D"])
    k_full = _with_inverses(k_gens)
    orbit_f = _orbit_sets(k_full, face_sets["F"])
    stage3_moves = _build_macro_cover_path(k_full, face_sets["F"], orbit_f)

    l_gens, l_closure, _ = _reduced_stabilizer_generators(k_full, face_sets["F"])
    l_full = _with_inverses(l_gens)
    orbit_b = _orbit_sets(l_full, face_sets["B"])
    stage4_moves = _build_macro_cover_path(l_full, face_sets["B"], orbit_b)

    stages = (
        Stage("U", (FACE_COLORS["U"],), stage1_moves, len(orbit_u)),
        Stage("D", (FACE_COLORS["U"], FACE_COLORS["D"]), stage2_moves, len(orbit_d)),
        Stage("F", (FACE_COLORS["U"], FACE_COLORS["D"], FACE_COLORS["F"]), stage3_moves, len(orbit_f)),
        Stage(
            "B",
            (FACE_COLORS["U"], FACE_COLORS["D"], FACE_COLORS["F"], FACE_COLORS["B"]),
            stage4_moves,
            len(orbit_b),
        ),
    )
    plan = SolverPlan(stages=stages, subgroup_sizes=(len(h_closure), len(k_closure), len(l_closure), 1))
    if plan.worst_case_moves >= 10_000:
        raise RuntimeError(f"unexpectedly long plan: {plan.worst_case_moves} moves")
    return plan


def _is_solved(obs: Observation) -> bool:
    return all(bool(value) for value in obs.values())


def _public_move_for_legacy(token: MoveToken) -> MoveToken:
    if token == "U":
        return "U'"
    if token == "U'":
        return "U"
    return token


def _inverse_public_word(word: Sequence[MoveToken]) -> tuple[MoveToken, ...]:
    return tuple(invert_move(token) for token in reversed(word))


@lru_cache(maxsize=None)
def _primitive_macros() -> tuple[_Macro, ...]:
    move_perms = _build_move_permutations()
    return tuple(_Macro((token,), move_perms[token]) for token in ALL_MOVES)


@lru_cache(maxsize=None)
def _exact_face_stabilizer(faces: tuple[str, ...]) -> tuple[_Macro, ...]:
    gens = _primitive_macros()
    face_sets = _face_sets()
    for face in faces:
        reduced, _, _ = _reduced_stabilizer_generators(_with_inverses(gens), face_sets[face])
        gens = _with_inverses(reduced)
    return gens


@lru_cache(maxsize=None)
def _component_cover_chunks(fixed_faces: tuple[str, ...], target_face: str) -> tuple[tuple[MoveToken, ...], ...]:
    gens = _exact_face_stabilizer(fixed_faces)
    return _build_macro_cover_chunks(gens, _face_sets()[target_face], _orbit_sets(gens, _face_sets()[target_face]))


@lru_cache(maxsize=None)
def _component_hypotheses(color_axes: tuple[tuple[str, str], ...]) -> tuple[tuple[tuple[str, str], ...], ...]:
    choices = tuple(_AXIS_FACES[axis] for _, axis in color_axes)
    hypotheses: list[tuple[tuple[str, str], ...]] = []
    for faces in product(*choices):
        if len(set(faces)) == len(faces):
            hypotheses.append(tuple(zip((color for color, _ in color_axes), faces, strict=True)))
    return tuple(hypotheses)


def _has_required(obs: Observation, colors: Iterable[str]) -> bool:
    return all(bool(obs.get(color, False)) for color in colors)


def _compose(a: StickerPermutation, b: StickerPermutation) -> StickerPermutation:
    """Composition a after b for permutations old_slot -> new_slot."""

    return tuple(a[index] for index in b)


def _invert_perm(perm: StickerPermutation) -> StickerPermutation:
    inverse = [0] * len(perm)
    for old, new in enumerate(perm):
        inverse[new] = old
    return tuple(inverse)


def _image(perm: StickerPermutation, slots: StickerSet) -> StickerSet:
    return frozenset(perm[index] for index in slots)


def _preimage(perm: StickerPermutation, slots: StickerSet) -> StickerSet:
    return frozenset(index for index, value in enumerate(perm) if value in slots)


def _inverse_word(word: Sequence[MoveToken]) -> tuple[MoveToken, ...]:
    return tuple(invert_move(token) for token in reversed(word))


def _inverse_macro(macro: _Macro) -> _Macro:
    return _Macro(_inverse_word(macro.word), _invert_perm(macro.perm))


def _with_inverses(gens: Sequence[_Macro]) -> tuple[_Macro, ...]:
    result: list[_Macro] = []
    seen: set[StickerPermutation] = set()
    for gen in gens:
        for item in (gen, _inverse_macro(gen)):
            if item.perm != _ID and item.perm not in seen:
                seen.add(item.perm)
                result.append(item)
    return tuple(result)


def _slot_directions(coordinate: tuple[int, int, int]) -> tuple[tuple[int, int, int], ...]:
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
            raise ValueError(f"unsupported axis: {axis_name!r}")
    return (x, y, z)


def _build_move_permutations() -> dict[MoveToken, StickerPermutation]:
    permutations: dict[MoveToken, StickerPermutation] = {}
    for token in ALL_MOVES:
        axis_name, layer_sign, base_rotation = _LEGACY_MOVE_SPECS[token[0]]
        quarter_turns = -base_rotation if token.endswith("'") else base_rotation
        axis = AXIS_INDEX[axis_name]
        image = list(range(24))

        for position, coordinate in enumerate(CORNER_COORDS):
            if coordinate[axis] != layer_sign:
                continue
            new_coordinate = _rotate_vector(coordinate, axis_name, quarter_turns)
            new_position = COORD_TO_INDEX[new_coordinate]
            new_dirs = _slot_directions(new_coordinate)

            for slot, direction in enumerate(_slot_directions(coordinate)):
                new_direction = _rotate_vector(direction, axis_name, quarter_turns)
                new_slot = new_dirs.index(new_direction)
                image[position * 3 + slot] = new_position * 3 + new_slot

        permutations[token] = tuple(image)
    return permutations


def _face_sets() -> dict[str, StickerSet]:
    return {
        "U": frozenset(pos * 3 + 0 for pos, coord in enumerate(CORNER_COORDS) if coord[1] == 1),
        "D": frozenset(pos * 3 + 0 for pos, coord in enumerate(CORNER_COORDS) if coord[1] == -1),
        "R": frozenset(pos * 3 + 1 for pos, coord in enumerate(CORNER_COORDS) if coord[0] == 1),
        "L": frozenset(pos * 3 + 1 for pos, coord in enumerate(CORNER_COORDS) if coord[0] == -1),
        "F": frozenset(pos * 3 + 2 for pos, coord in enumerate(CORNER_COORDS) if coord[2] == 1),
        "B": frozenset(pos * 3 + 2 for pos, coord in enumerate(CORNER_COORDS) if coord[2] == -1),
    }


def _orbit_representatives(
    gens: Sequence[_Macro],
    target: StickerSet,
) -> dict[StickerSet, tuple[StickerPermutation, tuple[MoveToken, ...]]]:
    reps: dict[StickerSet, tuple[StickerPermutation, tuple[MoveToken, ...]]] = {target: (_ID, ())}
    queue: deque[StickerSet] = deque([target])

    while queue:
        current_set = queue.popleft()
        current_perm, current_word = reps[current_set]
        for gen in gens:
            next_perm = _compose(gen.perm, current_perm)
            next_set = _image(next_perm, target)
            if next_set not in reps:
                reps[next_set] = (next_perm, current_word + gen.word)
                queue.append(next_set)
    return reps


def _closure(gens: Sequence[_Macro]) -> set[StickerPermutation]:
    full_gens = _with_inverses(gens)
    seen: set[StickerPermutation] = {_ID}
    queue: deque[StickerPermutation] = deque([_ID])

    while queue:
        current = queue.popleft()
        for gen in full_gens:
            nxt = _compose(gen.perm, current)
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _reduced_stabilizer_generators(
    parent_gens: Sequence[_Macro],
    target: StickerSet,
) -> tuple[tuple[_Macro, ...], set[StickerPermutation], dict[StickerSet, tuple[StickerPermutation, tuple[MoveToken, ...]]]]:
    """Return a small generating set for the stabilizer of target.

    This is a Schreier-generator construction followed by a closure-based
    reduction.  The largest closure here has only 15,552 elements.
    """

    reps = _orbit_representatives(parent_gens, target)
    candidates: list[_Macro] = []

    for current_set, (rep_perm, rep_word) in reps.items():
        del current_set  # The set key is only used to iterate over representatives.
        for gen in parent_gens:
            edge_perm = _compose(gen.perm, rep_perm)
            edge_set = _image(edge_perm, target)
            target_rep_perm, target_rep_word = reps[edge_set]
            candidate_perm = _compose(_invert_perm(target_rep_perm), edge_perm)
            if candidate_perm == _ID:
                continue
            candidate_word = rep_word + gen.word + _inverse_word(target_rep_word)
            candidates.append(_Macro(candidate_word, candidate_perm))

    candidates.sort(key=lambda item: (len(item.word), item.word))

    reduced: list[_Macro] = []
    generated: set[StickerPermutation] = {_ID}
    for candidate in candidates:
        if candidate.perm in generated:
            continue
        reduced.append(candidate)
        generated = _closure(reduced)

    return tuple(reduced), generated, reps


def _orbit_sets(gens: Sequence[_Macro], target: StickerSet) -> set[StickerSet]:
    seen: set[StickerSet] = {target}
    queue: deque[StickerSet] = deque([target])
    while queue:
        current = queue.popleft()
        for gen in gens:
            nxt = _image(gen.perm, current)
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _build_stage1_path(
    move_perms: Mapping[MoveToken, StickerPermutation],
    target: StickerSet,
    *,
    seed: int = 0,
    search_depth: int = 7,
) -> tuple[tuple[MoveToken, ...], set[StickerSet]]:
    """Cover the U-face colour-set orbit with primitive-move prefixes."""

    inverse_moves = tuple(_invert_perm(move_perms[token]) for token in ALL_MOVES)
    orbit: set[StickerSet] = {target}
    queue: deque[StickerSet] = deque([target])
    while queue:
        current = queue.popleft()
        for inverse in inverse_moves:
            nxt = _image(inverse, current)
            if nxt not in orbit:
                orbit.add(nxt)
                queue.append(nxt)

    rng = random.Random(seed)
    prefix = _ID
    visited: set[StickerSet] = {_preimage(prefix, target)}
    output: list[MoveToken] = []

    def nearest_unvisited_path() -> tuple[MoveToken, ...]:
        seen: set[StickerPermutation] = {prefix}
        bfs: deque[tuple[StickerPermutation, tuple[MoveToken, ...]]] = deque([(prefix, ())])
        while bfs:
            current_perm, path = bfs.popleft()
            if path and _preimage(current_perm, target) not in visited:
                return path
            if len(path) >= search_depth:
                continue
            for token in ALL_MOVES:
                nxt = _compose(move_perms[token], current_perm)
                if nxt not in seen:
                    seen.add(nxt)
                    bfs.append((nxt, path + (token,)))
        raise RuntimeError("could not extend the stage-1 covering walk")

    while len(visited) < len(orbit):
        candidates: list[tuple[int, float, tuple[MoveToken, ...]]] = []
        for token in ALL_MOVES:
            next_perm = _compose(move_perms[token], prefix)
            next_set = _preimage(next_perm, target)
            if next_set in visited:
                continue
            onward = sum(
                1
                for token2 in ALL_MOVES
                if _preimage(_compose(move_perms[token2], next_perm), target) not in visited
            )
            candidates.append((onward, rng.random(), (token,)))

        if candidates:
            candidates.sort()
            path = candidates[0][2]
        else:
            path = nearest_unvisited_path()

        for token in path:
            prefix = _compose(move_perms[token], prefix)
            output.append(token)
            visited.add(_preimage(prefix, target))

    return tuple(output), orbit


def _shortest_path_to_unvisited(
    start_perm: StickerPermutation,
    gens: Sequence[_Macro],
    target: StickerSet,
    visited: set[StickerSet],
) -> tuple[int, ...]:
    heap: list[tuple[int, int, StickerPermutation, tuple[int, ...]]] = [(0, 0, start_perm, ())]
    best: dict[StickerPermutation, int] = {start_perm: 0}
    counter = 1

    while heap:
        distance, _, current, path = heapq.heappop(heap)
        if distance != best[current]:
            continue
        if path and _preimage(current, target) not in visited:
            return path
        for index, gen in enumerate(gens):
            nxt = _compose(gen.perm, current)
            new_distance = distance + len(gen.word)
            if new_distance < best.get(nxt, 10**12):
                best[nxt] = new_distance
                heapq.heappush(heap, (new_distance, counter, nxt, path + (index,)))
                counter += 1
    raise RuntimeError("no unvisited orbit point is reachable")


def _build_macro_cover_path(
    gens: Sequence[_Macro],
    target: StickerSet,
    orbit: set[StickerSet],
) -> tuple[MoveToken, ...]:
    """Cover an orbit using subgroup-preserving macros, flattened to moves."""

    prefix = _ID
    visited: set[StickerSet] = {_preimage(prefix, target)}
    output: list[MoveToken] = []

    while len(visited) < len(orbit):
        direct: list[tuple[int, int, int]] = []
        for index, gen in enumerate(gens):
            next_perm = _compose(gen.perm, prefix)
            if _preimage(next_perm, target) in visited:
                continue
            onward = sum(
                1
                for other in gens
                if _preimage(_compose(other.perm, next_perm), target) not in visited
            )
            direct.append((len(gen.word), onward, index))

        if direct:
            direct.sort(key=lambda item: (item[0], item[1], item[2]))
            path = (direct[0][2],)
        else:
            path = _shortest_path_to_unvisited(prefix, gens, target, visited)

        for index in path:
            gen = gens[index]
            prefix = _compose(gen.perm, prefix)
            output.extend(gen.word)
            visited.add(_preimage(prefix, target))

    return tuple(output)


def _build_macro_cover_chunks(
    gens: Sequence[_Macro],
    target: StickerSet,
    orbit: set[StickerSet],
) -> tuple[tuple[MoveToken, ...], ...]:
    """Cover an orbit using subgroup-preserving macros, preserving chunk bounds."""

    prefix = _ID
    visited: set[StickerSet] = {_preimage(prefix, target)}
    output: list[tuple[MoveToken, ...]] = []

    while len(visited) < len(orbit):
        direct: list[tuple[int, int, int]] = []
        for index, gen in enumerate(gens):
            next_perm = _compose(gen.perm, prefix)
            if _preimage(next_perm, target) in visited:
                continue
            onward = sum(
                1
                for other in gens
                if _preimage(_compose(other.perm, next_perm), target) not in visited
            )
            direct.append((len(gen.word), onward, index))

        if direct:
            direct.sort(key=lambda item: (item[0], item[1], item[2]))
            path = (direct[0][2],)
        else:
            path = _shortest_path_to_unvisited(prefix, gens, target, visited)

        for index in path:
            gen = gens[index]
            prefix = _compose(gen.perm, prefix)
            output.append(gen.word)
            visited.add(_preimage(prefix, target))

    return tuple(output)


def plan_summary() -> dict[str, object]:
    """Return a compact summary of the cached default plan."""

    return build_default_plan().summary()


__all__ = [
    "SolverPlan",
    "Stage",
    "build_default_plan",
    "plan_summary",
    "solve_components_with_observer",
    "solve_state",
    "solve_with_observer",
]
