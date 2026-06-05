from __future__ import annotations

import asyncio

import pytest

from app.stages.stage3.models import TangoGrid
from app.stages.stage3.repository import (
    AWARD_DOLLARS,
    FLAG_COST_DOLLARS,
    FIXED_CELLS,
    INITIAL_GRID,
    PLAY_COST_DOLLARS,
    SOLUTION_GRID,
    derive_lock_order,
)
from app.stages.stage3.service import (
    InvalidGridError,
    NotEnoughCreditsError,
    SubmissionGate,
    TangoService,
    TangoValidationError,
    TooManySubmissionsError,
)
from app.stages.stage3.testing import InMemoryTangoRepository


class ProgressGatewayStub:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.cleared: set[int] = set()

    def mark_stage3_cleared(self, user_id: int) -> None:
        self.calls.append(user_id)
        self.cleared.add(user_id)

    def is_stage3_cleared(self, user_id: int) -> bool:
        return user_id in self.cleared


FINAL_FLAG = "grey{stage3-final-flag}"


def build_service() -> tuple[TangoService, InMemoryTangoRepository, ProgressGatewayStub]:
    repository = InMemoryTangoRepository()
    progress = ProgressGatewayStub()
    service = TangoService(
        repository=repository,
        progress_gateway=progress,
        final_flag=FINAL_FLAG,
    )
    return service, repository, progress


def test_status_returns_integer_puzzle_and_ledger_fields() -> None:
    service, _, _ = build_service()

    status = service.get_status(7)

    assert status.puzzle.size == 6
    assert status.puzzle.values == {"empty": 0, "sun": 1, "moon": 2}
    assert status.puzzle.initial_grid == INITIAL_GRID
    assert status.puzzle.fixed_cells == FIXED_CELLS
    assert status.ledger.currency_symbol == "$"
    assert status.ledger.spendable_dollars == 0
    assert status.ledger.play_cost_dollars == PLAY_COST_DOLLARS
    assert status.ledger.flag_cost_dollars == FLAG_COST_DOLLARS
    assert status.latest_attempt_state == "idle"


def test_derive_lock_order_is_a_deterministic_permutation() -> None:
    expected_keys = {f"row_balance:{i}" for i in range(1, 7)}
    grid_a: TangoGrid = [list(row) for row in SOLUTION_GRID]  # type: ignore[list-item]
    grid_b: TangoGrid = [list(row) for row in SOLUTION_GRID]  # type: ignore[list-item]
    grid_b[0] = [2, 2, 1, 2, 1, 1]

    order_a = derive_lock_order(grid_a)
    order_b = derive_lock_order(grid_b)

    assert set(order_a) == expected_keys
    assert set(order_b) == expected_keys
    assert derive_lock_order(grid_a) == order_a
    assert order_a != order_b


def test_valid_solution_awards_committed_dollars_and_play_fee_nets_to_zero() -> None:
    service, repository, progress = build_service()

    result = service.submit_grid(11, SOLUTION_GRID)
    ledger = service.get_ledger(11)

    assert result.result == "accepted"
    assert result.dollars_awarded == AWARD_DOLLARS
    assert service.get_attempt(11, result.attempt_id).status == "accepted"
    assert ledger.committed_dollars == 100
    assert ledger.pending_dollars == 0
    assert ledger.spendable_dollars == 0
    assert [entry.amount for entry in ledger.entries] == [100, -100]
    assert [entry.status for entry in ledger.entries] == ["COMMITTED", "PLAY_FEE"]
    with pytest.raises(NotEnoughCreditsError):
        service.buy_flag(11)
    assert progress.calls == []
    assert repository.get_status(11).latest_attempt_state == "accepted"


def test_normal_invalid_grid_rolls_back_ledger_entry() -> None:
    service, _, _ = build_service()
    invalid_grid: TangoGrid = [list(row) for row in SOLUTION_GRID]  # type: ignore[list-item]
    invalid_grid[0][0] = 2

    with pytest.raises(InvalidGridError) as exc_info:
        service.submit_grid(3, invalid_grid)

    ledger = service.get_ledger(3)
    attempt = service.get_attempt(3, exc_info.value.attempt_id)
    assert attempt is not None
    assert attempt.status == "rejected"
    assert attempt.ledger_status == "ROLLED_BACK"
    assert ledger.spendable_dollars == 0
    assert ledger.entries[0].status == "ROLLED_BACK"


def test_validation_database_error_leaves_pending_credit_spendable() -> None:
    service, repository, _ = build_service()
    repository.raise_validation_database_error = True

    with pytest.raises(TangoValidationError) as exc_info:
        service.submit_grid(5, SOLUTION_GRID)

    ledger = service.get_ledger(5)
    attempt = service.get_attempt(5, exc_info.value.attempt_id)
    assert attempt is not None
    assert attempt.status == "crashed"
    assert attempt.ledger_status == "PENDING"
    assert ledger.pending_dollars == 100
    assert ledger.committed_dollars == 0
    assert ledger.spendable_dollars == 100


def test_buy_flag_requires_ten_pending_deadlock_credits() -> None:
    service, repository, progress = build_service()

    for _ in range(9):
        repository.raise_validation_database_error = True
        with pytest.raises(TangoValidationError):
            service.submit_grid(17, SOLUTION_GRID)

    assert service.get_ledger(17).spendable_dollars == 900
    with pytest.raises(NotEnoughCreditsError):
        service.buy_flag(17)

    repository.raise_validation_database_error = True
    with pytest.raises(TangoValidationError):
        service.submit_grid(17, SOLUTION_GRID)

    result = service.buy_flag(17)

    assert result.result == "win"
    assert result.flag == FINAL_FLAG
    assert progress.calls == [17]


def test_buy_flag_is_idempotent_after_first_purchase() -> None:
    service, repository, progress = build_service()
    for _ in range(10):
        repository.raise_validation_database_error = True
        with pytest.raises(TangoValidationError):
            service.submit_grid(23, SOLUTION_GRID)
    assert service.buy_flag(23).result == "win"
    assert progress.calls == [23]

    second = service.buy_flag(23)
    third = service.buy_flag(23)
    assert second.result == "win"
    assert third.result == "win"
    assert second.flag == FINAL_FLAG
    assert third.flag == FINAL_FLAG
    # mark_stage3_cleared shouldn't be called again on repeat buys
    assert progress.calls == [23]


def test_refresh_ledger_rolls_pending_credits_back_to_zero() -> None:
    service, repository, _ = build_service()
    repository.raise_validation_database_error = True
    with pytest.raises(TangoValidationError):
        service.submit_grid(19, SOLUTION_GRID)

    assert service.get_ledger(19).spendable_dollars == 100

    ledger = service.refresh_ledger(19)

    assert ledger.pending_dollars == 0
    assert ledger.spendable_dollars == 0
    assert ledger.entries[0].status == "ROLLED_BACK"


def test_reset_clears_stage_local_state() -> None:
    service, repository, _ = build_service()
    service.submit_grid(21, SOLUTION_GRID)
    repository.raise_validation_database_error = True
    with pytest.raises(TangoValidationError):
        service.submit_grid(21, SOLUTION_GRID)

    status = service.reset(21)

    assert status.ledger.entries == []
    assert status.ledger.spendable_dollars == 0
    assert status.latest_attempt_state == "idle"


def test_submission_gate_allows_two_and_rejects_third() -> None:
    asyncio.run(_assert_submission_gate_allows_two_and_rejects_third())


async def _assert_submission_gate_allows_two_and_rejects_third() -> None:
    gate = SubmissionGate(capacity=2)
    first = gate.acquire(41, timeout=0.01)
    second = gate.acquire(41, timeout=0.01)

    async with first:
        async with second:
            assert gate.available_permits(41) == 0
            with pytest.raises(TooManySubmissionsError):
                async with gate.acquire(41, timeout=0.01):
                    pass

    assert gate.available_permits(41) == 2


def test_submission_gate_releases_after_exceptions() -> None:
    asyncio.run(_assert_submission_gate_releases_after_exceptions())


async def _assert_submission_gate_releases_after_exceptions() -> None:
    gate = SubmissionGate(capacity=2)

    with pytest.raises(RuntimeError):
        async with gate.acquire(8, timeout=0.01):
            raise RuntimeError("boom")

    async with gate.acquire(8, timeout=0.01):
        async with gate.acquire(8, timeout=0.01):
            await asyncio.sleep(0)
    assert gate.available_permits(8) == 2
