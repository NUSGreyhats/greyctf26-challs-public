from __future__ import annotations

import argparse
import sys

from rubikscube.render import CubeRenderer, RendererUnavailable, selected_backend, supports_interactive_rendering

from .pow import DEFAULT_POW_DIFFICULTY, make_challenge, verify_nonce
from .scoring import ScoreContext, ScoreSubmission, submit_ctfd_score
from .session import ChallengeConfig, ChallengeSession, DEFAULT_CUBE_COUNT, DEFAULT_SHUFFLE_LENGTH
from .team_token import TeamTokenError, TeamTokenResult, normalize_token_line, validate_team_token

BANNER_LINE = "INFO rubikscube-server ready"


def main() -> int:
    parser = argparse.ArgumentParser(description="Masked 2x2x2 terminal challenge server")
    parser.add_argument("--debug", action="store_true", help="Run one cube with verbose hidden-state logs.")
    parser.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-color", action="store_true", help="Render the cube in blind masked-color mode.")
    parser.add_argument("--pow", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pow-difficulty", type=int, default=DEFAULT_POW_DIFFICULTY, help=argparse.SUPPRESS)
    parser.add_argument("--team-token", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, help="Challenge-wide seed for reproducible shuffles.")
    parser.add_argument("--cube-count", type=int, default=DEFAULT_CUBE_COUNT, help="Number of cubes to solve consecutively.")
    parser.add_argument(
        "--shuffle-length",
        type=int,
        default=DEFAULT_SHUFFLE_LENGTH,
        help=f"Shuffle length per cube (minimum {DEFAULT_SHUFFLE_LENGTH}).",
    )
    args = parser.parse_args()

    try:
        session = ChallengeSession(
            ChallengeConfig(
                cube_count=args.cube_count,
                shuffle_length=args.shuffle_length,
                seed=args.seed,
                debug=args.debug,
            )
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not args.headless
    _emit_lines(_banner_lines(team_token=args.team_token, pow_enabled=args.pow))
    token_result = None
    if args.team_token:
        token_result = _run_team_token(interactive=interactive)
        if token_result is None:
            return 1
        session.set_score_submitter(_score_submitter_for(token_result))
    if args.pow:
        if not _run_pow(args.pow_difficulty, interactive=interactive):
            return 1

    render_mode = "solved-mask" if args.no_color else "normal"
    renderer = None if args.headless else _create_required_renderer(render_mode=render_mode)
    if not args.headless and renderer is None:
        return 1
    _emit_lines(session.intro_messages(), include_ready=not interactive)
    if renderer is not None:
        renderer.draw_state(session.current_state, render_mode=render_mode)

    while True:
        try:
            if interactive:
                raw = input("server> ")
            else:
                raw = sys.stdin.readline()
                if raw == "":
                    _emit_lines(("Session ended.",))
                    return 0
        except EOFError:
            _emit_lines(("Session ended.",))
            return 0

        result = session.process_line(raw)
        _emit_lines(result.messages, include_ready=not interactive and not result.should_exit)
        if renderer is not None and result.should_render:
            renderer.draw_state(session.current_state, render_mode=render_mode)
        if result.should_exit:
            return 0


def _format_output_block(lines: tuple[str, ...], *, include_ready: bool = False) -> str:
    output_lines = list(lines)
    if include_ready:
        output_lines.append("READY")
    if not output_lines:
        return ""
    return "".join(f"{line}\n" for line in output_lines)


def _emit_lines(lines: tuple[str, ...], *, include_ready: bool = False) -> None:
    block = _format_output_block(lines, include_ready=include_ready)
    if not block:
        return
    sys.stdout.write(block)
    sys.stdout.flush()


def _banner_lines(*, team_token: bool, pow_enabled: bool) -> tuple[str, ...]:
    if team_token and pow_enabled:
        return (BANNER_LINE, "INFO authenticate with your CTFd team token, then solve proof-of-work.")
    if team_token:
        return (BANNER_LINE, "INFO authenticate with your CTFd team token.")
    if pow_enabled:
        return (BANNER_LINE, "INFO solve proof-of-work to begin.")
    return (BANNER_LINE, "INFO challenge session starting.")


def _run_pow(difficulty: int, *, interactive: bool) -> bool:
    try:
        challenge = make_challenge(difficulty)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return False

    print(f"POW prefix={challenge.prefix} difficulty={challenge.difficulty}", flush=True)
    prompt = "pow> " if interactive else ""
    try:
        nonce = input(prompt).strip()
    except EOFError:
        print("POW failed")
        return False
    if not verify_nonce(challenge.prefix, nonce, challenge.difficulty):
        print("POW failed")
        return False
    print("POW ok", flush=True)
    return True


def _run_team_token(*, interactive: bool) -> TeamTokenResult | None:
    print("TOKEN required", flush=True)
    prompt = "token> " if interactive else ""
    try:
        token = normalize_token_line(input(prompt))
    except EOFError:
        print("TOKEN failed: missing token")
        return None
    except TeamTokenError as exc:
        print(f"TOKEN failed: {exc}")
        return None

    try:
        result = validate_team_token(token)
    except TeamTokenError as exc:
        print(f"TOKEN failed: {_public_token_error(exc)}")
        return None
    print("TOKEN ok", flush=True)
    return result


def _score_submitter_for(token_result: TeamTokenResult):
    context = ScoreContext(team_id=token_result.team_id, challenge_id=token_result.challenge_id)

    def submit(average_moves: float) -> ScoreSubmission:
        return submit_ctfd_score(average_moves, context)

    return submit


def _public_token_error(exc: TeamTokenError) -> str:
    text = str(exc)
    allowed = {
        "missing token",
        "invalid token",
        "challenge already solved for this team",
        "token is for a different challenge",
    }
    if text in allowed:
        return text
    return "authentication unavailable"


def _create_required_renderer(*, render_mode: str) -> CubeRenderer | None:
    if not supports_interactive_rendering():
        print(
            "Renderer unavailable. "
            f"backend={selected_backend()}. "
            "Install Matplotlib with an interactive backend, or pass --headless for CLI/server automation.",
            file=sys.stderr,
        )
        return None
    try:
        return CubeRenderer(render_mode=render_mode)  # type: ignore[arg-type]
    except RendererUnavailable as exc:
        print(f"Renderer unavailable: {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    raise SystemExit(main())
