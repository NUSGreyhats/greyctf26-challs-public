from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OPTIMAL_AVERAGE_MOVES = 2_000.0
BASELINE_AVERAGE_MOVES = 25_000.0
MIN_SCORE = 100
MAX_SCORE = 1_000
DEFAULT_AWARD_CATEGORY = "Rubikscube"
SCORE_MARKER = "rubikscube-score-v1"
DEFAULT_TIMEOUT_SECONDS = 5.0


class ScoringError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScoreContext:
    team_id: str
    challenge_id: str


@dataclass(frozen=True, slots=True)
class ScoreSubmission:
    score: int
    status: str


def compute_score(average_moves: float) -> int:
    if average_moves <= 0:
        raise ValueError("average_moves must be positive.")
    if average_moves <= OPTIMAL_AVERAGE_MOVES:
        return MAX_SCORE
    if average_moves >= BASELINE_AVERAGE_MOVES:
        return MIN_SCORE

    progress = math.log(BASELINE_AVERAGE_MOVES / average_moves) / math.log(
        BASELINE_AVERAGE_MOVES / OPTIMAL_AVERAGE_MOVES
    )
    return round(MIN_SCORE + (MAX_SCORE - MIN_SCORE) * progress)


def submit_ctfd_score(
    average_moves: float,
    context: ScoreContext | None,
    *,
    environ: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ScoreSubmission:
    score = compute_score(average_moves)
    if context is None:
        return ScoreSubmission(score=score, status="score_pending")

    env = os.environ if environ is None else environ
    if not env.get("CTFD_API_TOKEN") or not _award_collection_url(env):
        return ScoreSubmission(score=score, status="score_pending")

    try:
        _submit_award(score=score, average_moves=average_moves, context=context, environ=env, timeout=timeout)
    except ScoringError:
        return ScoreSubmission(score=score, status="score_pending")
    return ScoreSubmission(score=score, status="submitted")


def _award_collection_url(environ: Mapping[str, str]) -> str | None:
    explicit = environ.get("CTFD_SCORE_URL")
    if explicit:
        return explicit.rstrip("/")
    base_url = environ.get("CTFD_URL")
    if not base_url:
        return None
    return base_url.rstrip("/") + "/api/v1/awards"


def _submit_award(
    *,
    score: int,
    average_moves: float,
    context: ScoreContext,
    environ: Mapping[str, str],
    timeout: float,
) -> None:
    collection_url = _award_collection_url(environ)
    api_token = environ.get("CTFD_API_TOKEN")
    if not collection_url or not api_token:
        raise ScoringError("missing CTFd scoring configuration")

    existing = _find_existing_award(collection_url, api_token, context, timeout)
    if existing is not None:
        existing_score = _award_score(existing)
        if existing_score is not None and existing_score >= score:
            return
        award_id = existing.get("id")
        if award_id is None:
            raise ScoringError("existing award has no id")
        _update_award(collection_url, api_token, str(award_id), score, average_moves, context, environ, timeout)
        return

    _create_award(collection_url, api_token, score, average_moves, context, environ, timeout)


def _find_existing_award(
    collection_url: str,
    api_token: str,
    context: ScoreContext,
    timeout: float,
) -> dict[str, object] | None:
    query = urlencode({"team_id": context.team_id})
    separator = "&" if "?" in collection_url else "?"
    response = _request_json(f"{collection_url}{separator}{query}", api_token, method="GET", timeout=timeout)
    data = response.get("data", [])
    if not isinstance(data, list):
        raise ScoringError("unexpected CTFd awards response")

    marker = _score_marker(context)
    for item in data:
        if not isinstance(item, dict):
            continue
        description = item.get("description")
        if isinstance(description, str) and marker in description:
            return item
    return None


def _create_award(
    collection_url: str,
    api_token: str,
    score: int,
    average_moves: float,
    context: ScoreContext,
    environ: Mapping[str, str],
    timeout: float,
) -> None:
    _request_json(
        collection_url,
        api_token,
        method="POST",
        payload=_award_payload(score, average_moves, context, environ),
        timeout=timeout,
    )


def _update_award(
    collection_url: str,
    api_token: str,
    award_id: str,
    score: int,
    average_moves: float,
    context: ScoreContext,
    environ: Mapping[str, str],
    timeout: float,
) -> None:
    award_url = f"{collection_url.rstrip('/')}/{award_id}"
    payload = _award_payload(score, average_moves, context, environ)
    try:
        _request_json(award_url, api_token, method="PATCH", payload=payload, timeout=timeout)
    except ScoringError:
        _request_json(award_url, api_token, method="DELETE", timeout=timeout)
        _create_award(collection_url, api_token, score, average_moves, context, environ, timeout)


def _award_payload(
    score: int,
    average_moves: float,
    context: ScoreContext,
    environ: Mapping[str, str],
) -> dict[str, object]:
    team_id: int | str = int(context.team_id) if context.team_id.isdigit() else context.team_id
    return {
        "name": "Rubikscube score",
        "category": environ.get("CTFD_AWARD_CATEGORY", DEFAULT_AWARD_CATEGORY),
        "value": score,
        "team_id": team_id,
        "description": (
            f"{_score_marker(context)} "
            f"average={average_moves:.2f} score={score} "
            f"formula=log_100_at_25000_1000_at_2000"
        ),
    }


def _score_marker(context: ScoreContext) -> str:
    return f"{SCORE_MARKER} challenge={context.challenge_id} team={context.team_id}"


def _award_score(award: Mapping[str, object]) -> int | None:
    raw_value = award.get("value")
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError:
            return None
    return None


def _request_json(
    url: str,
    api_token: str,
    *,
    method: str,
    timeout: float,
    payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Token {api_token}",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except OSError as exc:
        raise ScoringError(str(exc)) from exc

    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScoringError("invalid CTFd response") from exc
    if not isinstance(parsed, dict):
        raise ScoringError("unexpected CTFd response")
    if parsed.get("success") is False:
        raise ScoringError("CTFd request was not successful")
    return parsed
