from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class QueenPosition:
    row: int
    col: int

@dataclass(frozen=True, slots=True)
class SubmissionState:
    status: str
    progress_pct: int
    last_result: str | None
    last_submitted_at: datetime | None

@dataclass(frozen=True, slots=True)
class BoardSnapshot:
    size: int
    queens: list[QueenPosition]
    total_queens: int
    submission: SubmissionState

@dataclass(frozen=True, slots=True)
class SubmitResult:
    result: str
    total_queens: int
