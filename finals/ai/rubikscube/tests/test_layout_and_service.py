from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CHALL = ROOT / "chall"
SOLVE = ROOT / "solve"


class _FakeAxes:
    def __init__(self, *, elev: float, azim: float, roll: float) -> None:
        self.elev = elev
        self.azim = azim
        self.roll = roll
        self.view_calls: list[dict[str, float]] = []

    def view_init(self, *, elev: float, azim: float, roll: float | None = None) -> None:
        call = {"elev": elev, "azim": azim}
        if roll is not None:
            call["roll"] = roll
            self.roll = roll
        self.elev = elev
        self.azim = azim
        self.view_calls.append(call)


class _NoRollAxes:
    def __init__(self) -> None:
        self.view_calls: list[dict[str, float]] = []

    def view_init(self, *, elev: float, azim: float, roll: float | None = None) -> None:
        if roll is not None:
            raise TypeError("roll is not supported")
        self.view_calls.append({"elev": elev, "azim": azim})


def _clear_rubikscube_modules() -> None:
    for name in tuple(sys.modules):
        if name == "rubikscube" or name.startswith("rubikscube."):
            del sys.modules[name]


def _clear_public_service_modules() -> None:
    for name in tuple(sys.modules):
        if name == "server" or name.startswith("server."):
            del sys.modules[name]
    _clear_rubikscube_modules()


def _load_session_module(base: Path):
    sys.path.insert(0, str(base))
    try:
        from server.cli import session
    finally:
        sys.path.pop(0)
    return session


def _load_render_module(base: Path):
    sys.path.insert(0, str(base))
    try:
        from rubikscube import render
    finally:
        sys.path.pop(0)
    return render


def _load_cli_module(base: Path):
    sys.path.insert(0, str(base))
    try:
        from rubikscube import cli
    finally:
        sys.path.pop(0)
    return cli


def _load_core_module(base: Path):
    sys.path.insert(0, str(base))
    try:
        from rubikscube import core
    finally:
        sys.path.pop(0)
    return core


def _load_team_token_module(base: Path):
    sys.path.insert(0, str(base))
    try:
        from server.cli import team_token
    finally:
        sys.path.pop(0)
    return team_token


def _load_scoring_module(base: Path):
    sys.path.insert(0, str(base))
    try:
        from server.cli import scoring
    finally:
        sys.path.pop(0)
    return scoring


class _FakeHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class LayoutTests(unittest.TestCase):
    def test_required_layout_exists(self) -> None:
        for path in (
            CHALL / "Dockerfile",
            CHALL / "SPEC.md",
            CHALL / "server" / "cli" / "app.py",
            CHALL / "server" / "cli" / "session.py",
            CHALL / "server" / "cli" / "scoring.py",
            CHALL / "server" / "cli" / "team_token.py",
            CHALL / "rubikscube" / "core.py",
            DIST / "USER_GUIDE.md",
            DIST / "pow.py",
            DIST / "rubikscube" / "cli.py",
            DIST / "rubikscube" / "core.py",
            SOLVE / "solve.py",
            SOLVE / "client.py",
        ):
            self.assertTrue(path.exists(), path)
        self.assertFalse((CHALL / "ctf").exists())
        self.assertFalse((DIST / "ctf").exists())
        self.assertFalse((DIST / "SPEC.md").exists())
        self.assertFalse((DIST / "README.md").exists())
        self.assertFalse((CHALL / "secret.py").exists())
        self.assertFalse((DIST / "server" / "cli" / "app.py").exists())
        self.assertFalse((DIST / "secret.py").exists())

    def test_dockerfile_uses_socat_timeouts_and_official_server_flags(self) -> None:
        dockerfile = (CHALL / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ENV SOCAT_CLOSE_TIMEOUT=20", dockerfile)
        self.assertIn("ENV SOCAT_IDLE_TIMEOUT=1800", dockerfile)
        self.assertIn("ENV SOCAT_MAX_CHILDREN=16", dockerfile)
        self.assertIn("exec socat -t ${SOCAT_CLOSE_TIMEOUT:-20} -T ${SOCAT_IDLE_TIMEOUT:-1800}", dockerfile)
        self.assertIn("TCP-LISTEN:${PORT:-1337},reuseaddr,fork,max-children=${SOCAT_MAX_CHILDREN:-16}", dockerfile)
        self.assertIn("python -u -m server.cli.app --headless --pow --no-color --team-token", dockerfile)

    def test_renderer_view_state_captures_and_restores_axes_view(self) -> None:
        for base in (CHALL, DIST):
            sys.path.insert(0, str(base))
            try:
                from rubikscube.render import _ViewState
            finally:
                sys.path.pop(0)
                _clear_rubikscube_modules()

            ax = _FakeAxes(elev=71, azim=22, roll=9)
            view_state = _ViewState()
            view_state.capture(ax)

            ax.elev = 25
            ax.azim = -45
            ax.roll = 0
            view_state.restore(ax)

            self.assertEqual(ax.view_calls[-1], {"elev": 71, "azim": 22, "roll": 9})

    def test_set_view_falls_back_without_roll_support(self) -> None:
        for base in (CHALL, DIST):
            sys.path.insert(0, str(base))
            try:
                from rubikscube.render import _set_view
            finally:
                sys.path.pop(0)
                _clear_rubikscube_modules()

            ax = _NoRollAxes()
            _set_view(ax, elev=13, azim=-17, roll=5)

            self.assertEqual(ax.view_calls, [{"elev": 13, "azim": -17}])

    def test_backend_classifier_allows_gui_agg_backends(self) -> None:
        for base in (CHALL, DIST):
            render = _load_render_module(base)
            try:
                self.assertTrue(render._backend_is_interactive("QtAgg"))
                self.assertTrue(render._backend_is_interactive("qtagg"))
                self.assertTrue(render._backend_is_interactive("TkAgg"))
                self.assertFalse(render._backend_is_interactive("agg"))
                self.assertFalse(render._backend_is_interactive("svg"))
                self.assertFalse(render._backend_is_interactive("module://matplotlib_inline.backend_inline"))
            finally:
                _clear_rubikscube_modules()

    def test_matplotlib_availability_check_does_not_import_pyplot(self) -> None:
        for base in (CHALL, DIST):
            render = _load_render_module(base)
            try:
                sys.modules.pop("matplotlib.pyplot", None)
                render.is_matplotlib_available()
                self.assertNotIn("matplotlib.pyplot", sys.modules)
            finally:
                _clear_rubikscube_modules()

    def test_supports_interactive_rendering_accepts_qtagg_backend(self) -> None:
        for base in (CHALL, DIST):
            render = _load_render_module(base)
            try:
                if not render.is_matplotlib_available():
                    self.skipTest("Matplotlib is not installed.")
                with mock.patch.object(render, "_current_backend", return_value="QtAgg"):
                    self.assertTrue(render.supports_interactive_rendering())
            finally:
                _clear_rubikscube_modules()

    def test_solved_mask_animation_starts_from_pre_move_observation(self) -> None:
        for base in (CHALL, DIST):
            sys.path.insert(0, str(base))
            try:
                from rubikscube import core, render

                scramble = core.generate_shuffle_moves(length=22, seed=1)
                solution = tuple(core.invert_move(move) for move in reversed(scramble))
                before = core.apply_moves(core.apply_moves(core.CubeState.solved(), scramble), solution[:-1])
                after = core.apply_move(before, solution[-1])

                self.assertNotEqual(before, after)
                self.assertEqual(after, core.CubeState.solved())

                first_frame = render._animated_move_frames(
                    before,
                    solution[-1],
                    after,
                    render_mode="solved-mask",
                    frame_count=2,
                )[0]
                expected = render.build_sticker_polygons_for_state(before, render_mode="solved-mask")

                self.assertEqual(
                    [(sticker.face, sticker.row, sticker.col, sticker.color) for sticker in first_frame],
                    [(sticker.face, sticker.row, sticker.col, sticker.color) for sticker in expected],
                )
            finally:
                sys.path.pop(0)
                _clear_rubikscube_modules()

    def test_public_import_hygiene(self) -> None:
        for base in (DIST, SOLVE):
            for path in base.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("finals.ai.rubikscube", text, path)
                self.assertNotRegex(text, r"(^|\n)\s*(from|import)\s+chall(\.|\s|$)", path)
                self.assertNotIn("ctf.cli", text, path)

    def test_public_dist_has_no_private_clutter_or_real_flag(self) -> None:
        forbidden_names = {".git", ".DS_Store", "__pycache__", "artifacts"}
        forbidden_markers = {
            "rubikscube_local_test_flag",
            "FLAG = os.environ",
            "chall/",
            "/chall",
        }
        for path in DIST.rglob("*"):
            if ".venv" in path.relative_to(DIST).parts:
                continue
            self.assertNotIn(path.name, forbidden_names, path)
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                for marker in forbidden_markers:
                    self.assertNotIn(marker, text, path)


class ProofOfWorkTests(unittest.TestCase):
    def test_pow_accepts_valid_nonce_and_rejects_invalid_nonce(self) -> None:
        sys.path.insert(0, str(DIST))
        try:
            from pow import solve_pow, verify_pow
        finally:
            sys.path.pop(0)

        prefix = "abc123"
        nonce = solve_pow(prefix, 8)
        self.assertTrue(verify_pow(prefix, nonce, 8))
        self.assertFalse(verify_pow(prefix, "definitely-wrong", 8))

    def test_dist_pow_script_prints_valid_nonce(self) -> None:
        result = subprocess.run(
            [sys.executable, "pow.py", "abc123", "8"],
            cwd=DIST,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)

        sys.path.insert(0, str(DIST))
        try:
            from pow import verify_pow
        finally:
            sys.path.pop(0)
        self.assertTrue(verify_pow("abc123", result.stdout.strip(), 8))


class CubeMechanicsTests(unittest.TestCase):
    def test_face_turns_have_order_four_and_explicit_inverses(self) -> None:
        for base in (CHALL, DIST):
            core = _load_core_module(base)
            try:
                solved = core.CubeState.solved()
                for move in core.ALL_MOVES:
                    with self.subTest(base=base.name, move=move):
                        state = solved
                        for _ in range(4):
                            state = core.apply_move(state, move)
                        self.assertEqual(state, solved)
                        self.assertEqual(core.apply_move(core.apply_move(solved, move), core.invert_move(move)), solved)
            finally:
                _clear_rubikscube_modules()

    def test_base_moves_follow_outer_face_clockwise_corner_cycles(self) -> None:
        expected_cycles = {
            "U": (1, 2, 3, 0, 4, 5, 6, 7),
            "D": (0, 1, 2, 3, 5, 6, 7, 4),
            "F": (3, 1, 2, 7, 0, 5, 6, 4),
            "B": (0, 5, 1, 3, 4, 6, 2, 7),
            "L": (0, 1, 6, 2, 4, 5, 7, 3),
            "R": (4, 0, 2, 3, 5, 1, 6, 7),
        }
        for base in (CHALL, DIST):
            core = _load_core_module(base)
            try:
                solved = core.CubeState.solved()
                for move, expected_permutation in expected_cycles.items():
                    with self.subTest(base=base.name, move=move):
                        self.assertEqual(core.apply_move(solved, move).permutation, expected_permutation)
            finally:
                _clear_rubikscube_modules()

    def test_fast_move_tables_match_geometric_sticker_rotation(self) -> None:
        for base in (CHALL, DIST):
            core = _load_core_module(base)
            try:
                sample_states = (
                    core.CubeState.solved(),
                    core.apply_moves(core.CubeState.solved(), "R U F' L D B'"),
                    core.CubeState((7, 4, 1, 6, 3, 0, 5, 2), (0, 1, 2, 1, 2, 0, 2, 1)),
                )
                for state in sample_states:
                    for move in core.ALL_MOVES:
                        with self.subTest(base=base.name, state=state, move=move):
                            self.assertEqual(core.apply_move(state, move), core._apply_move_geometric(state, move))
            finally:
                _clear_rubikscube_modules()

    def test_solved_face_observation_tracks_uniform_color_not_fixed_face(self) -> None:
        for base in (CHALL, DIST):
            sys.path.insert(0, str(base))
            try:
                from rubikscube import core
                from rubikscube.observations import observe_solved_faces

                state = core.apply_moves(core.CubeState.solved(), "U D")

                self.assertNotEqual(state.permutation, core.CubeState.solved().permutation)
                self.assertEqual(state, core.CubeState.solved())
                self.assertEqual(hash(state), hash(core.CubeState.solved()))
                self.assertEqual(
                    observe_solved_faces(state),
                    {color: True for color in core.FACE_COLORS.values()},
                )
            finally:
                sys.path.pop(0)
                _clear_rubikscube_modules()


class SessionProtocolTests(unittest.TestCase):
    def test_move_returns_compact_trace_response(self) -> None:
        for base in (CHALL,):
            session_module = _load_session_module(base)
            try:
                session = session_module.ChallengeSession(session_module.ChallengeConfig(cube_count=1, seed=1))
                result = session.process_line("move R U V")
                self.assertEqual(result.command, "move")
                self.assertTrue(result.move_applied)
                self.assertTrue(any(line.startswith("TRACE count=3 codes=") for line in result.messages))
                self.assertIn("MOVES current=3 limit=25000", result.messages)
                self.assertFalse(any(line.startswith("MOVE applied=") for line in result.messages))
            finally:
                _clear_public_service_modules()

    def test_session_solved_condition_matches_uniform_color_faces(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from rubikscube.core import CubeState
            from server.cli.session import ChallengeConfig, ChallengeSession

            session = ChallengeSession(ChallengeConfig(cube_count=1, seed=1))
            session.current_state = CubeState.solved()
            session.current_move_count = 0
            session._refresh_observation_cache(session.current_state)

            result = session.process_line("U D")

            self.assertTrue(result.session_complete)
            self.assertTrue(any(line.startswith("TRACE count=2 codes=3,63") for line in result.messages))
            self.assertTrue(any(line.startswith("SOLVED cube=1") for line in result.messages))
        finally:
            sys.path.pop(0)
            _clear_public_service_modules()


class TeamTokenTests(unittest.TestCase):
    def test_team_token_resolver_builds_plugin_request_and_accepts_matching_challenge(self) -> None:
        team_token = _load_team_token_module(CHALL)
        env = {
            "CTFD_URL": "https://ctfd.example",
            "CTFD_TEAM_TOKEN_PLUGIN_SECRET": "secret-value",
            "CTFD_TEAM_TOKEN_CHALLENGE_ID": "123",
        }
        response = (
            b'{"valid": true, "team_id": 45, "team_name": "blue", '
            b'"challenge_id": 123, "solved": false}'
        )
        with mock.patch.object(team_token, "urlopen", return_value=_FakeHTTPResponse(response)) as urlopen_mock:
            result = team_token.validate_team_token("tt_example", environ=env)

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://ctfd.example/plugins/team-token/api/v1/resolve?token=tt_example")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-value")
        self.assertEqual(result.team_id, "45")
        self.assertEqual(result.challenge_id, "123")
        self.assertEqual(result.team_name, "blue")
        _clear_public_service_modules()

    def test_team_token_resolver_accepts_ctfd_url_that_is_already_resolve_endpoint(self) -> None:
        team_token = _load_team_token_module(CHALL)
        env = {
            "CTFD_URL": "https://ctfd.example/plugins/team-token/api/v1/resolve",
        }

        self.assertEqual(
            team_token.resolver_url_from_env(env),
            "https://ctfd.example/plugins/team-token/api/v1/resolve",
        )
        _clear_public_service_modules()

    def test_team_token_rejects_invalid_solved_or_wrong_challenge_payloads(self) -> None:
        team_token = _load_team_token_module(CHALL)
        env = {
            "CTFD_RESOLVE_URL": "https://ctfd.example/custom-resolve",
            "TEAM_TOKEN_PLUGIN_SECRET": "secret-value",
            "CTFD_TEAM_TOKEN_CHALLENGE_ID": "123",
        }
        cases = (
            b'{"valid": false}',
            b'{"valid": true, "team_id": 45, "challenge_id": 123, "solved": true}',
            b'{"valid": true, "team_id": 45, "challenge_id": 999, "solved": false}',
        )
        for response in cases:
            with self.subTest(response=response):
                with mock.patch.object(team_token, "urlopen", return_value=_FakeHTTPResponse(response)):
                    with self.assertRaises(team_token.TeamTokenError):
                        team_token.validate_team_token("tt_example", environ=env)
        _clear_public_service_modules()

    def test_team_token_requires_resolver_secret_and_expected_challenge(self) -> None:
        team_token = _load_team_token_module(CHALL)
        with self.assertRaises(team_token.TeamTokenError):
            team_token.resolver_url_from_env({})
        with self.assertRaises(team_token.TeamTokenError):
            team_token.secret_from_env({"CTFD_URL": "https://ctfd.example"})
        with self.assertRaises(team_token.TeamTokenError):
            team_token.expected_challenge_id_from_env({"CTFD_URL": "https://ctfd.example"})
        _clear_public_service_modules()

    def test_team_token_app_prompts_after_banner_and_before_pow_and_state(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from server.cli import app
        finally:
            sys.path.pop(0)

        events: list[str] = []

        def fake_pow(_difficulty: int, *, interactive: bool) -> bool:
            del interactive
            events.append("pow")
            print("POW ok", flush=True)
            return True

        def fake_validate(token: str) -> object:
            events.append(f"token:{token}")
            return SimpleNamespace(team_id="45", challenge_id="123")

        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["server.cli.app", "--headless", "--pow", "--team-token", "--cube-count", "1", "--seed", "1"]),
            mock.patch.object(sys, "stdin", io.StringIO("token tt_ok\nquit\n")),
            mock.patch.object(sys, "stdout", stdout),
            mock.patch.object(app, "_run_pow", side_effect=fake_pow),
            mock.patch.object(app, "validate_team_token", side_effect=fake_validate),
        ):
            result = app.main()

        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, 0)
        self.assertEqual(events, ["token:tt_ok", "pow"])
        self.assertEqual(lines[0], "INFO rubikscube-server ready")
        self.assertLess(lines.index("INFO rubikscube-server ready"), lines.index("TOKEN required"))
        self.assertLess(lines.index("TOKEN ok"), lines.index("POW ok"))
        self.assertLess(lines.index("POW ok"), next(i for i, line in enumerate(lines) if line.startswith("STATE code=")))
        self.assertFalse(any("team_id=" in line or "challenge_id=" in line for line in lines if line.startswith("TOKEN ok")))
        _clear_public_service_modules()

    def test_team_token_app_rejects_before_pow_and_state_with_public_error(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from server.cli import app
            from server.cli.team_token import TeamTokenError
        finally:
            sys.path.pop(0)

        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["server.cli.app", "--headless", "--team-token", "--cube-count", "1", "--seed", "1"]),
            mock.patch.object(sys, "stdin", io.StringIO("tt_bad\n")),
            mock.patch.object(sys, "stdout", stdout),
            mock.patch.object(app, "validate_team_token", side_effect=TeamTokenError("invalid token")),
        ):
            result = app.main()

        self.assertEqual(result, 1)
        self.assertIn("TOKEN required", stdout.getvalue())
        self.assertIn("TOKEN failed: invalid token", stdout.getvalue())
        self.assertNotIn("POW prefix=", stdout.getvalue())
        self.assertNotIn("STATE code=", stdout.getvalue())
        _clear_public_service_modules()

    def test_team_token_app_hides_deployment_errors_from_players(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from server.cli import app
            from server.cli.team_token import TeamTokenError
        finally:
            sys.path.pop(0)

        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["server.cli.app", "--headless", "--team-token", "--cube-count", "1", "--seed", "1"]),
            mock.patch.object(sys, "stdin", io.StringIO("tt_bad\n")),
            mock.patch.object(sys, "stdout", stdout),
            mock.patch.object(app, "validate_team_token", side_effect=TeamTokenError("missing CTFD_URL or CTFD_RESOLVE_URL")),
        ):
            result = app.main()

        self.assertEqual(result, 1)
        self.assertIn("TOKEN failed: authentication unavailable", stdout.getvalue())
        self.assertNotIn("CTFD_URL", stdout.getvalue())
        self.assertNotIn("RESOLVE", stdout.getvalue())
        self.assertNotIn("STATE code=", stdout.getvalue())
        _clear_public_service_modules()

    def test_raw_moves_return_compact_trace_response(self) -> None:
        for base in (CHALL,):
            session_module = _load_session_module(base)
            try:
                explicit = session_module.ChallengeSession(session_module.ChallengeConfig(cube_count=1, seed=1))
                raw = session_module.ChallengeSession(session_module.ChallengeConfig(cube_count=1, seed=1))
                self.assertEqual(explicit.process_line("move R U V").messages, raw.process_line("R U V").messages)
            finally:
                _clear_public_service_modules()

    def test_trace_keyword_is_not_a_command(self) -> None:
        for base in (CHALL,):
            session_module = _load_session_module(base)
            try:
                session = session_module.ChallengeSession(session_module.ChallengeConfig(cube_count=1, seed=1))
                intro = "\n".join(session.intro_messages())
                help_text = "\n".join(session.process_line("help").messages)
                result = session.process_line("trace R")

                self.assertNotIn("commands=state,score,progress,help,quit,move,trace", intro)
                self.assertNotIn("trace <moves>", help_text)
                self.assertEqual(result.command, "invalid")
                self.assertIn("Invalid move sequence:", result.messages[0])
            finally:
                _clear_public_service_modules()

    def test_move_command_is_capped_at_2048_tokens(self) -> None:
        for base in (CHALL,):
            session_module = _load_session_module(base)
            try:
                accepted = session_module.parse_server_moves(
                    " ".join("R" for _ in range(2048)),
                    max_moves=session_module.MOVE_SEQUENCE_LIMIT,
                )
                self.assertEqual(len(accepted), 2048)

                with self.assertRaisesRegex(ValueError, "Too many moves: 2049 > 2048"):
                    session_module.parse_server_moves(
                        " ".join("R" for _ in range(2049)),
                        max_moves=session_module.MOVE_SEQUENCE_LIMIT,
                    )
            finally:
                _clear_public_service_modules()


class ScoringTests(unittest.TestCase):
    def test_score_formula_caps_and_interpolates(self) -> None:
        scoring = _load_scoring_module(CHALL)
        try:
            self.assertEqual(scoring.compute_score(1), 1000)
            self.assertEqual(scoring.compute_score(2000), 1000)
            self.assertEqual(scoring.compute_score(25000), 100)
            self.assertEqual(scoring.compute_score(100000), 100)
            self.assertGreater(scoring.compute_score(10000), scoring.compute_score(20000))
            self.assertGreater(scoring.compute_score(20000), 100)
            self.assertLess(scoring.compute_score(10000), 1000)
            with self.assertRaises(ValueError):
                scoring.compute_score(0)
        finally:
            _clear_public_service_modules()

    def test_ctfd_score_create_uses_team_award_payload(self) -> None:
        scoring = _load_scoring_module(CHALL)
        env = {
            "CTFD_URL": "https://ctfd.example",
            "CTFD_API_TOKEN": "api-token",
            "CTFD_AWARD_CATEGORY": "AI",
        }
        responses = [
            _FakeHTTPResponse(b'{"data": []}'),
            _FakeHTTPResponse(b'{"success": true, "data": {"id": 7}}'),
        ]
        requests = []

        def fake_urlopen(request, *, timeout: float):
            del timeout
            requests.append(request)
            return responses.pop(0)

        with mock.patch.object(scoring, "urlopen", side_effect=fake_urlopen):
            result = scoring.submit_ctfd_score(5000, scoring.ScoreContext(team_id="45", challenge_id="123"), environ=env)

        try:
            self.assertEqual(result.status, "submitted")
            self.assertGreater(result.score, 100)
            self.assertEqual(requests[0].get_method(), "GET")
            self.assertEqual(requests[1].get_method(), "POST")
            self.assertEqual(requests[1].get_header("Authorization"), "Token api-token")
            payload = scoring.json.loads(requests[1].data.decode("utf-8"))
            self.assertEqual(payload["team_id"], 45)
            self.assertEqual(payload["category"], "AI")
            self.assertIn("challenge=123 team=45", payload["description"])
        finally:
            _clear_public_service_modules()

    def test_ctfd_score_preserves_existing_better_award(self) -> None:
        scoring = _load_scoring_module(CHALL)
        env = {
            "CTFD_URL": "https://ctfd.example",
            "CTFD_API_TOKEN": "api-token",
        }
        existing = (
            b'{"data": [{"id": 7, "value": 900, '
            b'"description": "rubikscube-score-v1 challenge=123 team=45 average=10000.00"}]}'
        )
        requests = []

        def fake_urlopen(request, *, timeout: float):
            del timeout
            requests.append(request)
            return _FakeHTTPResponse(existing)

        with mock.patch.object(scoring, "urlopen", side_effect=fake_urlopen):
            result = scoring.submit_ctfd_score(50000, scoring.ScoreContext(team_id="45", challenge_id="123"), environ=env)

        try:
            self.assertEqual(result.status, "submitted")
            self.assertEqual([request.get_method() for request in requests], ["GET"])
        finally:
            _clear_public_service_modules()

    def test_ctfd_score_updates_existing_lower_award(self) -> None:
        scoring = _load_scoring_module(CHALL)
        env = {
            "CTFD_SCORE_URL": "https://ctfd.example/api/v1/awards",
            "CTFD_API_TOKEN": "api-token",
        }
        responses = [
            _FakeHTTPResponse(
                b'{"data": [{"id": 7, "value": 100, '
                b'"description": "rubikscube-score-v1 challenge=123 team=45 average=25000.00"}]}'
            ),
            _FakeHTTPResponse(b'{"success": true, "data": {"id": 7}}'),
        ]
        requests = []

        def fake_urlopen(request, *, timeout: float):
            del timeout
            requests.append(request)
            return responses.pop(0)

        with mock.patch.object(scoring, "urlopen", side_effect=fake_urlopen):
            result = scoring.submit_ctfd_score(2000, scoring.ScoreContext(team_id="45", challenge_id="123"), environ=env)

        try:
            self.assertEqual(result, scoring.ScoreSubmission(score=1000, status="submitted"))
            self.assertEqual([request.get_method() for request in requests], ["GET", "PATCH"])
            self.assertEqual(requests[1].full_url, "https://ctfd.example/api/v1/awards/7")
        finally:
            _clear_public_service_modules()

    def test_ctfd_score_pending_without_credentials(self) -> None:
        scoring = _load_scoring_module(CHALL)
        try:
            result = scoring.submit_ctfd_score(25000, scoring.ScoreContext(team_id="45", challenge_id="123"), environ={})
            self.assertEqual(result, scoring.ScoreSubmission(score=100, status="score_pending"))
        finally:
            _clear_public_service_modules()


class StandalonePublicCliTests(unittest.TestCase):
    def test_public_cli_parser_is_capped_at_2048_tokens(self) -> None:
        cli = _load_cli_module(DIST)
        try:
            accepted = cli.parse_player_moves(" ".join("R" for _ in range(2048)))
            self.assertEqual(len(accepted), 2048)

            with self.assertRaisesRegex(ValueError, "Too many moves: 2049 > 2048"):
                cli.parse_player_moves(" ".join("R" for _ in range(2049)))
        finally:
            _clear_rubikscube_modules()

    def test_public_cli_move_outputs_trace_lines(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "rubikscube.cli",
                "--no-render",
                "--no-repl",
                "--no-shuffle",
                "move R U V",
            ],
            cwd=DIST,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TRACE count=3 codes=", result.stdout)
        self.assertIn("MOVES current=3 limit=25000", result.stdout)

    def test_public_cli_rejects_trace_keyword(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "rubikscube.cli",
                "--no-render",
                "--no-repl",
                "--no-shuffle",
                "trace R",
            ],
            cwd=DIST,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid move sequence", result.stderr)

    def test_public_cli_no_color_prints_solved_faces(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "rubikscube.cli",
                "--no-render",
                "--no-repl",
                "--no-shuffle",
                "--no-color",
            ],
            cwd=DIST,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Solved faces:", result.stdout)
        self.assertNotIn("Full cube:", result.stdout)

    def test_public_cli_requires_renderer_unless_no_render_is_explicit(self) -> None:
        sys.path.insert(0, str(DIST))
        try:
            from rubikscube import cli
        finally:
            sys.path.pop(0)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["rubikscube.cli", "--no-repl", "--no-shuffle"]),
            mock.patch.object(sys, "stdout", stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(cli, "supports_interactive_rendering", return_value=False),
            mock.patch.object(cli, "selected_backend", return_value="agg"),
        ):
            result = cli.main()

        _clear_rubikscube_modules()
        self.assertEqual(result, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Renderer unavailable", stderr.getvalue())
        self.assertIn("backend=agg", stderr.getvalue())
        self.assertIn("--no-render", stderr.getvalue())

    def test_public_cli_animates_moves_when_renderer_is_enabled(self) -> None:
        sys.path.insert(0, str(DIST))
        try:
            from rubikscube import cli
        finally:
            sys.path.pop(0)

        created_modes: list[str] = []
        animated_moves: list[str] = []
        durations: list[float] = []

        class FakeRenderer:
            def __init__(self, *, render_mode: str, debug: bool = False) -> None:
                del debug
                created_modes.append(render_mode)

            def draw_state(self, _state: object, *, render_mode: str) -> bool:
                created_modes.append(render_mode)
                return True

            def animate_move(
                self,
                _before_state: object,
                move: str,
                _after_state: object,
                *,
                move_duration: float,
                render_mode: str,
            ) -> bool:
                durations.append(move_duration)
                created_modes.append(render_mode)
                animated_moves.append(move)
                return True

            def show(self, *, block: bool = True) -> None:
                del block

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["rubikscube.cli", "--no-repl", "--no-shuffle", "R U"]),
            mock.patch.object(sys, "stdout", stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(cli, "supports_interactive_rendering", return_value=True),
            mock.patch.object(cli, "CubeRenderer", FakeRenderer),
        ):
            result = cli.main()

        _clear_rubikscube_modules()
        self.assertEqual(result, 0, stderr.getvalue())
        self.assertEqual(animated_moves, ["R", "U"])
        self.assertEqual(durations, [0.05, 0.05])
        self.assertTrue(created_modes)
        self.assertTrue(all(mode == "normal" for mode in created_modes))


class SolverClientProtocolTests(unittest.TestCase):
    def test_challenge_client_answers_team_token_before_pow(self) -> None:
        sys.path.insert(0, str(SOLVE))
        try:
            from client import ChallengeClient
        finally:
            sys.path.pop(0)

        class FakeProcess:
            def __init__(self) -> None:
                self.stdin = io.StringIO()
                self.stdout = io.StringIO(
                    "INFO rubikscube-server ready\n"
                    "TOKEN required\n"
                    "POW prefix=abc difficulty=0\n"
                    "READY\n"
                )

        client = ChallengeClient(["unused"], team_token="tt_ok")
        client._process = FakeProcess()  # type: ignore[assignment]
        response = client._read_until_ready()

        self.assertEqual(response.lines, ("INFO rubikscube-server ready",))
        assert client._process is not None
        assert client._process.stdin is not None
        self.assertEqual(client._process.stdin.getvalue().splitlines(), ["tt_ok", "0"])


class CliSmokeTests(unittest.TestCase):
    def test_completed_challenge_session_reports_score_without_flag(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from server.cli.session import ChallengeConfig, ChallengeSession
            from rubikscube.core import invert_move
        finally:
            sys.path.pop(0)

        session = ChallengeSession(ChallengeConfig(cube_count=1, seed=1))
        solution = tuple(invert_move(move) for move in reversed(session.current_scramble))
        result = session.process_line(" ".join(solution))

        self.assertTrue(result.session_complete)
        final_lines = [line for line in result.messages if line.startswith("FINAL ")]
        self.assertEqual(len(final_lines), 1)
        self.assertIn("score=1000", final_lines[0])
        self.assertIn("status=score_pending", final_lines[0])
        self.assertFalse(any(line.startswith("FLAG ") for line in result.messages))

    def test_default_headless_cli_reaches_ready_without_pow(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{DIST}{os.pathsep}{CHALL}"
        result = subprocess.run(
            [
                sys.executable,
                "-u",
                "-m",
                "server.cli.app",
                "--cube-count",
                "1",
                "--seed",
                "1",
                "--headless",
            ],
            cwd=ROOT,
            env=env,
            input="quit\n",
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("POW prefix=", result.stdout)
        self.assertTrue(any(line.startswith("STATE code=") for line in result.stdout.splitlines()))
        self.assertIn("READY", result.stdout.splitlines())

    def test_pow_flag_reaches_ready_after_valid_nonce(self) -> None:
        sys.path.insert(0, str(SOLVE))
        try:
            from client import solve_pow
        finally:
            sys.path.pop(0)

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{DIST}{os.pathsep}{CHALL}"
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "server.cli.app",
                "--cube-count",
                "1",
                "--seed",
                "1",
                "--pow-difficulty",
                "8",
                "--headless",
                "--pow",
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        first_line = process.stdout.readline().strip()
        self.assertEqual(first_line, "INFO rubikscube-server ready")
        pow_line = ""
        while True:
            pow_line = process.stdout.readline().strip()
            if pow_line.startswith("POW "):
                break
        fields = dict(field.split("=", 1) for field in pow_line.split()[1:] if "=" in field)
        process.stdin.write(solve_pow(fields["prefix"], int(fields["difficulty"])) + "\n")
        process.stdin.flush()
        lines: list[str] = []
        while True:
            line = process.stdout.readline()
            if line == "":
                break
            lines.append(line.rstrip())
            if line.rstrip() == "READY":
                break
        process.stdin.write("quit\n")
        process.stdin.flush()
        process.communicate(timeout=5)

        self.assertEqual(process.returncode, 0)
        self.assertIn("POW ok", lines)
        self.assertTrue(any(line.startswith("STATE code=") for line in lines))
        self.assertIn("READY", lines)

    def test_non_headless_cli_requires_interactive_renderer(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from server.cli import app
        finally:
            sys.path.pop(0)

        stderr = io.StringIO()
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["server.cli.app", "--cube-count", "1", "--seed", "1"]),
            mock.patch.object(sys, "stdin", io.StringIO("quit\n")),
            mock.patch.object(sys, "stdout", stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(app, "supports_interactive_rendering", return_value=False),
            mock.patch.object(app, "selected_backend", return_value="agg"),
        ):
            result = app.main()

        _clear_public_service_modules()
        self.assertEqual(result, 1)
        self.assertIn("Renderer unavailable", stderr.getvalue())
        self.assertIn("backend=agg", stderr.getvalue())
        self.assertIn("INFO rubikscube-server ready", stdout.getvalue())

    def test_non_headless_cli_uses_full_color_renderer_by_default(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from server.cli import app
        finally:
            sys.path.pop(0)

        created_modes: list[str] = []
        drawn_modes: list[str] = []

        class FakeRenderer:
            def __init__(self, *, render_mode: str) -> None:
                created_modes.append(render_mode)

            def draw_state(self, _state: object, *, render_mode: str) -> bool:
                drawn_modes.append(render_mode)
                return True

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["server.cli.app", "--cube-count", "1", "--seed", "1"]),
            mock.patch.object(sys, "stdin", io.StringIO("quit\n")),
            mock.patch.object(sys, "stdout", stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(app, "supports_interactive_rendering", return_value=True),
            mock.patch.object(app, "CubeRenderer", FakeRenderer),
        ):
            result = app.main()

        _clear_public_service_modules()
        self.assertEqual(result, 0, stderr.getvalue())
        self.assertEqual(created_modes, ["normal"])
        self.assertTrue(drawn_modes)
        self.assertTrue(all(mode == "normal" for mode in drawn_modes))

    def test_no_color_cli_uses_masked_renderer(self) -> None:
        sys.path.insert(0, str(CHALL))
        try:
            from server.cli import app
        finally:
            sys.path.pop(0)

        created_modes: list[str] = []
        drawn_modes: list[str] = []

        class FakeRenderer:
            def __init__(self, *, render_mode: str) -> None:
                created_modes.append(render_mode)

            def draw_state(self, _state: object, *, render_mode: str) -> bool:
                drawn_modes.append(render_mode)
                return True

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["server.cli.app", "--cube-count", "1", "--seed", "1", "--no-color"]),
            mock.patch.object(sys, "stdin", io.StringIO("quit\n")),
            mock.patch.object(sys, "stdout", stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(app, "supports_interactive_rendering", return_value=True),
            mock.patch.object(app, "CubeRenderer", FakeRenderer),
        ):
            result = app.main()

        _clear_public_service_modules()
        self.assertEqual(result, 0, stderr.getvalue())
        self.assertEqual(created_modes, ["solved-mask"])
        self.assertTrue(drawn_modes)
        self.assertTrue(all(mode == "solved-mask" for mode in drawn_modes))

    def test_debug_mode_does_not_enable_pow_by_default(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{DIST}{os.pathsep}{CHALL}"
        result = subprocess.run(
            [sys.executable, "-u", "-m", "server.cli.app", "--debug", "--headless", "--seed", "1"],
            cwd=ROOT,
            env=env,
            input="quit\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("POW prefix=", result.stdout)
        self.assertIn("DEBUG hidden_full_state=", result.stdout)

    def test_sample_solve_solves_one_seeded_cube_against_dist_cli(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "solve/solve.py",
                "--challenge-command",
                f"{sys.executable} -u -m server.cli.app --cube-count 1 --seed 1 --headless",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SOLVER2 cube=1", result.stdout)
        group_line = next(line for line in result.stdout.splitlines() if line.startswith("SOLVER2 cube=1 "))
        move_count = int(next(field.removeprefix("moves=") for field in group_line.split() if field.startswith("moves=")))
        self.assertGreater(move_count, 22)

    def test_sample_solve_accepts_explicit_group_strategy(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "solve/solve.py",
                "--strategy",
                "group",
                "--challenge-command",
                f"{sys.executable} -u -m server.cli.app --cube-count 1 --seed 1 --headless",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SOLVER2 cube=1", result.stdout)

    def test_sample_solve_accepts_gofai_strategy(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "solve/solve.py",
                "--strategy",
                "gofai",
                "--challenge-command",
                f"{sys.executable} -u -m server.cli.app --cube-count 1 --seed 1 --headless",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SOLVER2 cube=1", result.stdout)

    def test_gofai_cases_and_probes_are_bounded_legal_quarter_turn_tokens(self) -> None:
        sys.path.insert(0, str(SOLVE))
        try:
            from gofai import solver as gofai_solver
            from gofai import cases as gofai_cases
            from gofai import probes as gofai_probes
        finally:
            sys.path.pop(0)

        self.assertIn("no solve/group_theory data path", gofai_cases.PROVENANCE)
        self.assertLessEqual(len(gofai_cases.OLL_ALGORITHMS), 8)
        self.assertLessEqual(len(gofai_cases.PBL_ALGORITHMS), 16)
        self.assertLess(gofai_cases.literal_move_count(), 256)
        for table, max_len in ((gofai_cases.OLL_ALGORITHMS, 14), (gofai_cases.PBL_ALGORITHMS, 18)):
            for case in table:
                self.assertLessEqual(len(case.moves), max_len, case.name)
                self.assertTrue(all(move in gofai_solver.LEGAL_MOVES for move in case.moves), case.name)
                self.assertFalse(any(move.endswith("2") for move in case.moves), case.name)
        self.assertLessEqual(len(gofai_cases.RESEARCH_OLL_ALGORITHMS), 8)
        for case in gofai_cases.RESEARCH_OLL_ALGORITHMS:
            self.assertLessEqual(len(case.moves), 10, case.name)
            self.assertTrue(all(move in gofai_solver.LEGAL_MOVES for move in case.moves), case.name)
            self.assertFalse(any(move.endswith("2") for move in case.moves), case.name)
        self.assertLessEqual(len(gofai_cases.RESEARCH_PBL_ALGORITHMS), 24)
        for case in gofai_cases.RESEARCH_PBL_ALGORITHMS:
            self.assertLessEqual(len(case.moves), 13, case.name)
            self.assertTrue(all(move in gofai_solver.LEGAL_MOVES for move in case.moves), case.name)
            self.assertFalse(any(move.endswith("2") for move in case.moves), case.name)
        self.assertLessEqual(len(gofai_cases.DIRECT_RESEARCH_PBL_ALGORITHMS), 64)
        for case in gofai_cases.DIRECT_RESEARCH_PBL_ALGORITHMS:
            self.assertLessEqual(len(case.moves), 12, case.name)
            self.assertTrue(all(move in gofai_solver.LEGAL_MOVES for move in case.moves), case.name)
            self.assertFalse(any(move.endswith("2") for move in case.moves), case.name)
        self.assertGreater(len(gofai_probes.FIRST_FACE_PROBES), len(gofai_probes.BASE_PROBE_MOTIFS))
        self.assertTrue(
            all(
                len(probe.moves) <= 8 and all(move in gofai_solver.LEGAL_MOVES for move in probe.moves)
                for probe in gofai_probes.FIRST_FACE_PROBES
            )
        )

    def test_gofai_inverse_cancels_sample_sequences_syntactically(self) -> None:
        sys.path.insert(0, str(SOLVE))
        try:
            from gofai import solver as gofai_solver
        finally:
            sys.path.pop(0)

        for sample in (
            ("R", "U", "R'", "U'"),
            ("F", "R'", "F'", "R"),
            ("B", "L", "D'", "F'"),
        ):
            inverse = gofai_solver.inverse(sample)
            self.assertEqual(gofai_solver.inverse(inverse), tuple(sample))
            for move, undo in zip(reversed(sample), inverse, strict=True):
                self.assertEqual(gofai_solver.inverse((move,)), (undo,))

    def test_gofai_skips_already_solved_cube(self) -> None:
        sys.path.insert(0, str(SOLVE))
        try:
            from gofai import solver as gofai_solver
        finally:
            sys.path.pop(0)

        class FakeClient:
            def __init__(self) -> None:
                self.moves: list[str] = []

            def apply_move(self, move: str) -> object:
                self.moves.append(move)
                raise AssertionError("already-solved GOFAI run should not apply moves")

        client = FakeClient()
        solver = gofai_solver.GofaiSolver(client, gofai_solver.SOLVED_MASK)
        solver.run()

        self.assertEqual(client.moves, [])

    def test_gofai_frame_mapping_covers_all_acquired_faces(self) -> None:
        sys.path.insert(0, str(SOLVE))
        try:
            from gofai import frame as gofai_frame
        finally:
            sys.path.pop(0)

        for down_face in gofai_frame.FACE_ORDER:
            frame = gofai_frame.frame_for_down_face(down_face)
            self.assertEqual(frame.move_map["D"], down_face)
            self.assertEqual(frame.move_map["U"], gofai_frame.OPPOSITE[down_face])
            self.assertEqual(set(frame.move_map.values()), set(gofai_frame.FACE_ORDER))

    def test_gofai_oll_candidates_preserve_acquired_face_by_construction(self) -> None:
        sys.path.insert(0, str(SOLVE))
        try:
            from gofai import cases as gofai_cases
            from gofai import frame as gofai_frame
        finally:
            sys.path.pop(0)

        for down_face in gofai_frame.FACE_ORDER:
            frame = gofai_frame.frame_for_down_face(down_face)
            for case in gofai_cases.OLL_ALGORITHMS + gofai_cases.RESEARCH_OLL_ALGORITHMS:
                mapped = frame.map_moves(case.moves)
                self.assertFalse(any(move[0] == down_face for move in mapped), (down_face, case.name, mapped))

    def test_gofai_failed_probe_undo_restores_local_state(self) -> None:
        sys.path[:0] = [str(SOLVE), str(CHALL)]
        try:
            from gofai import solver as gofai_solver
            from gofai.probes import Probe
            from client import ChallengeResponse
            from rubikscube.core import CubeState, apply_move, generate_shuffle_moves
            from rubikscube.observations import observe_solved_faces
            from server.cli.session import DEFAULT_SHUFFLE_LENGTH
        finally:
            del sys.path[:2]

        color_order = ("white", "yellow", "green", "blue", "orange", "red")

        def code_for_state(state: object) -> int:
            observed = observe_solved_faces(state)
            code = 0
            for bit, color in enumerate(color_order):
                if observed[color]:
                    code |= 1 << bit
            return code

        class SimulatorClient:
            def __init__(self) -> None:
                self.state = CubeState.solved()
                for move in generate_shuffle_moves(length=DEFAULT_SHUFFLE_LENGTH, seed=1):
                    self.state = apply_move(self.state, move)
                self.moves: list[str] = []

            def apply_move(self, move: str) -> ChallengeResponse:
                self.state = apply_move(self.state, move)
                self.moves.append(move)
                solved = self.state == CubeState.solved()
                return ChallengeResponse(
                    (),
                    trace_codes=(gofai_solver.SOLVED_MASK if solved else code_for_state(self.state),),
                    move_count=len(self.moves),
                    solved=solved,
                    failed=False,
                )

        client = SimulatorClient()
        before = client.state
        solver = gofai_solver.GofaiSolver(client, 0)
        self.assertIsNone(solver._try_first_face_probe(Probe("unit", ("R", "U"))))
        self.assertEqual(client.state, before)
        self.assertEqual(client.moves, ["R", "U", "U'", "R'"])

    def test_gofai_solver_does_not_import_cube_or_group_solver_modules(self) -> None:
        forbidden = (
            "rubikscube.core",
            "gofai.tapes",
            "group_theory",
            "group_theory_solver",
            "partial_observation_solver",
            "model",
            "search",
            "legacy",
        )
        for source in (
            SOLVE / "gofai" / "solver.py",
            SOLVE / "gofai" / "frame.py",
            SOLVE / "gofai" / "probes.py",
            SOLVE / "gofai" / "cases.py",
        ):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            for module in imports:
                self.assertFalse(any(module == name or module.startswith(name + ".") for name in forbidden), (source, module))

    def test_gofai_generated_probe_bank_acquires_faces_on_research_sample(self) -> None:
        sys.path[:0] = [str(SOLVE), str(CHALL)]
        try:
            from gofai import solver as gofai_solver
            from client import ChallengeResponse
            from rubikscube.core import CubeState, apply_move, generate_shuffle_moves
            from rubikscube.observations import observe_solved_faces
            from server.cli.session import DEFAULT_SHUFFLE_LENGTH
        finally:
            del sys.path[:2]

        import random

        color_order = ("white", "yellow", "green", "blue", "orange", "red")

        def code_for_state(state: object) -> int:
            observed = observe_solved_faces(state)
            code = 0
            for bit, color in enumerate(color_order):
                if observed[color]:
                    code |= 1 << bit
            return code

        class SimulatorClient:
            def __init__(self, seed: int) -> None:
                self.state = CubeState.solved()
                for move in generate_shuffle_moves(length=DEFAULT_SHUFFLE_LENGTH, seed=seed):
                    self.state = apply_move(self.state, move)
                self.moves: list[str] = []

            def apply_move(self, move: str) -> ChallengeResponse:
                self.state = apply_move(self.state, move)
                self.moves.append(move)
                solved = self.state == CubeState.solved()
                return ChallengeResponse(
                    (),
                    trace_codes=(gofai_solver.SOLVED_MASK if solved else code_for_state(self.state),),
                    move_count=len(self.moves),
                    solved=solved,
                    failed=False,
                )

        rng = random.Random(12345)
        seeds = [rng.randrange(1, 10_000_000) for _ in range(128)]
        acquired = 0
        for seed in seeds:
            client = SimulatorClient(seed)
            solver = gofai_solver.GofaiSolver(client, code_for_state(client.state))
            try:
                solver._acquire_first_face()
            except RuntimeError:
                continue
            acquired += 1
        self.assertGreaterEqual(acquired, 100)


@unittest.skipUnless(os.environ.get("RUN_DOCKER_SMOKE") and shutil.which("docker"), "set RUN_DOCKER_SMOKE=1 with docker available")
class DockerSmokeTests(unittest.TestCase):
    def test_docker_image_builds(self) -> None:
        result = subprocess.run(
            ["docker", "build", "-t", "rubikscube-chall-smoke", "."],
            cwd=CHALL,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
