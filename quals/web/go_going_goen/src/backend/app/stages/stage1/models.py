from __future__ import annotations

from dataclasses import dataclass

@dataclass(slots=True)
class PinpointUserState:
    user_id: int
    guesses_used: int
    solved: bool
    puzzle_answer: str
    last_result: str | None

@dataclass(slots=True)
class PinpointStatus:
    guesses_used: int
    remaining_guesses: int
    solved: bool
    last_result: str | None
    recent_guesses: list[str]

@dataclass(slots=True)
class GuessOutcome:
    result: str
    guesses_used: int | None = None
    remaining_guesses: int | None = None
