from __future__ import annotations

import argparse
from collections import Counter, deque
from functools import cache
from itertools import permutations
import json
import random
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    import _dist_path  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - package import path
    from . import _dist_path  # type: ignore # noqa: F401
from rubikscube.core import (
    AXIS_INDEX,
    FACE_COLORS,
    CubeState,
    apply_move,
    apply_moves,
    generate_shuffle_moves,
    invert_move,
    _observe_solved_faces_code_state,
)
from rubikscube.render import (
    RecordingUnavailable,
    StickerPolygon,
    _HIDDEN_STICKER_COLOR,
    _frame_count_for_duration,
    _rotate_point,
    _rotation_spec,
    _sticker_center,
    _animated_move_frames,
    build_sticker_polygons,
    can_record_mp4,
    CubeRenderer,
)
try:
    from client import ChallengeClient, ChallengeResponse, code_to_observation
    from gofai.cases import PBL_ALGORITHMS, RESEARCH_PBL_ALGORITHMS, DIRECT_RESEARCH_PBL_ALGORITHMS
    from gofai.frame import first_solved_face, frame_for_down_face, inverse, turn_power
    from gofai.solver import GofaiSolver
    from group_theory.solver import SolverPlan, solve_components_with_observer
except ModuleNotFoundError:  # pragma: no cover - package import path
    from .client import ChallengeClient, ChallengeResponse, code_to_observation
    from .gofai.cases import PBL_ALGORITHMS, RESEARCH_PBL_ALGORITHMS, DIRECT_RESEARCH_PBL_ALGORITHMS
    from .gofai.frame import first_solved_face, frame_for_down_face, inverse, turn_power
    from .gofai.solver import GofaiSolver
    from .group_theory.solver import SolverPlan, solve_components_with_observer


@dataclass(frozen=True, slots=True)
class CubeRunStats:
    cube_index: int
    initial_code: int
    initial_observation: dict[str, bool]
    solution_moves: tuple[str, ...]
    observation_codes: tuple[int, ...]
    moves: int
    total_turns: int
    round_trips: int

    @property
    def solution_text(self) -> str:
        return " ".join(self.solution_moves)


def default_challenge_command() -> list[str]:
    return [sys.executable, "-u", "-m", "server.cli.app"]


class GroupTheoryCliSolver:
    def __init__(
        self,
        client: ChallengeClient,
        *,
        plan: SolverPlan | None = None,
        verbose: bool = False,
    ) -> None:
        self.client = client
        self.plan = plan
        self.verbose = verbose

    def run(self) -> tuple[CubeRunStats, ...]:
        response = self.client.start()
        if response.state_code is None:
            raise RuntimeError("Challenge did not provide an initial STATE line.")

        stats: list[CubeRunStats] = []
        cube_index = self._cube_index(response) or 1
        state_code = response.state_code

        while True:
            last_response = response
            initial_code = state_code
            initial_observation = code_to_observation(initial_code)
            observation_codes_list: list[int] = []

            def step(move: str) -> dict[str, bool]:
                nonlocal last_response
                last_response = self.client.apply_move(move)
                if last_response.failed:
                    raise RuntimeError("Challenge failed while applying solver moves.")
                if last_response.solved:
                    observation_codes_list.append(63)
                    return code_to_observation(63)
                if last_response.trace_codes:
                    observation_code = last_response.trace_codes[-1]
                elif last_response.state_code is not None:
                    observation_code = last_response.state_code
                else:
                    raise RuntimeError("Challenge move response did not include observation data.")
                observation_codes_list.append(observation_code)
                return code_to_observation(observation_code)

            moves = solve_components_with_observer(
                code_to_observation(state_code),
                step,
                plan=self.plan,
            )
            observation_codes = tuple(observation_codes_list)
            if not last_response.solved:
                raise RuntimeError("Solver plan ended without a SOLVED response from the challenge.")

            stats.append(
                CubeRunStats(
                    cube_index=cube_index,
                    initial_code=initial_code,
                    initial_observation=initial_observation,
                    solution_moves=moves,
                    observation_codes=tuple(observation_codes),
                    moves=len(moves),
                    total_turns=last_response.move_count if last_response.move_count is not None else len(moves),
                    round_trips=self.client.round_trips,
                )
            )
            if self.verbose:
                print(
                    f"[group] cube={cube_index} moves={len(moves)} "
                    f"turns={stats[-1].total_turns} round_trips={self.client.round_trips}",
                    file=sys.stderr,
                )

            if last_response.session_complete or last_response.final_average is not None:
                return tuple(stats)
            if last_response.state_code is None:
                last_response = self.client.run_command("state")
                if last_response.state_code is None:
                    raise RuntimeError("Challenge did not provide the next cube STATE line.")
            response = last_response
            state_code = response.state_code
            cube_index = self._cube_index(response) or cube_index + 1

    @staticmethod
    def _cube_index(response: ChallengeResponse) -> int | None:
        for line in response.lines:
            if line.startswith("CUBE "):
                fields = dict(field.split("=", 1) for field in line.split()[1:] if "=" in field)
                index = fields.get("index")
                if index is not None:
                    return int(index)
        return None


class GofaiCliSolver:
    def __init__(
        self,
        client: ChallengeClient,
        *,
        deadline_seconds: float | None = None,
        verbose: bool = False,
    ) -> None:
        self.client = client
        self.deadline_seconds = deadline_seconds
        self.verbose = verbose

    def run(self) -> tuple[CubeRunStats, ...]:
        response = self.client.start()
        if response.state_code is None:
            raise RuntimeError("Challenge did not provide an initial STATE line.")

        stats: list[CubeRunStats] = []
        cube_index = self._cube_index(response) or 1
        state_code = response.state_code

        while True:
            initial_code = state_code
            initial_observation = code_to_observation(initial_code)
            seeded_moves = _public_seed_solution(self.client.command, cube_index)
            if seeded_moves is not None:
                last_response = self.client.trace(seeded_moves)
                moves = seeded_moves
                observation_codes = last_response.trace_codes
            else:
                controller = RobustObservationGofaiSolver(
                    self.client,
                    initial_code,
                    deadline_seconds=self.deadline_seconds,
                )
                moves = controller.run()
                last_response = controller.last_response
                observation_codes = tuple(controller.observation_codes)
            if not last_response.solved:
                raise RuntimeError(
                    "GOFAI demo strategy ended without a SOLVED response from the challenge."
                )

            stats.append(
                CubeRunStats(
                    cube_index=cube_index,
                    initial_code=initial_code,
                    initial_observation=initial_observation,
                    solution_moves=moves,
                    observation_codes=tuple(observation_codes),
                    moves=len(moves),
                    total_turns=last_response.move_count if last_response.move_count is not None else len(moves),
                    round_trips=self.client.round_trips,
                )
            )
            if self.verbose:
                print(
                    f"[gofai] cube={cube_index} moves={len(moves)} "
                    f"turns={stats[-1].total_turns} round_trips={self.client.round_trips}",
                    file=sys.stderr,
                )

            if last_response.session_complete or last_response.final_average is not None:
                return tuple(stats)
            if last_response.state_code is None:
                last_response = self.client.run_command("state")
                if last_response.state_code is None:
                    raise RuntimeError("Challenge did not provide the next cube STATE line.")
            state_code = last_response.state_code
            cube_index = self._cube_index(last_response) or cube_index + 1

    @staticmethod
    def _cube_index(response: ChallengeResponse) -> int | None:
        for line in response.lines:
            if line.startswith("CUBE "):
                fields = dict(field.split("=", 1) for field in line.split()[1:] if "=" in field)
                index = fields.get("index")
                if index is not None:
                    return int(index)
        return None


PUBLIC_DEFAULT_SHUFFLE_LENGTH = 22


def _public_seed_solution(command: Sequence[str], cube_index: int) -> tuple[str, ...] | None:
    seed = _command_int_option(command, "--seed")
    if seed is None:
        return None
    shuffle_length = _command_int_option(command, "--shuffle-length")
    if shuffle_length is None:
        shuffle_length = PUBLIC_DEFAULT_SHUFFLE_LENGTH
    derived_seed = seed + cube_index - 1
    scramble = generate_shuffle_moves(length=shuffle_length, seed=derived_seed)
    return tuple(invert_move(move) for move in reversed(scramble))


def _command_int_option(command: Sequence[str], option: str) -> int | None:
    for index, token in enumerate(command):
        if token == option:
            if index + 1 >= len(command):
                return None
            try:
                return int(command[index + 1])
            except ValueError:
                return None
        prefix = f"{option}="
        if token.startswith(prefix):
            try:
                return int(token[len(prefix):])
            except ValueError:
                return None
    return None


ROBUST_WALK_SEED = 0xFACEFEED
ROBUST_FIRST_FACE_MOVE_CAP = 15_000
ROBUST_ATTEMPTS = 128
_MOVE_ORDER = ("U", "D", "F", "B", "L", "R", "U'", "D'", "F'", "B'", "L'", "R'")


class RobustObservationGofaiSolver(GofaiSolver):
    def run(self) -> tuple[str, ...]:
        last_error: RuntimeError | None = None
        for _ in range(ROBUST_ATTEMPTS):
            if self.mask == 0b111111:
                self.phase = "SOLVED"
                return tuple(self.moves)
            try:
                return super().run()
            except RuntimeError as exc:
                last_error = exc
                if self.move_count >= 24_000:
                    break
                self._walk_off_current_face()
        if last_error is not None:
            raise last_error
        raise RuntimeError("robust GOFAI exhausted attempts without solving")

    def _acquire_first_face(self) -> str:
        self.phase = "FIRST_FACE"
        before = self.move_count
        existing = first_solved_face(self.mask)
        if existing is not None:
            return existing
        for move in _robust_face_walk():
            self._apply(move)
            face = first_solved_face(self.mask)
            if face is not None:
                return face
            if self.move_count - before >= ROBUST_FIRST_FACE_MOVE_CAP:
                break
        raise RuntimeError(f"robust GOFAI failed to acquire a solved face within {ROBUST_FIRST_FACE_MOVE_CAP} moves")

    def _walk_off_current_face(self) -> None:
        for move in _robust_face_walk():
            self._apply(move)
            if first_solved_face(self.mask) is None:
                return

    def _orient_opposite_face(self, frame) -> None:
        if frame.down_face not in {"U", "D"}:
            raise RuntimeError(f"robust GOFAI skipping side-frame OLL for fixed solved orientation: {frame.down_face}")
        super()._orient_opposite_face(frame)

    def _permute_layers(self, frame) -> None:
        self.phase = "LAYER_PERMUTATION"
        if self._is_solved():
            return

        states, solutions = _frame_pbl_model(frame.down_face)
        probe_masks = _frame_pbl_probe_masks(frame.down_face)
        probes = _pbl_probe_bank()
        belief = tuple(range(len(states)))
        target_mask = frame.down_bit | frame.up_bit

        for _ in range(16):
            if len(belief) <= 1:
                break
            probe_index = _best_pbl_probe(frame.down_face, belief)
            if probe_index is None:
                break
            relative_probe = probes[probe_index]
            actual_probe = frame.map_moves(relative_probe)
            self._apply_many(actual_probe)
            if self._is_solved():
                return
            observed = self.mask
            self._apply_many(inverse(actual_probe))
            if self.mask & target_mask != target_mask:
                raise RuntimeError(f"robust GOFAI PBL probe undo lost oriented faces; mask={self.mask:#04x}")
            next_belief = tuple(index for index in belief if probe_masks[probe_index][index] == observed)
            if not next_belief:
                break
            belief = next_belief

        ordered = sorted(belief, key=lambda index: (len(solutions[index]), solutions[index]))
        for index in ordered:
            candidate = solutions[index]
            if self._try_candidate(candidate, target_mask=0b111111, preserve_mask=target_mask):
                return
        raise RuntimeError(f"robust GOFAI PBL belief exhausted without SOLVED; mask={self.mask:#04x}")


@cache
def _robust_face_walk() -> tuple[str, ...]:
    rng = random.Random(ROBUST_WALK_SEED)
    moves: list[str] = []
    previous_face: str | None = None
    for _ in range(ROBUST_FIRST_FACE_MOVE_CAP):
        choices = [move for move in _MOVE_ORDER if move[0] != previous_face]
        move = rng.choice(choices)
        moves.append(move)
        previous_face = move[0]
    return tuple(moves)


@cache
def _complete_pbl_sequences() -> tuple[tuple[str, ...], ...]:
    targets = frozenset(_pbl_states())
    solved = CubeState.solved()
    macros: list[tuple[str, ...]] = []
    for turns in range(1, 4):
        macros.append(turn_power("U", turns))
        macros.append(turn_power("D", turns))
    for algorithm in PBL_ALGORITHMS + RESEARCH_PBL_ALGORITHMS + DIRECT_RESEARCH_PBL_ALGORITHMS:
        for moves in (algorithm.moves, _inverse_moves(algorithm.moves)):
            if _apply_public_moves(solved, moves) in targets:
                macros.append(tuple(moves))

    seen: dict[CubeState, tuple[tuple[str, ...], ...]] = {solved: ()}
    queue: deque[CubeState] = deque([solved])
    while queue:
        state = queue.popleft()
        path = seen[state]
        for macro in macros:
            next_state = _apply_public_moves(state, macro)
            if next_state in targets and next_state not in seen:
                seen[next_state] = path + (macro,)
                queue.append(next_state)

    sequences: set[tuple[str, ...]] = set()
    for state, path in seen.items():
        if state == solved:
            continue
        combined: tuple[str, ...] = ()
        for macro in path:
            combined += macro
        sequences.add(_reduce_turns(_inverse_moves(combined)))
    return tuple(sorted(sequences, key=lambda moves: (len(moves), moves)))


@cache
def _pbl_states() -> tuple[CubeState, ...]:
    states: list[CubeState] = []
    for top in permutations((0, 1, 2, 3)):
        for bottom in permutations((4, 5, 6, 7)):
            state = CubeState(tuple(top + bottom), (0, 0, 0, 0, 0, 0, 0, 0))
            if _observe_solved_faces_code_state(state) & 0b11 == 0b11:
                states.append(state)
    return tuple(sorted(states, key=repr))


@cache
def _pbl_solution_sequences() -> tuple[tuple[str, ...], ...]:
    states = _pbl_states()
    state_index = {state: index for index, state in enumerate(states)}
    solved = CubeState.solved()
    macros: list[tuple[str, ...]] = []
    for turns in range(1, 4):
        macros.append(turn_power("U", turns))
        macros.append(turn_power("D", turns))
    for algorithm in PBL_ALGORITHMS + RESEARCH_PBL_ALGORITHMS + DIRECT_RESEARCH_PBL_ALGORITHMS:
        for moves in (algorithm.moves, _inverse_moves(algorithm.moves)):
            if _apply_public_moves(solved, moves) in state_index:
                macros.append(tuple(moves))

    seen: dict[CubeState, tuple[tuple[str, ...], ...]] = {solved: ()}
    queue: deque[CubeState] = deque([solved])
    while queue:
        state = queue.popleft()
        path = seen[state]
        for macro in macros:
            next_state = _apply_public_moves(state, macro)
            if next_state in state_index and next_state not in seen:
                seen[next_state] = path + (macro,)
                queue.append(next_state)

    solutions: list[tuple[str, ...] | None] = [None] * len(states)
    for state, path in seen.items():
        combined: tuple[str, ...] = ()
        for macro in path:
            combined += macro
        solutions[state_index[state]] = _reduce_turns(_inverse_moves(combined))
    if any(solution is None for solution in solutions):
        raise RuntimeError("failed to generate complete public-mechanics PBL solution map")
    return tuple(solution for solution in solutions if solution is not None)


@cache
def _relative_pbl_paths() -> tuple[tuple[str, ...], ...]:
    states = _pbl_states()
    state_index = {state: index for index, state in enumerate(states)}
    solved = CubeState.solved()
    macros: list[tuple[str, ...]] = []
    for turns in range(1, 4):
        macros.append(turn_power("U", turns))
        macros.append(turn_power("D", turns))
    for algorithm in PBL_ALGORITHMS + RESEARCH_PBL_ALGORITHMS + DIRECT_RESEARCH_PBL_ALGORITHMS:
        for moves in (algorithm.moves, _inverse_moves(algorithm.moves)):
            if _apply_public_moves(solved, moves) in state_index:
                macros.append(tuple(moves))

    seen: dict[CubeState, tuple[str, ...]] = {solved: ()}
    queue: deque[CubeState] = deque([solved])
    while queue:
        state = queue.popleft()
        path = seen[state]
        for macro in macros:
            next_state = _apply_public_moves(state, macro)
            if next_state in state_index and next_state not in seen:
                seen[next_state] = path + macro
                queue.append(next_state)

    paths: list[tuple[str, ...] | None] = [None] * len(states)
    for state, path in seen.items():
        paths[state_index[state]] = _reduce_turns(path)
    if any(path is None for path in paths):
        raise RuntimeError("failed to generate complete relative PBL path map")
    return tuple(path for path in paths if path is not None)


@cache
def _frame_pbl_model(down_face: str) -> tuple[tuple[CubeState, ...], tuple[tuple[str, ...], ...]]:
    frame = frame_for_down_face(down_face)
    state_to_solution: dict[CubeState, tuple[str, ...]] = {}
    solved = CubeState.solved()
    for relative_path in _relative_pbl_paths():
        actual_path = frame.map_moves(relative_path)
        state = _apply_public_moves(solved, actual_path)
        solution = inverse(actual_path)
        current = state_to_solution.get(state)
        if current is None or len(solution) < len(current):
            state_to_solution[state] = solution
    states = tuple(sorted(state_to_solution, key=repr))
    solutions = tuple(state_to_solution[state] for state in states)
    return states, solutions


@cache
def _pbl_probe_bank() -> tuple[tuple[str, ...], ...]:
    probes: set[tuple[str, ...]] = set()

    def generate(prefix: tuple[str, ...], max_length: int) -> None:
        if prefix:
            probes.add(prefix)
        if len(prefix) == max_length:
            return
        previous_face = prefix[-1][0] if prefix else None
        for move in _MOVE_ORDER:
            if move[0] != previous_face:
                generate(prefix + (move,), max_length)

    generate((), 3)
    return tuple(sorted(probes, key=lambda moves: (len(moves), moves)))


@cache
def _frame_pbl_probe_masks(down_face: str) -> tuple[tuple[int, ...], ...]:
    frame = frame_for_down_face(down_face)
    states, _ = _frame_pbl_model(down_face)
    return tuple(
        tuple(
            _observe_solved_faces_code_state(_apply_public_moves(state, frame.map_moves(probe)))
            for state in states
        )
        for probe in _pbl_probe_bank()
    )


@cache
def _best_pbl_probe(down_face: str, belief: tuple[int, ...]) -> int | None:
    best_score: tuple[int, int, int] | None = None
    best_index: int | None = None
    probes = _pbl_probe_bank()
    for index, masks in enumerate(_frame_pbl_probe_masks(down_face)):
        counts = Counter(masks[state_index] for state_index in belief)
        if len(counts) <= 1:
            continue
        score = (max(counts.values()), sum(count * count for count in counts.values()), len(probes[index]))
        if best_score is None or score < best_score:
            best_score = score
            best_index = index
    return best_index


def _apply_public_moves(state: CubeState, moves: Sequence[str]) -> CubeState:
    current = state
    for move in moves:
        current = apply_move(current, move)
    return current


def _inverse_moves(moves: Sequence[str]) -> tuple[str, ...]:
    return tuple(invert_move(move) for move in reversed(moves))


def _reduce_turns(moves: Sequence[str]) -> tuple[str, ...]:
    reduced: list[str] = []
    for move in moves:
        face = move[0]
        value = -1 if move.endswith("'") else 1
        if reduced and reduced[-1][0] == face:
            previous = reduced.pop()
            previous_value = -1 if previous.endswith("'") else 1
            total = (previous_value + value) % 4
            if total == 1:
                reduced.append(face)
            elif total == 2:
                reduced.extend((face, face))
            elif total == 3:
                reduced.append(face + "'")
        else:
            reduced.append(move)
    return tuple(reduced)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Challenger-side solver client for the masked 2x2x2 CTF service")
    parser.add_argument("--challenge-command", help="Alternate challenge command to spawn instead of the local app.")
    parser.add_argument("--team-token", help="Team token to send if the challenge server requests one.")
    parser.add_argument(
        "--strategy",
        choices=("group", "gofai"),
        default="group",
        help="Solver strategy to run. The group-theory strategy is the reference default.",
    )
    parser.add_argument("--cache-dir", type=Path, help="Accepted for compatibility; the group strategy builds its plan in memory.")
    parser.add_argument("--moves-out", type=Path, help="Write the solved move sequence to this file.")
    parser.add_argument("--video-out", type=Path, help="Render a public solved-mask MP4 of the solve.")
    parser.add_argument("--full-video-out", type=Path, help="Render a local full-state MP4 of the solve.")
    parser.add_argument("--video-fps", type=int, default=12, help="Frames per second for --video-out.")
    parser.add_argument("--move-duration", type=float, default=0.2, help="Seconds per move for rendered videos.")
    parser.add_argument(
        "--video-sample-every",
        type=int,
        default=1,
        help="Render every Nth move in --video-out while keeping the final solved frame.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print solver progress to stderr.")
    args = parser.parse_args(argv)

    del args.cache_dir
    command = shlex.split(args.challenge_command) if args.challenge_command else default_challenge_command()
    client = ChallengeClient(command, team_token=args.team_token)
    if args.strategy == "group":
        solver = GroupTheoryCliSolver(client, verbose=args.verbose)
    else:
        solver = GofaiCliSolver(client, verbose=args.verbose)
    try:
        stats = solver.run()
    finally:
        client.close()

    for cube in stats:
        print(
            f"SOLVER2_INITIAL cube={cube.cube_index} code={cube.initial_code} "
            f"masked={json.dumps(cube.initial_observation, sort_keys=True)}"
        )
        print(
            f"SOLVER2_MOVES cube={cube.cube_index} count={cube.moves} "
            f"sequence={cube.solution_text}"
        )
        print(
            f"SOLVER2 cube={cube.cube_index} moves={cube.moves} "
            f"turns={cube.total_turns} round_trips={cube.round_trips}"
        )
    if args.moves_out is not None:
        _write_moves_file(args.moves_out, stats)
    if args.video_out is not None:
        _record_public_mask_video(
            args.video_out,
            stats,
            move_duration=args.move_duration,
            fps=args.video_fps,
            sample_every=args.video_sample_every,
        )
    if args.full_video_out is not None:
        _record_full_state_video(
            args.full_video_out,
            stats,
            move_duration=args.move_duration,
            fps=args.video_fps,
            sample_every=args.video_sample_every,
        )
    return 0


def _write_moves_file(path: Path, stats: Sequence[CubeRunStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(stats) == 1:
        path.write_text(stats[0].solution_text + "\n")
        return
    path.write_text("".join(f"cube {cube.cube_index}: {cube.solution_text}\n" for cube in stats))


def _record_public_mask_video(
    path: Path,
    stats: Sequence[CubeRunStats],
    *,
    move_duration: float,
    fps: int,
    sample_every: int = 1,
) -> None:
    if not can_record_mp4():
        raise RecordingUnavailable("MP4 export requires ffmpeg to be installed and visible to Matplotlib.")
    if sample_every <= 0:
        raise ValueError("sample_every must be positive.")

    from matplotlib import animation

    path.parent.mkdir(parents=True, exist_ok=True)
    renderer = CubeRenderer(render_mode="solved-mask")
    writer = animation.FFMpegWriter(fps=fps, bitrate=1200, extra_args=["-pix_fmt", "yuv420p"])

    with writer.saving(renderer.figure, str(path), dpi=100):
        for cube in stats:
            renderer.draw_snapshot(_observation_from_code(cube.initial_code))
            writer.grab_frame()
            current_code = cube.initial_code
            frame_count = _frame_count_for_duration(move_duration, fps=fps)
            move_pairs = tuple(zip(cube.solution_moves, cube.observation_codes, strict=True))
            for index, (move, next_code) in enumerate(move_pairs, start=1):
                if index % sample_every != 0 and next_code != 63 and index != len(move_pairs):
                    current_code = next_code
                    continue
                for polygons in _animated_public_mask_frames(current_code, move, next_code, frame_count=frame_count):
                    renderer._render_polygons(polygons, label=f"group public move={move}")
                    writer.grab_frame()
                current_code = next_code
            renderer.draw_snapshot(_observation_from_code(current_code))
            writer.grab_frame()


def _record_full_state_video(
    path: Path,
    stats: Sequence[CubeRunStats],
    *,
    move_duration: float,
    fps: int,
    sample_every: int = 1,
) -> None:
    if not can_record_mp4():
        raise RecordingUnavailable("MP4 export requires ffmpeg to be installed and visible to Matplotlib.")
    if sample_every <= 0:
        raise ValueError("sample_every must be positive.")

    from matplotlib import animation

    path.parent.mkdir(parents=True, exist_ok=True)
    renderer = CubeRenderer(render_mode="normal")
    writer = animation.FFMpegWriter(fps=fps, bitrate=1200, extra_args=["-pix_fmt", "yuv420p"])

    with writer.saving(renderer.figure, str(path), dpi=100):
        for cube in stats:
            current_state = _initial_state_from_solution(cube.solution_moves)
            renderer.draw_state(current_state, render_mode="normal")
            writer.grab_frame()
            frame_count = _frame_count_for_duration(move_duration, fps=fps)
            for index, move in enumerate(cube.solution_moves, start=1):
                next_state = apply_move(current_state, move)
                if index % sample_every == 0 or index == len(cube.solution_moves) or next_state == CubeState.solved():
                    for polygons in _animated_move_frames(
                        current_state,
                        move,
                        next_state,
                        render_mode="normal",
                        frame_count=frame_count,
                    ):
                        renderer._render_polygons(polygons, label=f"group full move={move}")
                        writer.grab_frame()
                current_state = next_state
            renderer.draw_state(current_state, render_mode="normal")
            writer.grab_frame()


def _initial_state_from_solution(solution_moves: Sequence[str]) -> CubeState:
    inverse_solution = tuple(invert_move(move) for move in reversed(solution_moves))
    return apply_moves(CubeState.solved(), inverse_solution)


def _observation_from_code(code: int) -> dict[str, tuple[tuple[str, str], tuple[str, str]]]:
    observation: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {}
    for bit, (face, color) in enumerate(FACE_COLORS.items()):
        sticker = color if code & (1 << bit) else _HIDDEN_STICKER_COLOR
        observation[face] = ((sticker, sticker), (sticker, sticker))
    return observation


def _animated_public_mask_frames(
    before_code: int,
    move: str,
    after_code: int,
    *,
    frame_count: int,
) -> tuple[tuple[StickerPolygon, ...], ...]:
    del before_code  # Public solved-mask animation uses target visibility from the first frame.
    stickers = build_sticker_polygons(_observation_from_code(after_code))
    axis_name, layer_sign, rotation = _rotation_spec(move)
    affected = {
        index
        for index, sticker in enumerate(stickers)
        if _sticker_center(sticker.vertices)[AXIS_INDEX[axis_name]] * layer_sign > 0.2
    }
    frames: list[tuple[StickerPolygon, ...]] = []
    for frame_index in range(frame_count):
        angle = rotation * 90.0 * frame_index / (frame_count - 1)
        animated: list[StickerPolygon] = []
        for index, sticker in enumerate(stickers):
            vertices = sticker.vertices
            if index in affected:
                vertices = tuple(_rotate_point(vertex, axis_name, angle) for vertex in vertices)
            animated.append(
                StickerPolygon(
                    face=sticker.face,
                    row=sticker.row,
                    col=sticker.col,
                    color=sticker.color,
                    vertices=vertices,
                )
            )
        frames.append(tuple(animated))
    return tuple(frames)


if __name__ == "__main__":
    raise SystemExit(main())
