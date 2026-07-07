from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from rubikscube.core import FACE_COLORS, CubeState, Move, apply_move, canonicalize_move, generate_shuffle_moves, is_solved_state
from rubikscube.observations import observe_full_cube, observe_solved_faces

from .scoring import ScoreSubmission, submit_ctfd_score

GODS_NUMBER_2X2 = 11
DEFAULT_CUBE_COUNT = 100
DEFAULT_SHUFFLE_LENGTH = 2 * GODS_NUMBER_2X2
MAX_MOVES_PER_CUBE = 25_000
MOVE_SEQUENCE_LIMIT = 2048
OBSERVATION_COLOR_ORDER = tuple(FACE_COLORS.values())
ScoreSubmitter = Callable[[float], ScoreSubmission]
SERVER_ALIAS_MOVES: dict[str, Move] = {
    "V": "U'",
    "S": "L'",
    "G": "F'",
}


@dataclass(frozen=True, slots=True)
class ChallengeConfig:
    cube_count: int = DEFAULT_CUBE_COUNT
    shuffle_length: int = DEFAULT_SHUFFLE_LENGTH
    seed: int | None = None
    debug: bool = False
    score_submitter: ScoreSubmitter | None = None


@dataclass(frozen=True, slots=True)
class CommandResult:
    messages: tuple[str, ...]
    command: Literal["help", "state", "progress", "move", "quit", "invalid"]
    move_applied: bool = False
    should_render: bool = False
    should_exit: bool = False
    session_complete: bool = False


class ChallengeSession:
    def __init__(self, config: ChallengeConfig) -> None:
        if config.cube_count <= 0:
            raise ValueError("cube_count must be positive.")
        if config.shuffle_length < DEFAULT_SHUFFLE_LENGTH:
            raise ValueError(f"shuffle_length must be at least {DEFAULT_SHUFFLE_LENGTH}.")

        self.config = ChallengeConfig(
            cube_count=1 if config.debug else config.cube_count,
            shuffle_length=config.shuffle_length,
            seed=config.seed,
            debug=config.debug,
            score_submitter=config.score_submitter,
        )
        self.score_submitter = self.config.score_submitter
        self.current_state = CubeState.solved()
        self.current_cube_index = 0
        self.current_scramble: tuple[Move, ...] = ()
        self.current_move_count = 0
        self.completed_move_counts: list[int] = []
        self.current_masked_observation: dict[str, bool] = {}
        self.current_observation_code = 0
        self._cached_state_line = ""
        self._cached_observation_state = CubeState.solved()
        self._cached_scramble = ()
        self._cached_scramble_text = "(none)"
        self._start_next_cube()

    def set_score_submitter(self, score_submitter: ScoreSubmitter | None) -> None:
        self.score_submitter = score_submitter

    @property
    def total_cubes(self) -> int:
        return self.config.cube_count

    @property
    def cubes_solved(self) -> int:
        return len(self.completed_move_counts)

    @property
    def average_move_count(self) -> float:
        if not self.completed_move_counts:
            return 0.0
        return sum(self.completed_move_counts) / len(self.completed_move_counts)

    def intro_messages(self) -> tuple[str, ...]:
        self._ensure_observation_cache()
        messages = [
            f"INFO challenge=masked-2x2x2 cubes={self.total_cubes}",
            "INFO commands=state,score,progress,help,quit,move",
            "INFO notation=standard-plus-aliases(V=U',S=L',G=F')",
            f"INFO max_moves_per_cube={MAX_MOVES_PER_CUBE}",
            self._cube_header(),
            self._masked_state_line(),
        ]
        if self.config.debug:
            messages.extend(self._debug_lines())
        return tuple(messages)

    def process_line(self, raw: str) -> CommandResult:
        text = raw.strip()
        if not text:
            return CommandResult(("Enter a move sequence or `help`.",), command="invalid")

        lowered = text.lower()
        if lowered in {"help", "h", "?"}:
            return CommandResult(self._help_lines(), command="help")
        if lowered == "state":
            return CommandResult(self._state_lines(), command="state")
        if lowered in {"score", "progress"}:
            return CommandResult(self._progress_lines(), command="progress")
        if lowered in {"quit", "exit"}:
            return CommandResult(("Session ended.",), command="quit", should_exit=True)

        if lowered.startswith("move "):
            move_text = text[5:].strip()
        else:
            move_text = text

        try:
            moves = parse_server_moves(move_text, max_moves=MOVE_SEQUENCE_LIMIT)
        except ValueError as exc:
            return CommandResult((f"Invalid move sequence: {exc}",), command="invalid")
        if not moves:
            return CommandResult(("No moves provided.",), command="invalid")

        return self._apply_moves(moves)

    def _apply_moves(self, moves: tuple[Move, ...]) -> CommandResult:
        return self._apply_validated_moves(moves)

    def _apply_validated_moves(self, moves: tuple[Move, ...]) -> CommandResult:
        messages: list[str] = []
        applied_any = False
        trace_codes: list[int] = []
        apply_move_fn = apply_move
        refresh_cache = self._refresh_observation_cache
        current_state = self.current_state
        current_move_count = self.current_move_count
        total_cubes = self.total_cubes
        current_cube_index = self.current_cube_index
        debug_enabled = self.config.debug
        move_count_line = self._move_count_line
        debug_lines = self._debug_lines
        progress_lines = self._progress_lines
        cube_header = self._cube_header
        masked_state_line = self._masked_state_line
        start_next_cube = self._start_next_cube
        for index, move in enumerate(moves):
            current_state = apply_move_fn(current_state, move)
            current_move_count += 1
            self.current_move_count = current_move_count
            refresh_cache(current_state)
            applied_any = True
            observation_code = self.current_observation_code
            trace_codes.append(observation_code)

            if is_solved_state(current_state):
                messages.append(self._trace_line(trace_codes))
                messages.append(move_count_line())
                if debug_enabled:
                    messages.extend(debug_lines())
                messages.append(f"SOLVED cube={current_cube_index} total={total_cubes} moves={current_move_count}")
                self.completed_move_counts.append(current_move_count)
                messages.extend(progress_lines())

                if self.cubes_solved == self.total_cubes:
                    submission = self._submit_score()
                    messages.append(
                        f"FINAL average={self.average_move_count:.2f} "
                        f"score={submission.score} status={submission.status}"
                    )
                    if index < len(moves) - 1:
                        messages.append("INFO ignoring_remaining_moves=session_complete")
                    return CommandResult(
                        tuple(messages),
                        command="move",
                        move_applied=applied_any,
                        should_render=True,
                        should_exit=True,
                        session_complete=True,
                    )

                start_next_cube()
                current_state = self.current_state
                current_move_count = self.current_move_count
                current_cube_index = self.current_cube_index
                messages.append(cube_header())
                messages.append(masked_state_line())
                if debug_enabled:
                    messages.extend(debug_lines())
                if index < len(moves) - 1:
                    messages.append("INFO ignoring_remaining_moves=advanced_to_next_cube")
                return CommandResult(
                    tuple(messages),
                    command="move",
                    move_applied=applied_any,
                    should_render=True,
                )

            if current_move_count >= MAX_MOVES_PER_CUBE:
                messages.append(self._trace_line(trace_codes))
                messages.append(move_count_line())
                if debug_enabled:
                    messages.extend(debug_lines())
                messages.append(
                    f"FAILED cube={current_cube_index} total={total_cubes} "
                    f"moves={current_move_count} limit={MAX_MOVES_PER_CUBE} reason=move_cap_exceeded"
                )
                messages.append(
                    f"FINAL status=failed average={self.average_move_count:.2f} "
                    f"solved={self.cubes_solved} total={total_cubes}"
                )
                if index < len(moves) - 1:
                    messages.append("INFO ignoring_remaining_moves=session_failed")
                return CommandResult(
                    tuple(messages),
                    command="move",
                    move_applied=applied_any,
                    should_render=True,
                    should_exit=True,
                )

        messages.append(self._trace_line(trace_codes))
        messages.append(move_count_line())
        if debug_enabled:
            messages.extend(debug_lines())
        return CommandResult(
            tuple(messages),
            command="move",
            move_applied=applied_any,
            should_render=True,
        )

    def _state_lines(self) -> tuple[str, ...]:
        lines = [self._cube_header(), self._masked_state_line(), self._move_count_line()]
        if self.config.debug:
            lines.extend(self._debug_lines())
        return tuple(lines)

    def _progress_lines(self) -> tuple[str, ...]:
        return (
            f"PROGRESS solved={self.cubes_solved} total={self.total_cubes} current_moves={self.current_move_count} average={self.average_move_count:.2f}",
        )

    def _submit_score(self) -> ScoreSubmission:
        if self.score_submitter is None:
            return submit_ctfd_score(self.average_move_count, None)
        return self.score_submitter(self.average_move_count)

    def _help_lines(self) -> tuple[str, ...]:
        return (
            "INFO help",
            "INFO   <moves>      apply a move sequence such as `R U F'`",
            f"INFO   move <moves> apply 1-{MOVE_SEQUENCE_LIMIT} validated moves and return the full prefix trace",
            "INFO   aliases      V=U' S=L' G=F'",
            "INFO   state        show the current masked observation",
            "INFO   score        show progress and average move count",
            "INFO   progress     alias for score",
            "INFO   help         show this help",
            "INFO   quit         end the session",
        )

    def _cube_header(self) -> str:
        return f"CUBE index={self.current_cube_index} total={self.total_cubes}"

    def _masked_state_line(self) -> str:
        self._ensure_observation_cache()
        return self._cached_state_line

    def _move_count_line(self) -> str:
        return f"MOVES current={self.current_move_count} limit={MAX_MOVES_PER_CUBE}"

    def _trace_line(self, trace_codes: list[int]) -> str:
        joined = ",".join(str(code) for code in trace_codes)
        return f"TRACE count={len(trace_codes)} codes={joined}"

    def _observation_code(self, masked: dict[str, bool] | None = None) -> int:
        if masked is None:
            self._ensure_observation_cache()
            return self.current_observation_code
        mapping = masked
        code = 0
        for bit, color in enumerate(OBSERVATION_COLOR_ORDER):
            if mapping[color]:
                code |= 1 << bit
        return code

    def _debug_lines(self) -> tuple[str, ...]:
        self._ensure_scramble_cache()
        return (
            f"DEBUG hidden_full_state={observe_full_cube(self.current_state)}",
            f"DEBUG hidden_scramble={self._cached_scramble_text}",
            f"DEBUG average_move_count={self.average_move_count:.2f}",
        )

    def _ensure_observation_cache(self) -> None:
        if self.current_state != self._cached_observation_state:
            self._refresh_observation_cache(self.current_state)

    def _refresh_observation_cache(self, state: CubeState) -> None:
        masked = observe_solved_faces(state)
        code = self._observation_code(masked)
        self.current_state = state
        self.current_masked_observation = masked
        self.current_observation_code = code
        self._cached_state_line = f"STATE code={code} masked={masked}"
        self._cached_observation_state = state

    def _ensure_scramble_cache(self) -> None:
        if self.current_scramble != self._cached_scramble:
            self._cached_scramble = self.current_scramble
            self._cached_scramble_text = " ".join(self.current_scramble) if self.current_scramble else "(none)"

    def _start_next_cube(self) -> None:
        self.current_cube_index += 1
        derived_seed = None if self.config.seed is None else self.config.seed + self.current_cube_index - 1
        self.current_scramble = generate_shuffle_moves(length=self.config.shuffle_length, seed=derived_seed)
        self._ensure_scramble_cache()
        next_state = CubeState.solved()
        for move in self.current_scramble:
            next_state = apply_move(next_state, move)
        self._refresh_observation_cache(next_state)
        self.current_move_count = 0


def parse_server_moves(text: str, *, max_moves: int | None = None) -> tuple[Move, ...]:
    tokens: list[Move] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        token = text[index]
        if token in SERVER_ALIAS_MOVES:
            if index + 1 < len(text) and text[index + 1] == "'":
                raise ValueError(f"Invalid alias token at position {index}: {text!r}")
            tokens.append(SERVER_ALIAS_MOVES[token])
            index += 1
            continue
        if token not in "UDFBLR":
            raise ValueError(f"Invalid move sequence at position {index}: {text!r}")
        index += 1
        if index < len(text) and text[index] == "'":
            token += "'"
            index += 1
        tokens.append(canonicalize_move(token))

    if not tokens:
        raise ValueError("No moves provided.")
    if max_moves is not None and len(tokens) > max_moves:
        raise ValueError(f"Too many moves: {len(tokens)} > {max_moves}.")
    return tuple(tokens)
