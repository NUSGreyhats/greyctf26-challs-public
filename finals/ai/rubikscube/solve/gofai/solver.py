"""Observation-only GOFAI controller for the masked 2x2x2 service."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Sequence

try:
    from client import ChallengeClient, ChallengeResponse, code_to_observation
    from gofai.cases import (
        DIRECT_RESEARCH_PBL_ALGORITHMS,
        OLL_ALGORITHMS,
        PBL_ALGORITHMS,
        RESEARCH_OLL_ALGORITHMS,
        RESEARCH_PBL_ALGORITHMS,
    )
    from gofai.frame import (
        FACE_BITS,
        LEGAL_MOVES,
        Frame,
        first_solved_face,
        frame_for_down_face,
        inverse,
        turn_power,
    )
    from gofai.probes import FIRST_FACE_PROBES, Probe
except ModuleNotFoundError:  # pragma: no cover - package import path
    from ..client import ChallengeClient, ChallengeResponse, code_to_observation
    from .cases import (
        DIRECT_RESEARCH_PBL_ALGORITHMS,
        OLL_ALGORITHMS,
        PBL_ALGORITHMS,
        RESEARCH_OLL_ALGORITHMS,
        RESEARCH_PBL_ALGORITHMS,
    )
    from .frame import (
        FACE_BITS,
        LEGAL_MOVES,
        Frame,
        first_solved_face,
        frame_for_down_face,
        inverse,
        turn_power,
    )
    from .probes import FIRST_FACE_PROBES, Probe


MoveToken = str

SOLVED_MASK = 0b111111
FIRST_FACE_MOVE_CAP = 20_000
STAGE_NAMES: tuple[str, ...] = ("FIRST_FACE", "OPPOSITE_ORIENTATION", "LAYER_PERMUTATION")
STAGE_MASKS: tuple[int, ...] = (0, 0, SOLVED_MASK)
WORST_CASE_MOVES = 25_000


@dataclass(frozen=True, slots=True)
class StageResult:
    name: str
    required_mask: int
    skipped: bool
    moves_used: int
    final_mask: int


class GofaiSolver:
    def __init__(
        self,
        client: ChallengeClient,
        initial_mask: int,
        *,
        deadline_seconds: float | None = None,
    ) -> None:
        self.client = client
        self.phase = "INIT"
        self.mask = initial_mask
        self.stage_index = 0
        self.macro_no = 0
        self.move_count = 0
        self.deadline = None if deadline_seconds is None else time.monotonic() + deadline_seconds
        self.moves: list[MoveToken] = []
        self.observation_codes: list[int] = []
        self.stage_results: list[StageResult] = []
        self.last_response = ChallengeResponse((), state_code=initial_mask, solved=initial_mask == SOLVED_MASK)
        self.frame: Frame | None = None

    def run(self) -> tuple[MoveToken, ...]:
        if self.mask == SOLVED_MASK:
            self.phase = "SOLVED"
            return ()

        self.stage_index = 0
        first_face = self._acquire_first_face()
        frame = frame_for_down_face(first_face)
        self.frame = frame
        if self._is_solved():
            return tuple(self.moves)

        self.stage_index = 1
        self._orient_opposite_face(frame)
        if self._is_solved():
            return tuple(self.moves)

        self.stage_index = 2
        self._permute_layers(frame)
        if not self._is_solved():
            raise RuntimeError(f"GOFAI decision tree finished without SOLVED; final mask={self.mask:#04x}")
        self.phase = "SOLVED"
        return tuple(self.moves)

    def _acquire_first_face(self) -> str:
        self.phase = "FIRST_FACE"
        before = self.move_count
        existing = first_solved_face(self.mask)
        if existing is not None:
            self.stage_results.append(
                StageResult("FIRST_FACE", FACE_BITS[existing], True, 0, self.mask)
            )
            return existing

        for probe in FIRST_FACE_PROBES:
            found = self._try_first_face_probe(probe)
            if found is not None:
                self.stage_results.append(
                    StageResult("FIRST_FACE", FACE_BITS[found], False, self.move_count - before, self.mask)
                )
                return found
            if self.move_count - before > FIRST_FACE_MOVE_CAP:
                break

        raise RuntimeError(f"GOFAI failed to acquire a solved face within {FIRST_FACE_MOVE_CAP} moves")

    def _try_first_face_probe(self, probe: Probe) -> str | None:
        applied: list[MoveToken] = []
        for move in probe.moves:
            self._apply(move)
            applied.append(move)
            if self._is_solved():
                return first_solved_face(self.mask)
            face = first_solved_face(self.mask)
            if face is not None:
                return face
        self._apply_many(inverse(applied))
        return None

    def _orient_opposite_face(self, frame: Frame) -> None:
        self.phase = "OPPOSITE_ORIENTATION"
        before = self.move_count
        target = frame.down_bit | frame.up_bit
        if self.mask & target == target:
            self.stage_results.append(StageResult("OPPOSITE_ORIENTATION", target, True, 0, self.mask))
            return

        for candidate in self._oll_candidates(frame):
            if self._try_candidate(candidate, target_mask=target, preserve_mask=frame.down_bit):
                self.stage_results.append(
                    StageResult("OPPOSITE_ORIENTATION", target, False, self.move_count - before, self.mask)
                )
                return

        raise RuntimeError(f"GOFAI OLL probes exhausted; mask={self.mask:#04x} target={target:#04x}")

    def _permute_layers(self, frame: Frame) -> None:
        self.phase = "LAYER_PERMUTATION"
        before = self.move_count
        if self._is_solved():
            self.stage_results.append(StageResult("LAYER_PERMUTATION", SOLVED_MASK, True, 0, self.mask))
            return

        for candidate in self._pbl_candidates(frame):
            if self._try_candidate(candidate, target_mask=SOLVED_MASK, preserve_mask=frame.down_bit | frame.up_bit):
                self.stage_results.append(
                    StageResult("LAYER_PERMUTATION", SOLVED_MASK, False, self.move_count - before, self.mask)
                )
                return

        raise RuntimeError(f"GOFAI PBL probes exhausted without SOLVED; mask={self.mask:#04x}")

    def _oll_candidates(self, frame: Frame) -> tuple[tuple[MoveToken, ...], ...]:
        candidates: list[tuple[MoveToken, ...]] = []
        for auf in range(4):
            prefix = turn_power("U", auf)
            for algorithm in OLL_ALGORITHMS + RESEARCH_OLL_ALGORITHMS:
                candidates.append(frame.map_moves(prefix + algorithm.moves))
        return tuple(candidates)

    def _pbl_candidates(self, frame: Frame) -> tuple[tuple[MoveToken, ...], ...]:
        candidates: list[tuple[MoveToken, ...]] = []
        for u_adjust in range(4):
            for d_adjust in range(4):
                prefix = turn_power("U", u_adjust) + turn_power("D", d_adjust)
                for algorithm in PBL_ALGORITHMS + RESEARCH_PBL_ALGORITHMS:
                    relative = prefix + algorithm.moves
                    candidates.append(frame.map_moves(relative))
        for algorithm in DIRECT_RESEARCH_PBL_ALGORITHMS:
            candidates.append(frame.map_moves(algorithm.moves))
        return tuple(candidates)

    def _try_candidate(self, moves: Sequence[MoveToken], *, target_mask: int, preserve_mask: int) -> bool:
        before_mask = self.mask
        self._apply_many(moves)
        if self._is_solved() or self.mask & target_mask == target_mask:
            return True
        if self.mask & preserve_mask != preserve_mask:
            self._apply_many(inverse(moves))
            if self.mask != before_mask:
                raise RuntimeError(
                    f"GOFAI undo failed in phase {self.phase!r}: before={before_mask:#04x} after={self.mask:#04x}"
                )
            return False
        self._apply_many(inverse(moves))
        if self.mask != before_mask:
            raise RuntimeError(
                f"GOFAI undo failed in phase {self.phase!r}: before={before_mask:#04x} after={self.mask:#04x}"
            )
        return False

    def _apply_many(self, moves: Sequence[MoveToken]) -> None:
        for move in moves:
            self._apply(move)
            if self._is_solved():
                return

    def _apply(self, move: MoveToken) -> ChallengeResponse:
        if move not in LEGAL_MOVES:
            raise ValueError(f"illegal GOFAI move token: {move!r}")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError(f"GOFAI deadline exceeded in phase {self.phase!r}")

        response = self.client.apply_move(move)
        self.last_response = response
        self.move_count += 1
        self.macro_no = self.move_count
        self.moves.append(move)
        self.mask = _mask_from_response(response)
        self.observation_codes.append(self.mask)
        if response.failed:
            raise RuntimeError("Challenge failed while applying GOFAI moves.")
        return response

    def _is_solved(self) -> bool:
        if self.last_response.solved or self.mask == SOLVED_MASK:
            self.phase = "SOLVED"
            self.mask = SOLVED_MASK
            return True
        return False


def _mask_from_response(response: ChallengeResponse) -> int:
    if response.solved:
        return SOLVED_MASK
    if response.trace_codes:
        return response.trace_codes[-1]
    if response.state_code is not None:
        return response.state_code
    return 0


def observation_from_mask(mask: int) -> dict[str, bool]:
    return code_to_observation(mask)


__all__ = [
    "FIRST_FACE_MOVE_CAP",
    "GofaiSolver",
    "LEGAL_MOVES",
    "SOLVED_MASK",
    "STAGE_MASKS",
    "STAGE_NAMES",
    "StageResult",
    "WORST_CASE_MOVES",
    "inverse",
    "observation_from_mask",
]
