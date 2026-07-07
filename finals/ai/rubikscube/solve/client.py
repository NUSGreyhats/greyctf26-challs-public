from __future__ import annotations

import ast
import hashlib
import os
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence

try:
    import _dist_path
except ModuleNotFoundError:  # pragma: no cover - package import path
    from . import _dist_path  # type: ignore
from rubikscube.core import FACE_COLORS

OBSERVATION_COLOR_ORDER = tuple(FACE_COLORS.values())
CUBER_BRUCE_ALIASES = {
    "U'": "V",
    "L'": "S",
    "F'": "G",
}


@dataclass(frozen=True, slots=True)
class ChallengeResponse:
    lines: tuple[str, ...]
    trace_codes: tuple[int, ...] = ()
    state_codes: tuple[int, ...] = ()
    state_code: int | None = None
    move_count: int | None = None
    solved: bool = False
    failed: bool = False
    final_average: float | None = None
    session_complete: bool = False


def code_to_observation(code: int) -> dict[str, bool]:
    return {
        color: bool(code & (1 << bit))
        for bit, color in enumerate(OBSERVATION_COLOR_ORDER)
    }


def observation_to_code(observation: Mapping[str, bool]) -> int:
    code = 0
    for bit, color in enumerate(OBSERVATION_COLOR_ORDER):
        if observation[color]:
            code |= 1 << bit
    return code


def encode_moves(moves: Sequence[str]) -> str:
    return " ".join(CUBER_BRUCE_ALIASES.get(move, move) for move in moves)


def parse_response(lines: Sequence[str]) -> ChallengeResponse:
    state_code: int | None = None
    state_codes: list[int] = []
    trace_codes: tuple[int, ...] = ()
    move_count: int | None = None
    solved = False
    failed = False
    final_average: float | None = None
    session_complete = False

    for line in lines:
        if line.startswith("STATE "):
            if " code=" in line and " masked=" in line:
                state_code = int(line.split(" code=", 1)[1].split(" ", 1)[0])
            elif line.startswith("STATE masked="):
                payload = ast.literal_eval(line.split("=", 1)[1].strip())
                state_code = observation_to_code(payload)
            if state_code is not None:
                state_codes.append(state_code)
        elif line.startswith("TRACE "):
            fields = dict(field.split("=", 1) for field in line.split()[1:] if "=" in field)
            raw_codes = fields.get("codes", "")
            trace_codes = tuple(int(code) for code in raw_codes.split(",") if code)
        elif line.startswith("MOVES "):
            fields = dict(field.split("=", 1) for field in line.split()[1:] if "=" in field)
            current = fields.get("current")
            if current is not None:
                move_count = int(current)
        elif line.startswith("SOLVED "):
            solved = True
            fields = dict(field.split("=", 1) for field in line.split()[1:] if "=" in field)
            moves = fields.get("moves")
            if moves is not None:
                move_count = int(moves)
        elif line.startswith("FAILED "):
            failed = True
            fields = dict(field.split("=", 1) for field in line.split()[1:] if "=" in field)
            moves = fields.get("moves")
            if moves is not None:
                move_count = int(moves)
        elif line.startswith("FINAL "):
            session_complete = True
            for field in line.split()[1:]:
                if field.startswith("average="):
                    final_average = float(field.split("=", 1)[1])
        elif line.startswith("DEBUG "):
            continue

    return ChallengeResponse(
        lines=tuple(lines),
        trace_codes=trace_codes,
        state_codes=tuple(state_codes),
        state_code=state_code,
        move_count=move_count,
        solved=solved,
        failed=failed,
        final_average=final_average,
        session_complete=session_complete,
    )


class ChallengeClient:
    def __init__(self, command: Sequence[str], *, team_token: str | None = None) -> None:
        self.command = tuple(command)
        self.team_token = team_token if team_token is not None else os.environ.get("RUBIK_TEAM_TOKEN")
        self._process: subprocess.Popen[str] | None = None
        self.round_trips = 0

    def start(self) -> ChallengeResponse:
        if self._process is not None:
            raise RuntimeError("Challenge process already started.")
        env = os.environ.copy()
        challenge_paths = f"{_dist_path.DIST_DIR}{os.pathsep}{_dist_path.CHALL_DIR}"
        env["PYTHONPATH"] = (
            challenge_paths
            if not env.get("PYTHONPATH")
            else f"{challenge_paths}{os.pathsep}{env['PYTHONPATH']}"
        )
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        return self._read_until_ready()

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def run_command(self, command: str) -> ChallengeResponse:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Challenge process has not been started.")
        self._process.stdin.write(command + "\n")
        self._process.stdin.flush()
        self.round_trips += 1
        return self._read_until_ready()

    def apply_move(self, move: str) -> ChallengeResponse:
        return self.run_command(encode_moves((move,)))

    def trace(self, moves: Sequence[str]) -> ChallengeResponse:
        return self.run_command(f"move {encode_moves(moves)}")

    def _read_until_ready(self) -> ChallengeResponse:
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Challenge process has not been started.")
        lines: list[str] = []
        while True:
            line = self._process.stdout.readline()
            if line == "":
                break
            stripped = line.rstrip()
            if stripped.startswith("POW "):
                self._answer_pow(stripped)
                continue
            if stripped == "TOKEN required":
                self._answer_team_token()
                continue
            if stripped == "READY":
                break
            if stripped:
                lines.append(stripped)
        return parse_response(lines)

    def _answer_pow(self, line: str) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Challenge process has not been started.")
        fields = dict(field.split("=", 1) for field in line.split()[1:] if "=" in field)
        prefix = fields["prefix"]
        difficulty = int(fields["difficulty"])
        nonce = solve_pow(prefix, difficulty)
        self._process.stdin.write(nonce + "\n")
        self._process.stdin.flush()

    def _answer_team_token(self) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Challenge process has not been started.")
        if not self.team_token:
            raise RuntimeError("Challenge requested a team token, but none was provided.")
        self._process.stdin.write(self.team_token + "\n")
        self._process.stdin.flush()


def solve_pow(prefix: str, difficulty: int) -> str:
    counter = 0
    while True:
        nonce = f"{counter:x}"
        if verify_pow(prefix, nonce, difficulty):
            return nonce
        counter += 1


def verify_pow(prefix: str, nonce: str, difficulty: int) -> bool:
    digest = hashlib.sha256((prefix + nonce).encode("ascii")).digest()
    whole_bytes, remaining_bits = divmod(difficulty, 8)
    if any(digest[index] != 0 for index in range(whole_bytes)):
        return False
    if remaining_bits == 0:
        return True
    return digest[whole_bytes] >> (8 - remaining_bits) == 0
