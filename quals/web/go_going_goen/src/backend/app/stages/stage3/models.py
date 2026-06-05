from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

TangoCell = Literal[0, 1, 2]
TangoGrid = list[list[TangoCell]]

@dataclass(frozen=True, slots=True)
class FixedCell:
    row: int
    col: int
    value: TangoCell

@dataclass(frozen=True, slots=True)
class PuzzleView:
    size: int
    values: dict[str, int]
    fixed_cells: list[FixedCell]
    initial_grid: TangoGrid

@dataclass(frozen=True, slots=True)
class LedgerEntryView:
    entry_id: UUID
    attempt_id: UUID
    status: str
    amount: int

@dataclass(frozen=True, slots=True)
class LedgerView:
    currency_symbol: str
    spendable_dollars: int
    committed_dollars: int
    pending_dollars: int
    play_cost_dollars: int
    flag_cost_dollars: int
    entries: list[LedgerEntryView]

@dataclass(frozen=True, slots=True)
class TangoStatus:
    puzzle: PuzzleView
    ledger: LedgerView
    latest_attempt_state: str

@dataclass(frozen=True, slots=True)
class TangoSubmitResult:
    result: str
    dollars_awarded: int
    attempt_id: UUID

@dataclass(frozen=True, slots=True)
class TangoAttemptView:
    attempt_id: UUID
    status: str
    lock_order: list[str]
    ledger_status: str | None

@dataclass(frozen=True, slots=True)
class FlagPurchaseResult:
    result: str
    flag: str
