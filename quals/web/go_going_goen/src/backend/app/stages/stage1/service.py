from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from app.observability.metrics import get_metrics

from .constants import GUESS_GATE_CAPACITY, GUESS_LIMIT, RESET_COOLDOWN_SECONDS
from .models import GuessOutcome, PinpointStatus, PinpointUserState
from .repository import PinpointProgressGateway, PinpointRepository
from .wordbank import WORD_PATTERN, WordBank

class GuessLimitReached(Exception):
    pass

class InvalidGuess(Exception):
    pass

class TooManyGuessesError(RuntimeError):
    def __init__(self, message: str = "Too many guesses.") -> None:
        super().__init__(message)

class ResetCooldownError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Reset is on cooldown.")
        self.retry_after_seconds = retry_after_seconds

class GuessGate:
    def __init__(self, *, capacity: int = GUESS_GATE_CAPACITY) -> None:
        self._capacity = capacity
        self._semaphores: dict[int, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(capacity)
        )

    @asynccontextmanager
    async def acquire(self, user_id: int, timeout: float = 0.25):
        semaphore = self._semaphores[user_id]
        started = time.perf_counter()
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            get_metrics().observe_gate_wait(
                stage="stage1",
                outcome="timeout",
                duration_seconds=time.perf_counter() - started,
            )
            raise TooManyGuessesError() from exc
        get_metrics().observe_gate_wait(
            stage="stage1",
            outcome="acquired",
            duration_seconds=time.perf_counter() - started,
        )

        try:
            yield
        finally:
            semaphore.release()

    @property
    def capacity(self) -> int:
        return self._capacity

class ResetGate:
    def __init__(self, *, cooldown_seconds: int = RESET_COOLDOWN_SECONDS) -> None:
        self._cooldown_seconds = cooldown_seconds
        self._last_reset_at: dict[int, float] = {}

    def consume(self, user_id: int) -> None:
        now = time.monotonic()
        previous = self._last_reset_at.get(user_id)
        if previous is not None:
            elapsed = now - previous
            if elapsed < self._cooldown_seconds:
                retry_after = max(1, int(self._cooldown_seconds - elapsed))
                raise ResetCooldownError(retry_after)
        self._last_reset_at[user_id] = now

    @property
    def cooldown_seconds(self) -> int:
        return self._cooldown_seconds

class PinpointService:
    def __init__(
        self,
        *,
        repository: PinpointRepository,
        progress_gateway: PinpointProgressGateway,
        wordbank: WordBank,
        instance_seed: str,
    ) -> None:
        self._repository = repository
        self._progress_gateway = progress_gateway
        self._wordbank = wordbank
        self._instance_seed = instance_seed

    def get_status(self, user_id: int) -> PinpointStatus:
        state = self._ensure_user_state(user_id)
        return self._status_from_state(state)

    def submit_guess(self, user_id: int, guess: str) -> GuessOutcome:
        normalized_guess = self._normalize_guess(guess)
        state = self._ensure_user_state(user_id)

        if state.solved:
            self._progress_gateway.unlock_stage2(user_id)
            return GuessOutcome(result="correct")

        if not self._wordbank.contains(normalized_guess):
            raise InvalidGuess("Guesses must be in the wordlist")

        if state.guesses_used >= GUESS_LIMIT:
            raise GuessLimitReached

        is_correct = normalized_guess == state.puzzle_answer

        updated_state = self._repository.apply_guess(
            user_id=user_id,
            is_correct=is_correct,
            guess=normalized_guess,
        )

        if is_correct:
            self._progress_gateway.unlock_stage2(user_id)
            return GuessOutcome(result="correct")

        return GuessOutcome(
            result="wrong",
            guesses_used=updated_state.guesses_used,
            remaining_guesses=max(0, GUESS_LIMIT - updated_state.guesses_used),
        )

    def reset(self, user_id: int) -> PinpointStatus:
        state = self._ensure_user_state(user_id)
        next_answer = self._wordbank.rotated_answer(
            instance_seed=self._instance_seed,
            current_answer=state.puzzle_answer,
        )
        reset_state = self._repository.reset_user_state(
            state.user_id,
            puzzle_answer=next_answer,
        )
        return self._status_from_state(reset_state)

    def ensure_stage_row(self, user_id: int) -> PinpointUserState:
        return self._ensure_user_state(user_id)

    def _ensure_user_state(self, user_id: int) -> PinpointUserState:
        state = self._repository.fetch_user_state(user_id)
        if state:
            return state

        seeded = PinpointUserState(
            user_id=user_id,
            guesses_used=0,
            solved=False,
            puzzle_answer=self._wordbank.answer_for(
                instance_seed=self._instance_seed,
            ),
            last_result=None,
        )
        self._repository.create_user_state(seeded)
        return seeded

    @staticmethod
    def _normalize_guess(guess: str) -> str:
        candidate = guess.strip().lower()
        if not WORD_PATTERN.fullmatch(candidate):
            raise InvalidGuess("Guesses must be exactly 5 letters")
        return candidate

    def _status_from_state(self, state: PinpointUserState) -> PinpointStatus:
        return PinpointStatus(
            guesses_used=state.guesses_used,
            remaining_guesses=max(0, GUESS_LIMIT - state.guesses_used),
            solved=state.solved,
            last_result=state.last_result,
            recent_guesses=self._repository.fetch_recent_guesses(state.user_id),
        )
