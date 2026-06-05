from __future__ import annotations

from contextvars import ContextVar

_team_id: ContextVar[str | None] = ContextVar("team_id", default=None)

BOOTSTRAP_TEAM_ID = "__bootstrap__"


def set_team_id(team_id: str) -> None:
    _team_id.set(team_id)


def get_team_id() -> str | None:
    return _team_id.get()


def get_team_id_required() -> str:
    team_id = get_team_id()
    if team_id is None:
        raise RuntimeError("Team context is not set for this request.")
    return team_id


def clear_team_id() -> None:
    _team_id.set(None)
