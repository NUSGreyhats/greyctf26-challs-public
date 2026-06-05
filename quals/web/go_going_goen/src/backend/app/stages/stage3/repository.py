from __future__ import annotations

import hashlib
import json
import random
from typing import Protocol
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.db.session import Database

from .models import (
    FixedCell,
    LedgerEntryView,
    LedgerView,
    PuzzleView,
    TangoAttemptView,
    TangoCell,
    TangoGrid,
    TangoStatus,
)

GRID_SIZE = 6
AWARD_DOLLARS = 100
PLAY_COST_DOLLARS = 100
FLAG_COST_DOLLARS = 1000
SOLUTION_GRID: TangoGrid = [
    [1, 1, 2, 1, 2, 2],
    [1, 2, 2, 1, 1, 2],
    [2, 1, 1, 2, 2, 1],
    [1, 2, 1, 2, 1, 2],
    [2, 1, 2, 1, 2, 1],
    [2, 2, 1, 2, 1, 1],
]
FIXED_CELLS = [
    FixedCell(row=0, col=0, value=1),
    FixedCell(row=0, col=2, value=2),
    FixedCell(row=1, col=5, value=2),
    FixedCell(row=2, col=0, value=2),
    FixedCell(row=3, col=3, value=2),
    FixedCell(row=4, col=4, value=2),
    FixedCell(row=5, col=1, value=2),
    FixedCell(row=5, col=5, value=1),
]
INITIAL_GRID: TangoGrid = [
    [
        cell if any(clue.row == row and clue.col == col for clue in FIXED_CELLS) else 0
        for col, cell in enumerate(line)
    ]
    for row, line in enumerate(SOLUTION_GRID)
]

class InvalidTangoGrid(RuntimeError):
    pass

class ValidationDatabaseError(RuntimeError):
    pass

class TangoProgressGateway(Protocol):
    def mark_stage3_cleared(self, user_id: int) -> None: ...

    def is_stage3_cleared(self, user_id: int) -> bool: ...

class TangoRepository(Protocol):
    def get_status(self, user_id: int) -> TangoStatus: ...

    def get_ledger(self, user_id: int) -> LedgerView: ...

    def create_attempt_with_pending_entry(
        self,
        *,
        user_id: int,
        attempt_id: UUID,
        entry_id: UUID,
        grid: TangoGrid,
        lock_order: list[str],
    ) -> None: ...

    def validate_attempt(
        self,
        *,
        user_id: int,
        attempt_id: UUID,
        grid: TangoGrid,
        lock_order: list[str],
    ) -> None: ...

    def set_attempt_status(
        self, attempt_id: UUID, entry_id: UUID, status: str
    ) -> None: ...

    def record_play_fee(self, *, attempt_id: UUID, user_id: int) -> None: ...

    def refresh_ledger(self, user_id: int) -> LedgerView: ...

    def get_attempt(
        self, user_id: int, attempt_id: UUID
    ) -> TangoAttemptView | None: ...

    def reset(self, user_id: int) -> TangoStatus: ...

class SqlTangoRepository:
    def __init__(self, db) -> None:
        self._db = db

    def get_status(self, user_id: int) -> TangoStatus:
        self._ensure_state(user_id)
        return TangoStatus(
            puzzle=_puzzle_view(),
            ledger=self.get_ledger(user_id),
            latest_attempt_state=self._latest_attempt_state(user_id),
        )

    def get_ledger(self, user_id: int) -> LedgerView:
        rows = self._db.fetch_all(
            """
            SELECT entry_id, attempt_id, status, amount
            FROM tango_ledger_entries
            WHERE user_id = %s
            ORDER BY created_at ASC
            """,
            [user_id],
        )
        entries = [
            LedgerEntryView(
                entry_id=row["entry_id"],
                attempt_id=row["attempt_id"],
                status=str(row["status"]),
                amount=int(row["amount"]),
            )
            for row in rows
        ]
        committed = sum(
            entry.amount for entry in entries if entry.status == "COMMITTED"
        )
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
        self._ensure_state(user_id)
        self._db.execute(
            """
            INSERT INTO tango_attempts (attempt_id, user_id, status, grid_payload, lock_order)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            [attempt_id, user_id, "pending", _json(grid), _json(lock_order)],
        )
        self._db.execute(
            """
            INSERT INTO tango_ledger_entries (entry_id, attempt_id, user_id, status, amount)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [entry_id, attempt_id, user_id, "PENDING", AWARD_DOLLARS],
        )
        self._db.commit()

    def validate_attempt(
        self,
        *,
        user_id: int,
        attempt_id: UUID,
        grid: TangoGrid,
        lock_order: list[str],
    ) -> None:
        try:
            with psycopg.connect(
                settings.database_url,
                row_factory=dict_row,
                autocommit=False,
                prepare_threshold=None,
            ) as connection:
                Database.configure_connection(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE tango_attempts
                        SET status = 'validating', updated_at = now()
                        WHERE attempt_id = %s AND user_id = %s
                        """,
                        [attempt_id, user_id],
                    )
                    for index, lock_key in enumerate(lock_order):
                        cursor.execute(
                            """
                            SELECT lock_key
                            FROM tango_validation_locks
                            WHERE lock_key = %s
                            FOR UPDATE
                            """,
                            [lock_key],
                        )
                        imbalance = _validate_region(grid, lock_key)
                        cursor.execute(
                            """
                            INSERT INTO tango_region_audit (attempt_id, user_id, lock_key, region_payload)
                            VALUES (%s, %s, %s, %s::jsonb)
                            """,
                            [
                                attempt_id,
                                user_id,
                                lock_key,
                                _json(_region_for_lock(grid, lock_key)),
                            ],
                        )
                        self._record_validation_metrics(
                            cursor,
                            user_id=user_id,
                            attempt_id=attempt_id,
                            lock_key=lock_key,
                            imbalance=imbalance,
                            validated_regions=index + 1,
                        )
                    validate_full_grid(grid)
                connection.commit()
        except InvalidTangoGrid:
            raise
        except psycopg.Error as exc:
            raise ValidationDatabaseError("validation transaction failed") from exc

    def set_attempt_status(self, attempt_id: UUID, entry_id: UUID, status: str) -> None:
        self._db.execute(
            """
            UPDATE tango_attempts
            SET status = %s, updated_at = now()
            WHERE attempt_id = %s
            """,
            [status, attempt_id],
        )
        self._db.execute(
            """
            UPDATE tango_ledger_entries
            SET status = %s, updated_at = now()
            WHERE entry_id = %s
            """,
            [_ledger_status_for_attempt_status(status), entry_id],
        )

    def record_play_fee(self, *, attempt_id: UUID, user_id: int) -> None:
        self._db.execute(
            """
            INSERT INTO tango_ledger_entries (entry_id, attempt_id, user_id, status, amount)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [uuid4(), attempt_id, user_id, "PLAY_FEE", -PLAY_COST_DOLLARS],
        )

    def refresh_ledger(self, user_id: int) -> LedgerView:
        self._db.execute(
            """
            UPDATE tango_ledger_entries
            SET status = 'ROLLED_BACK', updated_at = now()
            WHERE user_id = %s AND status = 'PENDING'
            """,
            [user_id],
        )
        return self.get_ledger(user_id)

    def get_attempt(self, user_id: int, attempt_id: UUID) -> TangoAttemptView | None:
        row = self._db.fetch_one(
            """
            SELECT a.attempt_id, a.status, a.lock_order, l.status AS ledger_status
            FROM tango_attempts a
            LEFT JOIN tango_ledger_entries l ON l.attempt_id = a.attempt_id AND l.amount > 0
            WHERE a.user_id = %s AND a.attempt_id = %s
            """,
            [user_id, attempt_id],
        )
        if row is None:
            return None
        return TangoAttemptView(
            attempt_id=row["attempt_id"],
            status=str(row["status"]),
            lock_order=_loads_list(row["lock_order"]),
            ledger_status=(
                str(row["ledger_status"]) if row["ledger_status"] is not None else None
            ),
        )

    def reset(self, user_id: int) -> TangoStatus:
        self._db.execute("DELETE FROM tango_validation_metrics WHERE user_id = %s", [user_id])
        self._db.execute("DELETE FROM tango_region_audit WHERE user_id = %s", [user_id])
        self._db.execute(
            "DELETE FROM tango_ledger_entries WHERE user_id = %s", [user_id]
        )
        self._db.execute("DELETE FROM tango_attempts WHERE user_id = %s", [user_id])
        self._db.execute(
            """
            INSERT INTO tango_state (user_id)
            VALUES (%s)
            ON CONFLICT (user_id) DO UPDATE
            SET puzzle_id = 'default', updated_at = now()
            """,
            [user_id],
        )
        return self.get_status(user_id)

    def _ensure_state(self, user_id: int) -> None:
        self._db.execute(
            """
            INSERT INTO tango_state (user_id)
            VALUES (%s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            [user_id],
        )

    def _latest_attempt_state(self, user_id: int) -> str:
        row = self._db.fetch_one(
            """
            SELECT status
            FROM tango_attempts
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [user_id],
        )
        return "idle" if row is None else str(row["status"])

    def _record_validation_metrics(
        self,
        cursor,
        *,
        user_id: int,
        attempt_id: UUID,
        lock_key: str,
        imbalance: int,
        validated_regions: int,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO tango_validation_metrics (
                attempt_id,
                user_id,
                validated_regions,
                latest_lock_key,
                latest_imbalance,
                audit_row_count
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                (
                    SELECT COUNT(*)
                    FROM tango_region_audit
                    WHERE attempt_id = %s
                )
            )
            ON CONFLICT (attempt_id) DO UPDATE
            SET validated_regions = EXCLUDED.validated_regions,
                latest_lock_key = EXCLUDED.latest_lock_key,
                latest_imbalance = EXCLUDED.latest_imbalance,
                audit_row_count = EXCLUDED.audit_row_count,
                updated_at = now()
            """,
            [
                attempt_id,
                user_id,
                validated_regions,
                lock_key,
                imbalance,
                attempt_id,
            ],
        )
        cursor.execute(
            """
            SELECT validated_regions, audit_row_count
            FROM tango_validation_metrics
            WHERE attempt_id = %s
            """,
            [attempt_id],
        )
        cursor.fetchone()

def derive_lock_order(grid: TangoGrid) -> list[str]:
    digest = hashlib.sha256(_json(grid).encode()).digest()
    seed = int.from_bytes(digest[:8], "big")
    rng = random.Random(seed)
    keys = [f"row_balance:{index}" for index in range(1, 7)]
    rng.shuffle(keys)
    return keys

def validate_full_grid(grid: TangoGrid) -> None:
    _validate_shape(grid)
    for clue in FIXED_CELLS:
        if grid[clue.row][clue.col] != clue.value:
            raise InvalidTangoGrid("Grid rejected.")
    for line in grid:
        _validate_complete_balanced_line(line)
    for col in range(GRID_SIZE):
        _validate_complete_balanced_line([grid[row][col] for row in range(GRID_SIZE)])

def _validate_region(grid: TangoGrid, lock_key: str) -> int:
    row_index = int(lock_key.split(":")[1]) - 1
    return _row_imbalance(grid[row_index])

def _validate_shape(grid: TangoGrid) -> None:
    if len(grid) != GRID_SIZE or any(len(row) != GRID_SIZE for row in grid):
        raise InvalidTangoGrid("Grid rejected.")
    if any(cell not in (0, 1, 2) for row in grid for cell in row):
        raise InvalidTangoGrid("Grid rejected.")

def _validate_complete_balanced_line(line: list[TangoCell]) -> None:
    if any(cell == 0 for cell in line):
        raise InvalidTangoGrid("Grid rejected.")
    _validate_no_three_adjacent(line)
    if line.count(1) != GRID_SIZE // 2 or line.count(2) != GRID_SIZE // 2:
        raise InvalidTangoGrid("Grid rejected.")

def _validate_no_three_adjacent(line: list[TangoCell]) -> None:
    for left, middle, right in zip(line, line[1:], line[2:]):
        if left != 0 and left == middle == right:
            raise InvalidTangoGrid("Grid rejected.")

def _row_imbalance(row: list[TangoCell]) -> int:
    return row.count(1) - row.count(2)

def _region_for_lock(grid: TangoGrid, lock_key: str) -> list[TangoCell]:
    return list(grid[int(lock_key.split(":")[1]) - 1])

def _puzzle_view() -> PuzzleView:
    return PuzzleView(
        size=GRID_SIZE,
        values={"empty": 0, "sun": 1, "moon": 2},
        fixed_cells=list(FIXED_CELLS),
        initial_grid=_copy_grid(INITIAL_GRID),
    )

def _copy_grid(grid: TangoGrid) -> TangoGrid:
    return [list(row) for row in grid]

def _json(payload: object) -> str:
    return json.dumps(payload)

def _loads_list(payload: object) -> list[str]:
    if isinstance(payload, str):
        loaded = json.loads(payload)
    else:
        loaded = payload
    return [str(item) for item in loaded]

_ATTEMPT_TO_LEDGER_STATUS: dict[str, str] = {
    "accepted": "COMMITTED",
    "rejected": "ROLLED_BACK",
    "validating": "PENDING",
    "pending": "PENDING",
}

def _ledger_status_for_attempt_status(status: str) -> str:
    return _ATTEMPT_TO_LEDGER_STATUS.get(status, "PENDING")
