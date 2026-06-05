from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .models import LedgerEntryView, LedgerView, TangoAttemptView, TangoCell, TangoGrid, TangoStatus
from .repository import (
    AWARD_DOLLARS,
    FLAG_COST_DOLLARS,
    PLAY_COST_DOLLARS,
    ValidationDatabaseError,
    _copy_grid,
    _ledger_status_for_attempt_status,
    _puzzle_view,
    _region_for_lock,
    _validate_region,
    validate_full_grid,
)

@dataclass(slots=True)
class AttemptRecord:
    attempt_id: UUID
    user_id: int
    status: str
    grid: TangoGrid
    lock_order: list[str]
    created_at: datetime
    updated_at: datetime

@dataclass(slots=True)
class LedgerRecord:
    entry_id: UUID
    attempt_id: UUID
    user_id: int
    status: str
    amount: int
    created_at: datetime
    updated_at: datetime

@dataclass(slots=True)
class ValidationMetricRecord:
    attempt_id: UUID
    user_id: int
    validated_regions: int
    latest_lock_key: str
    latest_imbalance: int
    audit_row_count: int
    created_at: datetime
    updated_at: datetime

class InMemoryTangoRepository:
    def __init__(self) -> None:
        self._attempts: dict[UUID, AttemptRecord] = {}
        self._ledger_entries: dict[UUID, LedgerRecord] = {}
        self._audit_rows: list[tuple[UUID, int, str, list[TangoCell]]] = []
        self._validation_metrics: dict[UUID, ValidationMetricRecord] = {}
        self.raise_validation_database_error = False
        self.raise_unexpected_validation_error = False

    def get_status(self, user_id: int) -> TangoStatus:
        return TangoStatus(
            puzzle=_puzzle_view(),
            ledger=self.get_ledger(user_id),
            latest_attempt_state=self._latest_attempt_state(user_id),
        )

    def get_ledger(self, user_id: int) -> LedgerView:
        entries = [
            LedgerEntryView(
                entry_id=entry.entry_id,
                attempt_id=entry.attempt_id,
                status=entry.status,
                amount=entry.amount,
            )
            for entry in self._ledger_entries.values()
            if entry.user_id == user_id
        ]
        committed = sum(entry.amount for entry in entries if entry.status == "COMMITTED")
        pending = sum(entry.amount for entry in entries if entry.status == "PENDING")
        fees = sum(entry.amount for entry in entries if entry.status == "PLAY_FEE")
        return LedgerView(
            currency_symbol="$",
            spendable_dollars=committed + pending + fees,
            committed_dollars=committed,
            pending_dollars=pending,
            play_cost_dollars=PLAY_COST_DOLLARS,
            flag_cost_dollars=FLAG_COST_DOLLARS,
            entries=entries,
        )

    def create_attempt_with_pending_entry(
        self,
        *,
        user_id: int,
        attempt_id: UUID,
        entry_id: UUID,
        grid: TangoGrid,
        lock_order: list[str],
    ) -> None:
        now = datetime.now(UTC)
        self._attempts[attempt_id] = AttemptRecord(
            attempt_id=attempt_id,
            user_id=user_id,
            status="pending",
            grid=_copy_grid(grid),
            lock_order=list(lock_order),
            created_at=now,
            updated_at=now,
        )
        self._ledger_entries[entry_id] = LedgerRecord(
            entry_id=entry_id,
            attempt_id=attempt_id,
            user_id=user_id,
            status="PENDING",
            amount=AWARD_DOLLARS,
            created_at=now,
            updated_at=now,
        )

    def validate_attempt(
        self,
        *,
        user_id: int,
        attempt_id: UUID,
        grid: TangoGrid,
        lock_order: list[str],
    ) -> None:
        if self.raise_unexpected_validation_error:
            raise RuntimeError("unexpected validation failure")
        if self.raise_validation_database_error:
            self.raise_validation_database_error = False
            raise ValidationDatabaseError("validation transaction failed")

        self._set_attempt_state(attempt_id, "validating")
        for index, lock_key in enumerate(lock_order, start=1):
            self._audit_rows.append((attempt_id, user_id, lock_key, _region_for_lock(grid, lock_key)))
            imbalance = _validate_region(grid, lock_key)
            self._set_validation_metrics(
                attempt_id=attempt_id,
                user_id=user_id,
                validated_regions=index,
                latest_lock_key=lock_key,
                latest_imbalance=imbalance,
            )
        validate_full_grid(grid)

    def set_attempt_status(self, attempt_id: UUID, entry_id: UUID, status: str) -> None:
        now = datetime.now(UTC)
        record = self._attempts[attempt_id]
        record.status = status
        record.updated_at = now

        ledger_record = self._ledger_entries[entry_id]
        ledger_record.status = _ledger_status_for_attempt_status(status)
        ledger_record.updated_at = now

    def record_play_fee(self, *, attempt_id: UUID, user_id: int) -> None:
        now = datetime.now(UTC)
        entry_id = uuid4()
        self._ledger_entries[entry_id] = LedgerRecord(
            entry_id=entry_id,
            attempt_id=attempt_id,
            user_id=user_id,
            status="PLAY_FEE",
            amount=-PLAY_COST_DOLLARS,
            created_at=now,
            updated_at=now,
        )

    def refresh_ledger(self, user_id: int) -> LedgerView:
        for record in self._ledger_entries.values():
            if record.user_id == user_id and record.status == "PENDING":
                record.status = "ROLLED_BACK"
                record.updated_at = datetime.now(UTC)
        return self.get_ledger(user_id)

    def get_attempt(self, user_id: int, attempt_id: UUID) -> TangoAttemptView | None:
        record = self._attempts.get(attempt_id)
        if record is None or record.user_id != user_id:
            return None
        ledger_status = next(
            (
                entry.status
                for entry in self._ledger_entries.values()
                if entry.attempt_id == attempt_id and entry.amount > 0
            ),
            None,
        )
        return TangoAttemptView(
            attempt_id=record.attempt_id,
            status=record.status,
            lock_order=list(record.lock_order),
            ledger_status=ledger_status,
        )

    def reset(self, user_id: int) -> TangoStatus:
        attempt_ids = {
            attempt_id
            for attempt_id, record in self._attempts.items()
            if record.user_id == user_id
        }
        for attempt_id in attempt_ids:
            self._attempts.pop(attempt_id, None)
        for entry_id, record in list(self._ledger_entries.items()):
            if record.user_id == user_id:
                self._ledger_entries.pop(entry_id, None)
        self._audit_rows = [row for row in self._audit_rows if row[1] != user_id]
        self._validation_metrics = {
            attempt_id: record
            for attempt_id, record in self._validation_metrics.items()
            if record.user_id != user_id
        }
        return self.get_status(user_id)

    def _set_attempt_state(self, attempt_id: UUID, status: str) -> None:
        record = self._attempts[attempt_id]
        record.status = status
        record.updated_at = datetime.now(UTC)

    def _set_validation_metrics(
        self,
        *,
        attempt_id: UUID,
        user_id: int,
        validated_regions: int,
        latest_lock_key: str,
        latest_imbalance: int,
    ) -> None:
        now = datetime.now(UTC)
        existing = self._validation_metrics.get(attempt_id)
        created_at = now if existing is None else existing.created_at
        self._validation_metrics[attempt_id] = ValidationMetricRecord(
            attempt_id=attempt_id,
            user_id=user_id,
            validated_regions=validated_regions,
            latest_lock_key=latest_lock_key,
            latest_imbalance=latest_imbalance,
            audit_row_count=sum(
                1 for audit_attempt_id, _, _, _ in self._audit_rows if audit_attempt_id == attempt_id
            ),
            created_at=created_at,
            updated_at=now,
        )

    def _latest_attempt_state(self, user_id: int) -> str:
        latest = max(
            (record for record in self._attempts.values() if record.user_id == user_id),
            key=lambda record: record.created_at,
            default=None,
        )
        return "idle" if latest is None else latest.status
