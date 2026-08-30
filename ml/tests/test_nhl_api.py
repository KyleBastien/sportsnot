"""Unit tests for the typed, cached NHL API client (US-003).

No test touches the network: an ``httpx.MockTransport`` serves recorded fixture
JSON, and backoff sleeps are stubbed out (SPEC §7 — fixtures only).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from draft_oracle.ingest.nhl_api import (
    NHLApiClient,
    NHLApiError,
    ResponseCache,
)

FIXTURES = Path(__file__).parent / "fixtures" / "nhl"
# A real recorded NHL response, committed under the archive (SPEC §5).
BRACKET_FIXTURE = Path("data/raw/nhl-archive/bracket-2026.json")


def _load(name: str) -> dict[str, object]:
    with (FIXTURES / name).open("r", encoding="utf-8") as handle:
        data: dict[str, object] = json.load(handle)
    return data


def _noop_sleep(_seconds: float) -> None:
    return None


def _routed_transport(
    routes: dict[str, dict[str, object]], counter: list[int]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        counter[0] += 1
        payload = routes.get(request.url.path)
        if payload is None:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


@pytest.fixture
def make_client(
    tmp_path: Path,
) -> Iterator[Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient]]:
    created: list[NHLApiClient] = []

    def factory(routes: dict[str, dict[str, object]], counter: list[int]) -> NHLApiClient:
        transport = _routed_transport(routes, counter)
        client = NHLApiClient(
            cache_dir=tmp_path / "cache",
            delay=0.0,
            retry_backoff=0.0,
            sleep=_noop_sleep,
            client=httpx.Client(transport=transport),
        )
        created.append(client)
        return client

    yield factory
    for client in created:
        client.close()


# ── Typed adapter parsing ────────────────────────────────────────────────


def test_player_game_log_parses(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    routes = {"/v1/player/8478403/game-log/20252026/3": _load("player_game_log.json")}
    client = make_client(routes, calls)

    log = client.player_game_log(8478403, 20252026, 3)

    assert log.season_id == 20252026
    assert len(log.game_log) == 2
    first = log.game_log[0]
    assert first.game_id == 2025030111
    assert first.goals == 1
    assert first.assists == 2
    assert first.points == 3
    assert first.opponent_abbrev == "BOS"


def test_club_schedule_season_parses_scores(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    routes = {"/v1/club-schedule-season/BUF/20252026": _load("club_schedule_season.json")}
    client = make_client(routes, calls)

    schedule = client.club_schedule_season("BUF", 20252026)

    assert schedule.current_season == 20252026
    assert len(schedule.games) == 2
    game = schedule.games[0]
    assert game.home_team.abbrev == "BUF"
    assert game.home_team.score == 3
    assert game.away_team.score == 2
    assert game.game_outcome is not None
    assert game.game_outcome.last_period_type == "REG"
    assert schedule.games[1].game_outcome is not None
    assert schedule.games[1].game_outcome.last_period_type == "OT"


def test_team_roster_parses(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    routes = {"/v1/roster/BUF/20252026": _load("team_roster.json")}
    client = make_client(routes, calls)

    roster = client.team_roster("BUF", 20252026)

    assert len(roster.forwards) == 2
    assert len(roster.defensemen) == 1
    assert len(roster.goalies) == 1
    assert roster.goalies[0].position_code == "G"
    dahlin = roster.defensemen[0]
    assert dahlin.last_name is not None
    assert dahlin.last_name.default == "Dahlin"


def test_player_info_parses_position_and_status(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    routes = {"/v1/player/8478403/landing": _load("player_landing.json")}
    client = make_client(routes, calls)

    info = client.player_info(8478403)

    assert info.player_id == 8478403
    assert info.position == "C"
    assert info.is_active is True
    assert info.current_team_abbrev == "BUF"


def test_scores_by_date_parses(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    routes = {"/v1/score/2026-04-20": _load("scores_by_date.json")}
    client = make_client(routes, calls)

    scores = client.scores_by_date("2026-04-20")

    assert scores.current_date == "2026-04-20"
    assert len(scores.games) == 1
    assert scores.games[0].home_team.abbrev == "BUF"


def test_skater_summary_parses(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    routes = {"/stats/rest/en/skater/summary": _load("skater_summary.json")}
    client = make_client(routes, calls)

    summary = client.skater_summary(20252026, 3)

    assert summary.total == 2
    assert len(summary.data) == 2
    assert summary.data[0].player_id == 8478403
    assert summary.data[0].position_code == "C"


def test_skater_summary_rejects_response_at_row_cap(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    payload = _load("skater_summary.json")
    payload["total"] = 10_000
    routes = {"/stats/rest/en/skater/summary": payload}
    client = make_client(routes, calls)

    with pytest.raises(NHLApiError, match="10,000-row response cap"):
        client.skater_summary(20252026, 2)


def test_playoff_bracket_parses_recorded_response(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    assert BRACKET_FIXTURE.is_file(), "committed NHL bracket archive is required"
    with BRACKET_FIXTURE.open("r", encoding="utf-8") as handle:
        bracket_json: dict[str, object] = json.load(handle)
    calls = [0]
    routes = {"/v1/playoff-bracket/2026": bracket_json}
    client = make_client(routes, calls)

    bracket = client.playoff_bracket(2026)

    assert len(bracket.series) >= 1
    series = bracket.series[0]
    assert series.series_letter == "A"
    assert series.playoff_round == 1
    assert series.top_seed_team is not None
    assert series.top_seed_team.abbrev is not None


# ── Caching ──────────────────────────────────────────────────────────────


def test_cache_hit_skips_network(
    make_client: Callable[[dict[str, dict[str, object]], list[int]], NHLApiClient],
) -> None:
    calls = [0]
    routes = {"/v1/roster/BUF/20252026": _load("team_roster.json")}
    client = make_client(routes, calls)

    client.team_roster("BUF", 20252026)
    client.team_roster("BUF", 20252026)

    assert calls[0] == 1  # second call served entirely from disk cache


def test_cache_persists_across_client_instances(
    tmp_path: Path,
) -> None:
    payload = _load("team_roster.json")
    calls = [0]

    def build() -> NHLApiClient:
        transport = _routed_transport({"/v1/roster/BUF/20252026": payload}, calls)
        return NHLApiClient(
            cache_dir=tmp_path / "cache",
            delay=0.0,
            retry_backoff=0.0,
            sleep=_noop_sleep,
            client=httpx.Client(transport=transport),
        )

    with build() as first:
        first.team_roster("BUF", 20252026)
    with build() as second:
        second.team_roster("BUF", 20252026)

    assert calls[0] == 1


def test_cache_key_is_endpoint_and_param_specific() -> None:
    base = "https://api-web.nhle.com/v1"
    a = ResponseCache.key_for(base, "/score/2026-04-20", None)
    b = ResponseCache.key_for(base, "/score/2026-04-21", None)
    assert a != b
    p1 = ResponseCache.key_for(base, "/skater/summary", {"a": 1, "b": 2})
    p2 = ResponseCache.key_for(base, "/skater/summary", {"b": 2, "a": 1})
    assert p1 == p2  # param order independent


# ── Retry / backoff / loud failure ───────────────────────────────────────


def test_retry_then_success(tmp_path: Path) -> None:
    payload = _load("team_roster.json")
    attempts = [0]

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts[0] += 1
        if attempts[0] < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json=payload)

    sleeps: list[float] = []
    client = NHLApiClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.5,
        max_attempts=4,
        sleep=sleeps.append,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with client:
        roster = client.team_roster("BUF", 20252026)

    assert attempts[0] == 3
    assert len(roster.forwards) == 2
    assert sleeps == [0.5, 1.0]  # backoff after the two failures


def test_retry_exhausted_raises_loudly(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = NHLApiClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        max_attempts=3,
        sleep=_noop_sleep,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with client, pytest.raises(NHLApiError):
        client.player_info(8478403)


def test_invalid_max_attempts_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        NHLApiClient(cache_dir=tmp_path, max_attempts=0)
