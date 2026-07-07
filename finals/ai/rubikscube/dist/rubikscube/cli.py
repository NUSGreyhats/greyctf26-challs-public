from __future__ import annotations

import argparse
import json
import sys

from .core import FACE_COLORS, CubeState, Move, MoveLog, apply_move, canonicalize_move, is_solved_state, record_move, shuffled_state
from .observations import observe_full_cube, observe_solved_faces
from .render import (
    CubeRenderer,
    RecordingUnavailable,
    RendererUnavailable,
    RenderMode,
    record_mp4,
    selected_backend,
    supports_interactive_rendering,
)

MOVE_SEQUENCE_LIMIT = 2048
MAX_MOVES_PER_CUBE = 25_000
DEFAULT_SHUFFLE_LENGTH = 22
DEFAULT_MOVE_DURATION = 0.05
OBSERVATION_COLOR_ORDER = tuple(FACE_COLORS.values())
SERVER_ALIAS_MOVES: dict[str, Move] = {
    "V": "U'",
    "S": "L'",
    "G": "F'",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="2x2x2 Rubik's cube simulator demo")
    parser.add_argument("moves", nargs="?", default="", help="Initial move sequence, for example: R U F'")
    parser.add_argument("--no-color", action="store_true", help="Render the cube in blind masked-color mode.")
    parser.add_argument(
        "--move-duration",
        type=float,
        default=DEFAULT_MOVE_DURATION,
        help="Target duration in seconds for each quarter-turn animation.",
    )
    parser.add_argument("--no-shuffle", action="store_true", help="Start from a solved cube instead of a random shuffle.")
    parser.add_argument("--shuffle-seed", type=int, help="Seed for reproducible shuffle generation.")
    parser.add_argument(
        "--shuffle-length",
        type=int,
        default=DEFAULT_SHUFFLE_LENGTH,
        help="Number of random moves to use for the startup shuffle.",
    )
    parser.add_argument("--record-mp4", metavar="PATH", help="Record the initial move sequence to an MP4 file.")
    parser.add_argument("--debug-render", action="store_true", help="Print every rendered tile color to stderr.")
    parser.add_argument("--no-render", action="store_true", help="Disable windowed rendering.")
    parser.add_argument("--no-repl", action="store_true", help="Exit after processing the initial move sequence.")
    args = parser.parse_args()

    try:
        moves = parse_player_moves(args.moves)
    except ValueError as exc:
        print(f"Invalid move sequence: {exc}", file=sys.stderr)
        return 1

    render_mode: RenderMode = "solved-mask" if args.no_color else "normal"
    try:
        state, startup_shuffle = _initial_state(args.no_shuffle, args.shuffle_length, args.shuffle_seed)
    except ValueError as exc:
        print(f"Invalid shuffle configuration: {exc}", file=sys.stderr)
        return 1

    if args.record_mp4:
        try:
            record_mp4(
                state,
                moves,
                args.record_mp4,
                move_duration=args.move_duration,
                render_mode=render_mode,
                debug=args.debug_render,
            )
        except (RecordingUnavailable, RendererUnavailable, ValueError) as exc:
            print(f"Unable to record MP4: {exc}", file=sys.stderr)
            return 1
        print(f"Recorded MP4: {args.record_mp4}", file=sys.stderr)

    renderer = _maybe_create_renderer(
        disabled=args.no_render or bool(args.record_mp4),
        render_mode=render_mode,
        debug=args.debug_render,
    )
    if renderer is None and not (args.no_render or args.record_mp4):
        return 1
    log: MoveLog = ()
    move_count = 0

    _print_startup_state(state, render_mode, startup_shuffle)

    if renderer is not None and not (render_mode == "solved-mask" and moves and is_solved_state(state)):
        renderer.draw_state(state, render_mode=render_mode)

    try:
        state, log = _apply_sequence(
            moves,
            state,
            log,
            move_count=move_count,
            renderer=renderer,
            render_mode=render_mode,
            move_duration=args.move_duration,
        )
    except ValueError as exc:
        print(f"Unable to apply move sequence: {exc}", file=sys.stderr)
        return 1
    move_count += len(moves)

    if args.record_mp4 or args.no_repl or not sys.stdin.isatty():
        if renderer is not None:
            renderer.show(block=True)
        return 0

    while True:
        try:
            raw = input("moves> ").strip()
        except EOFError:
            break
        if raw.lower() in {"q", "quit", "exit"}:
            break
        if not raw:
            continue
        try:
            move_sequence = parse_player_moves(raw)
        except ValueError as exc:
            print(f"Invalid move sequence: {exc}", file=sys.stderr)
            continue
        try:
            state, log = _apply_sequence(
                move_sequence,
                state,
                log,
                move_count=move_count,
                renderer=renderer,
                render_mode=render_mode,
                move_duration=args.move_duration,
            )
        except ValueError as exc:
            print(f"Unable to apply move sequence: {exc}", file=sys.stderr)
            continue
        move_count += len(move_sequence)

    return 0


def _initial_state(no_shuffle: bool, shuffle_length: int, shuffle_seed: int | None) -> tuple[CubeState, tuple[str, ...]]:
    if no_shuffle:
        return CubeState.solved(), ()
    if shuffle_length <= 0:
        raise ValueError("shuffle_length must be positive unless --no-shuffle is used.")
    return shuffled_state(length=shuffle_length, seed=shuffle_seed)


def _print_startup_state(state: CubeState, render_mode: RenderMode, startup_shuffle: tuple[str, ...]) -> None:
    if startup_shuffle:
        print(f"Shuffle: {' '.join(startup_shuffle)}")
    if render_mode == "normal":
        print(f"Full cube: {json.dumps(observe_full_cube(state), sort_keys=True)}")
    else:
        print(f"Solved faces: {json.dumps(observe_solved_faces(state), sort_keys=True)}")
    print()


def _apply_sequence(
    moves: tuple[str, ...],
    state: CubeState,
    log: MoveLog,
    *,
    move_count: int,
    renderer: CubeRenderer | None,
    render_mode: RenderMode,
    move_duration: float,
) -> tuple[CubeState, MoveLog]:
    next_move_count = move_count + len(moves)
    if next_move_count > MAX_MOVES_PER_CUBE:
        raise ValueError(f"move limit exceeded: {next_move_count} > {MAX_MOVES_PER_CUBE}.")
    if not moves:
        return state, log

    trace_codes: list[int] = []
    for move in moves:
        before = state
        token = canonicalize_move(move)
        state = apply_move(state, token)
        log = record_move(log, token)
        trace_codes.append(_observation_code(state))
        if renderer is not None:
            renderer.animate_move(before, token, state, move_duration=move_duration, render_mode=render_mode)

    _print_step(log, state, render_mode, trace_codes=trace_codes, move_count=next_move_count)
    return state, log


def _print_step(
    log: MoveLog,
    state: CubeState,
    render_mode: RenderMode,
    *,
    trace_codes: list[int],
    move_count: int,
) -> None:
    print(f"Log: {' '.join(log)}")
    print(_trace_line(trace_codes))
    print(f"MOVES current={move_count} limit={MAX_MOVES_PER_CUBE}")
    if render_mode == "normal":
        print(f"Full cube: {json.dumps(observe_full_cube(state), sort_keys=True)}")
    else:
        print(f"Solved faces: {json.dumps(observe_solved_faces(state), sort_keys=True)}")
    print()


def _maybe_create_renderer(*, disabled: bool, render_mode: RenderMode, debug: bool) -> CubeRenderer | None:
    if disabled:
        return None
    if not supports_interactive_rendering():
        print(
            "Renderer unavailable. "
            f"backend={selected_backend()}. "
            "Install Matplotlib with an interactive backend, or pass --no-render for terminal-only use.",
            file=sys.stderr,
        )
        return None
    try:
        return CubeRenderer(render_mode=render_mode, debug=debug)
    except RendererUnavailable as exc:
        print(f"Renderer unavailable: {exc}", file=sys.stderr)
        return None


def parse_player_moves(text: str, *, max_moves: int = MOVE_SEQUENCE_LIMIT) -> tuple[Move, ...]:
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered == "move":
        raise ValueError("No moves provided.")
    if lowered.startswith("move "):
        stripped = stripped[5:].strip()

    tokens: list[Move] = []
    index = 0
    while index < len(stripped):
        if stripped[index].isspace():
            index += 1
            continue
        token = stripped[index]
        if token in SERVER_ALIAS_MOVES:
            if index + 1 < len(stripped) and stripped[index + 1] == "'":
                raise ValueError(f"Invalid alias token at position {index}: {stripped!r}")
            tokens.append(SERVER_ALIAS_MOVES[token])
            index += 1
            continue
        if token not in "UDFBLR":
            raise ValueError(f"Invalid move sequence at position {index}: {stripped!r}")
        index += 1
        if index < len(stripped) and stripped[index] == "'":
            token += "'"
            index += 1
        tokens.append(canonicalize_move(token))

    if len(tokens) > max_moves:
        raise ValueError(f"Too many moves: {len(tokens)} > {max_moves}.")
    return tuple(tokens)


def _trace_line(trace_codes: list[int]) -> str:
    joined = ",".join(str(code) for code in trace_codes)
    return f"TRACE count={len(trace_codes)} codes={joined}"


def _observation_code(state: CubeState) -> int:
    solved_faces = observe_solved_faces(state)
    code = 0
    for bit, color in enumerate(OBSERVATION_COLOR_ORDER):
        if solved_faces[color]:
            code |= 1 << bit
    return code


if __name__ == "__main__":
    raise SystemExit(main())
