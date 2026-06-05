from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from app.observability.metrics import get_metrics

from .models import (
    FlagPurchaseResult,
    LedgerView,
    TangoAttemptView,
    TangoGrid,
    TangoStatus,
    TangoSubmitResult,
)
from .repository import (
    AWARD_DOLLARS,
    FLAG_COST_DOLLARS,
    InvalidTangoGrid,
    TangoProgressGateway,
    TangoRepository,
    ValidationDatabaseError,
    derive_lock_order,
)

class InvalidGridError(RuntimeError):
    def __init__(self, attempt_id: UUID, message: str = "Grid rejected.") -> None:
        super().__init__(message)
        self.attempt_id = attempt_id

class TangoValidationError(RuntimeError):
    def __init__(
        self, attempt_id: UUID, message: str = "Validation could not complete."
    ) -> None:
        super().__init__(message)
        self.attempt_id = attempt_id

class NotEnoughCreditsError(RuntimeError):
    def __init__(self, message: str = "Not enough credits.") -> None:
        super().__init__(message)

class TooManySubmissionsError(RuntimeError):
    def __init__(self, message: str = "Too many submissions.") -> None:
        super().__init__(message)

class SubmissionGate:
    def __init__(self, *, capacity: int = 2) -> None:
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
                stage="stage3",
                outcome="timeout",
                duration_seconds=time.perf_counter() - started,
            )
            raise TooManySubmissionsError() from exc
        get_metrics().observe_gate_wait(
            stage="stage3",
            outcome="acquired",
            duration_seconds=time.perf_counter() - started,
        )

        try:
            yield
        finally:
            semaphore.release()

    def available_permits(self, user_id: int) -> int:
        return self._semaphores[user_id]._value

    @property
    def capacity(self) -> int:
        return self._capacity

class TangoService:
    def __init__(
        self,
        *,
        repository: TangoRepository,
        progress_gateway: TangoProgressGateway,
        final_flag: str,
    ) -> None:
        self._repository = repository
        self._progress_gateway = progress_gateway
        self._final_flag = final_flag

    def get_status(self, user_id: int) -> TangoStatus:
        return self._repository.get_status(user_id)

    def get_ledger(self, user_id: int) -> LedgerView:
        return self._repository.get_ledger(user_id)

    def refresh_ledger(self, user_id: int) -> LedgerView:
        return self._repository.refresh_ledger(user_id)

    def submit_grid(self, user_id: int, grid: TangoGrid) -> TangoSubmitResult:
        attempt_id = uuid4()
        entry_id = uuid4()
        lock_order = derive_lock_order(grid)
        self._repository.create_attempt_with_pending_entry(
            user_id=user_id,
            attempt_id=attempt_id,
            entry_id=entry_id,
            grid=grid,
            lock_order=lock_order,
        )

        started = time.perf_counter()
        outcome = "accepted"
        try:
            try:
                self._repository.validate_attempt(
                    user_id=user_id,
                    attempt_id=attempt_id,
                    grid=grid,
                    lock_order=lock_order,
                )
            except InvalidTangoGrid as exc:
                outcome = "rejected"
                self._repository.set_attempt_status(attempt_id, entry_id, "rejected")
                raise InvalidGridError(attempt_id) from exc
            except ValidationDatabaseError as exc:
                outcome = "crashed"
                self._repository.set_attempt_status(attempt_id, entry_id, "crashed")
                raise TangoValidationError(attempt_id) from exc

            self._repository.set_attempt_status(attempt_id, entry_id, "accepted")
            self._repository.record_play_fee(attempt_id=attempt_id, user_id=user_id)
            return TangoSubmitResult(
                result="accepted", dollars_awarded=AWARD_DOLLARS, attempt_id=attempt_id
            )
        finally:
            get_metrics().observe_stage_submit(
                stage="stage3",
                outcome=outcome,
                duration_seconds=time.perf_counter() - started,
            )

    def buy_flag(self, user_id: int) -> FlagPurchaseResult:
        # Idempotent for the player's benefit: once stage 3 is cleared we just
        # hand the flag straight back on repeat calls. Folks bookmark this URL
        # and reopen it days later expecting the flag to still be there, so
        # making them re-run the whole purchase flow (and risk a transient
        # failure on a stage they've already beaten) would be a nasty surprise.
        if self._progress_gateway.is_stage3_cleared(user_id):
            return FlagPurchaseResult(result="win", flag=self._final_flag)
        ledger = self._repository.get_ledger(user_id)
        if ledger.spendable_dollars < FLAG_COST_DOLLARS:
            raise NotEnoughCreditsError()
        self._progress_gateway.mark_stage3_cleared(user_id)
        return FlagPurchaseResult(result="win", flag=self._final_flag)

    def get_attempt(self, user_id: int, attempt_id: UUID) -> TangoAttemptView | None:
        return self._repository.get_attempt(user_id, attempt_id)

    def reset(self, user_id: int) -> TangoStatus:
        return self._repository.reset(user_id)
