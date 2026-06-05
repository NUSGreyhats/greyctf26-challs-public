from __future__ import annotations

from dataclasses import replace

import pytest

from app.stages.stage1.models import PinpointUserState
from app.stages.stage1.service import GuessLimitReached, InvalidGuess, PinpointService
from app.stages.stage1.wordbank import WordBank


class InMemoryRepository:
    def __init__(self) -> None:
        self.rows: dict[int, PinpointUserState] = {}
        self.guess_log: dict[int, list[str]] = {}
        self.calls: list[str] = []

    def fetch_user_state(self, user_id: int) -> PinpointUserState | None:
        self.calls.append("fetch_user_state")
        return self.rows.get(user_id)

    def create_user_state(self, state: PinpointUserState) -> None:
        self.calls.append("create_user_state")
        self.rows[state.user_id] = state

    def fetch_recent_guesses(self, user_id: int, limit: int = 5) -> list[str]:
        self.calls.append("fetch_recent_guesses")
        return self.guess_log.get(user_id, [])[:limit]

    def apply_guess(self, *, user_id: int, is_correct: bool, guess: str) -> PinpointUserState:
        self.calls.append("apply_guess")
        current = self.rows[user_id]
        updated = replace(
            current,
            guesses_used=current.guesses_used + 1,
            solved=current.solved or is_correct,
            last_result="correct" if is_correct else "wrong",
        )
        self.rows[user_id] = updated
        self.guess_log[user_id] = [guess, *self.guess_log.get(user_id, [])]
        return updated

    def reset_user_state(self, user_id: int, *, puzzle_answer: str) -> PinpointUserState:
        self.calls.append("reset_user_state")
        current = self.rows[user_id]
        updated = replace(
            current,
            guesses_used=0,
            solved=False,
            puzzle_answer=puzzle_answer,
            last_result=None,
        )
        self.rows[user_id] = updated
        self.guess_log[user_id] = []
        return updated


class ProgressGatewayStub:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def unlock_stage2(self, user_id: int) -> None:
        self.calls.append(user_id)


@pytest.fixture
def wordbank() -> WordBank:
    return WordBank(
        ["crane", "slate", "shard", "flint", "proud", "gleam"],
        secret="test-pinpoint-secret",
        minimum_size=1,
    )


@pytest.fixture
def service(wordbank: WordBank) -> tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]:
    repository = InMemoryRepository()
    progress = ProgressGatewayStub()
    pinpoint = PinpointService(
        repository=repository,
        progress_gateway=progress,
        wordbank=wordbank,
        instance_seed="seed-123",
    )
    return pinpoint, repository, progress


def test_answer_is_deterministic_per_secret(wordbank: WordBank) -> None:
    answer_a = wordbank.answer_for()
    answer_b = wordbank.answer_for()
    assert answer_a == answer_b
    assert answer_a in {"crane", "flint", "gleam", "proud", "shard", "slate"}

    other = WordBank(
        ["crane", "slate", "shard", "flint", "proud", "gleam"],
        secret="a-different-secret-with-different-digest",
        minimum_size=1,
    )
    assert other.answer_for() in {"crane", "flint", "gleam", "proud", "shard", "slate"}


def test_subset_is_fixed_when_subset_size_is_used() -> None:
    subset_wordbank = WordBank(
        ["crane", "slate", "shard", "flint", "proud", "gleam"],
        secret="test-pinpoint-secret",
        minimum_size=1,
        subset_size=3,
    )

    words_a = subset_wordbank.words_for_instance()
    words_b = subset_wordbank.words_for_instance()

    assert words_a == words_b
    assert len(words_a) == 3
    assert words_a != []


def test_status_bootstraps_stage_row(service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]) -> None:
    pinpoint, repository, _ = service

    status = pinpoint.get_status(11)

    assert status.guesses_used == 0
    assert status.remaining_guesses == 5
    assert status.recent_guesses == []
    assert repository.calls == ["fetch_user_state", "create_user_state", "fetch_recent_guesses"]
    assert repository.rows[11].puzzle_answer


def test_wrong_guess_updates_status_without_unlock(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, repository, progress = service
    pinpoint.ensure_stage_row(5)
    repository.rows[5] = replace(repository.rows[5], puzzle_answer="crane")

    outcome = pinpoint.submit_guess(5, "slate")

    assert outcome.result == "wrong"
    assert outcome.guesses_used == 1
    assert outcome.remaining_guesses == 4
    assert progress.calls == []
    assert repository.calls[-2:] == ["fetch_user_state", "apply_guess"]
    assert repository.guess_log[5] == ["slate"]


def test_correct_guess_unlocks_stage2(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, repository, progress = service
    pinpoint.ensure_stage_row(5)
    repository.rows[5] = replace(repository.rows[5], puzzle_answer="crane")

    outcome = pinpoint.submit_guess(5, "crane")

    assert outcome.result == "correct"
    assert progress.calls == [5]
    assert repository.rows[5].solved is True


def test_solved_user_unlocks_without_consuming_another_guess(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, repository, progress = service
    pinpoint.ensure_stage_row(6)
    repository.rows[6] = replace(
        repository.rows[6],
        guesses_used=3,
        solved=True,
        puzzle_answer="crane",
        last_result="correct",
    )

    outcome = pinpoint.submit_guess(6, "slate")

    assert outcome.result == "correct"
    assert repository.rows[6].guesses_used == 3
    assert repository.calls[-1] == "fetch_user_state"
    assert "apply_guess" not in repository.calls[-2:]
    assert progress.calls == [6]


def test_limit_reached_raises(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, repository, _ = service
    pinpoint.ensure_stage_row(5)
    repository.rows[5] = replace(repository.rows[5], guesses_used=5)

    with pytest.raises(GuessLimitReached):
        pinpoint.submit_guess(5, "crane")


def test_wordbank_check_runs_before_limit_check_after_exhaustion(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, repository, _ = service
    pinpoint.ensure_stage_row(5)
    repository.rows[5] = replace(repository.rows[5], guesses_used=5)

    with pytest.raises(InvalidGuess):
        pinpoint.submit_guess(5, "zzzzz")
    assert repository.rows[5].guesses_used == 5


def test_invalid_guess_is_rejected(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, _, _ = service

    with pytest.raises(InvalidGuess):
        pinpoint.submit_guess(5, "12")


def test_guess_outside_wordbank_is_rejected_without_incrementing(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, repository, _ = service
    pinpoint.ensure_stage_row(5)

    with pytest.raises(InvalidGuess):
        pinpoint.submit_guess(5, "zzzzz")

    assert repository.rows[5].guesses_used == 0
    assert repository.guess_log.get(5) is None


def test_reset_rotates_answer_and_clears_mutable_state(
    service: tuple[PinpointService, InMemoryRepository, ProgressGatewayStub]
) -> None:
    pinpoint, repository, _ = service
    pinpoint.ensure_stage_row(9)
    seeded_answer = repository.rows[9].puzzle_answer
    repository.rows[9] = replace(repository.rows[9], guesses_used=4, solved=True, last_result="correct")
    repository.guess_log[9] = ["crane"]

    status = pinpoint.reset(9)

    assert status.guesses_used == 0
    assert status.remaining_guesses == 5
    assert status.solved is False
    assert status.recent_guesses == []
    assert repository.rows[9].puzzle_answer != seeded_answer
    assert repository.rows[9].puzzle_answer in {"crane", "flint", "gleam", "proud", "shard", "slate"}
