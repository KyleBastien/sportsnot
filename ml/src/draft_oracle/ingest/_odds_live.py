"""Live odds clients and conversion helpers."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from draft_oracle.ingest.nhl_api import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT,
    NHLApiError,
    ResponseCache,
)

# ── Live odds: The Odds API (future games only) ──────────────────────────

DEFAULT_ODDS_CACHE_DIR = Path("data/raw/odds-api")
DEFAULT_ESPN_CACHE_DIR = Path("data/raw/espn-odds")
SOURCE_ODDS_API = "odds_api"
SOURCE_ESPN_SUMMARY = "espn_summary"

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_SPORT = "icehockey_nhl"
DEFAULT_ODDS_API_DELAY = 1.0


class OddsApiOutcome(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    price: float
    point: float | None = None


class OddsApiMarket(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    key: str
    outcomes: list[OddsApiOutcome] = Field(default_factory=list)


class OddsApiBookmaker(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    key: str
    title: str | None = None
    markets: list[OddsApiMarket] = Field(default_factory=list)


class OddsApiEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    commence_time: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    bookmakers: list[OddsApiBookmaker] = Field(default_factory=list)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


class OddsApiClient:
    """The Odds API client - current/upcoming NHL odds only (SPEC §5).

    Free tier serves live/upcoming markets; the paid historical endpoints are
    never called. Quota is capped (typically 500 requests/month on the free
    tier); each response's ``x-requests-remaining`` / ``x-requests-used``
    headers are captured on :attr:`requests_remaining` / :attr:`requests_used`.
    Caching and rate-limiting mirror :class:`NHLApiClient`; the API key is read
    from ``ODDS_API_KEY`` (gitignored ``ml/.env``) and never committed.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_ODDS_CACHE_DIR,
        *,
        api_key: str | None = None,
        base: str = ODDS_API_BASE,
        sport: str = ODDS_API_SPORT,
        delay: float = DEFAULT_ODDS_API_DELAY,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff: float = 1.0,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.api_key = api_key if api_key is not None else os.environ.get("ODDS_API_KEY", "")
        self.base = base.rstrip("/")
        self.sport = sport
        self.delay = delay
        self.max_attempts = max_attempts
        self.retry_backoff = retry_backoff
        self._cache = ResponseCache(Path(cache_dir))
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout)
        self.requests_remaining: int | None = None
        self.requests_used: int | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OddsApiClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _get(self, path: str, params: Mapping[str, str]) -> Any:
        if not self.api_key:
            raise NHLApiError("ODDS_API_KEY is not set; cannot call The Odds API")
        query = {**params, "apiKey": self.api_key}
        # Cache key excludes the api key so a rotated key still hits the cache.
        cache_key = ResponseCache.key_for(self.base, path, dict(params))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.get("data")
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            if self.delay > 0:
                self._sleep(self.delay)
            try:
                response = self._client.get(f"{self.base}{path}", params=dict(query))
                response.raise_for_status()
                self._capture_quota(response.headers)
                parsed = response.json()
                self._cache.put(cache_key, {"data": parsed})
                return parsed
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt + 1 < self.max_attempts:
                    self._sleep(self.retry_backoff * (2**attempt))
        raise NHLApiError(
            f"Odds API request failed after {self.max_attempts} attempts: {path}"
        ) from last_error

    def _capture_quota(self, headers: httpx.Headers) -> None:
        remaining = headers.get("x-requests-remaining")
        used = headers.get("x-requests-used")
        if remaining is not None:
            try:
                self.requests_remaining = int(float(remaining))
            except ValueError:
                self.requests_remaining = None
        if used is not None:
            try:
                self.requests_used = int(float(used))
            except ValueError:
                self.requests_used = None

    def nhl_odds(
        self, *, markets: str = "h2h", regions: str = "us", odds_format: str = "american"
    ) -> list[OddsApiEvent]:
        """Current/upcoming NHL game odds. ``markets='h2h'`` for moneylines."""
        data = self._get(
            f"/sports/{self.sport}/odds",
            {"regions": regions, "markets": markets, "oddsFormat": odds_format},
        )
        return [OddsApiEvent.model_validate(item) for item in data]

    def nhl_series_odds(
        self, *, regions: str = "us", odds_format: str = "american"
    ) -> list[OddsApiEvent]:
        """Series/outright (futures) prices where the free tier offers them."""
        data = self._get(
            f"/sports/{self.sport}/odds",
            {"regions": regions, "markets": "outrights", "oddsFormat": odds_format},
        )
        return [OddsApiEvent.model_validate(item) for item in data]


def odds_api_events_to_rows(events: Iterable[OddsApiEvent]) -> pd.DataFrame:
    """Convert live Odds API ``h2h`` events into de-vigged odds rows.

    Uses the median moneyline across the books that priced each side (consensus
    per PROVENANCE/AC). Events whose teams do not resolve, or that lack a
    two-sided price, are flagged uncovered rather than imputed.
    """
    from draft_oracle.ingest.odds import (
        _finalize,
        _parse_utc_date,
        _two_sided_row,
        _uncovered_row,
        resolve_team_id,
    )

    rows: list[dict[str, Any]] = []
    for event in events:
        if event.home_team is None or event.away_team is None:
            continue
        home_id = resolve_team_id(event.home_team)
        away_id = resolve_team_id(event.away_team)
        game_date = _parse_utc_date(event.commence_time)
        if home_id is None or away_id is None or game_date is None:
            continue
        season_end_year = game_date.year + 1 if game_date.month >= 8 else game_date.year
        home_prices: list[float] = []
        away_prices: list[float] = []
        for book in event.bookmakers:
            for market in book.markets:
                if market.key != "h2h":
                    continue
                for outcome in market.outcomes:
                    oid = resolve_team_id(outcome.name)
                    if oid == home_id:
                        home_prices.append(outcome.price)
                    elif oid == away_id:
                        away_prices.append(outcome.price)
        if not home_prices or not away_prices:
            rows.append(
                _uncovered_row(
                    source=SOURCE_ODDS_API,
                    season_end_year=season_end_year,
                    game_date=game_date,
                    away_id=away_id,
                    home_id=home_id,
                    away_name=event.away_team,
                    home_name=event.home_team,
                    neutral=False,
                )
            )
            continue
        rows.append(
            _two_sided_row(
                source=SOURCE_ODDS_API,
                season_end_year=season_end_year,
                game_date=game_date,
                away_id=away_id,
                home_id=home_id,
                away_name=event.away_team,
                home_name=event.home_team,
                away_ml=_median(away_prices),
                home_ml=_median(home_prices),
                neutral=False,
            )
        )
    return _finalize(rows)


# ── Live odds: ESPN summary (favorite-only, future games) ────────────────

ESPN_SUMMARY_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"


class EspnGameOddsClient:
    """ESPN public ``summary`` endpoint client for a single future game.

    Reads the ``pickcenter`` block's favorite moneyline. Unlike the committed
    completion parser, live favorite attribution is inferred from the
    home-relative spread because raw summary-side favorite flags are not retained
    by this client. Favorite-only, so de-vigged with the standard-overround
    approximation. Caching/rate-limiting mirror :class:`NHLApiClient`; ESPN 403s
    browser-like User-Agents, so the default httpx UA is used. No key required.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_ESPN_CACHE_DIR,
        *,
        base: str = ESPN_SUMMARY_BASE,
        delay: float = 1.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff: float = 1.0,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.base = base.rstrip("/")
        self.delay = delay
        self.max_attempts = max_attempts
        self.retry_backoff = retry_backoff
        self._cache = ResponseCache(Path(cache_dir))
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> EspnGameOddsClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def summary(self, event_id: int | str) -> dict[str, Any]:
        """Raw (cached) ``summary`` JSON for one ESPN event id."""
        path = "/summary"
        params = {"event": str(event_id)}
        cache_key = ResponseCache.key_for(self.base, path, params)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            if self.delay > 0:
                self._sleep(self.delay)
            try:
                response = self._client.get(f"{self.base}{path}", params=dict(params))
                response.raise_for_status()
                parsed: dict[str, Any] = response.json()
                self._cache.put(cache_key, parsed)
                return parsed
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt + 1 < self.max_attempts:
                    self._sleep(self.retry_backoff * (2**attempt))
        raise NHLApiError(
            f"ESPN summary request failed after {self.max_attempts} attempts: event={event_id}"
        ) from last_error

    def game_odds(self, event_id: int | str) -> pd.DataFrame:
        """One favorite-only, de-vigged odds row for a future game (or flagged)."""
        return espn_summary_to_rows(self.summary(event_id))


def espn_summary_to_rows(summary: Mapping[str, Any]) -> pd.DataFrame:
    """Convert one ESPN ``summary`` payload into a favorite-only odds row.

    Reads ``header.competitions[0]`` for the teams/date and ``pickcenter[0]``
    for the favorite moneyline and authoritative per-side favorite flag. A usable
    home-relative spread (``spread < 0`` ⇒ home favorite - PROVENANCE §9) is only
    the fallback when neither side is flagged. Missing/blank prices or attribution
    are flagged, not imputed.
    """
    from draft_oracle.ingest.odds import (
        _american,
        _empty_odds_frame,
        _favorite_only_row,
        _finalize,
        _parse_utc_date,
        _pickcenter_favorite_side,
        _uncovered_row,
        resolve_team_id,
    )

    competitions = _dig(summary, "header", "competitions")
    if not isinstance(competitions, list) or not competitions:
        return _empty_odds_frame()
    competition = competitions[0]
    competitors = competition.get("competitors", []) if isinstance(competition, dict) else []
    home_name: str | None = None
    away_name: str | None = None
    for competitor in competitors:
        team = competitor.get("team", {}) if isinstance(competitor, dict) else {}
        name = team.get("displayName") if isinstance(team, dict) else None
        if competitor.get("homeAway") == "home":
            home_name = name
        elif competitor.get("homeAway") == "away":
            away_name = name
    game_date = _parse_utc_date(competition.get("date")) if isinstance(competition, dict) else None
    if home_name is None or away_name is None or game_date is None:
        return _empty_odds_frame()
    home_id = resolve_team_id(home_name)
    away_id = resolve_team_id(away_name)
    if home_id is None or away_id is None:
        return _empty_odds_frame()
    season_end_year = game_date.year if game_date.month < 8 else game_date.year + 1

    pickcenter = summary.get("pickcenter") if isinstance(summary, Mapping) else None
    fav_ml: float | None = None
    favorite_side: str | None = None
    home_relative_spread: float | None = None
    if isinstance(pickcenter, list) and pickcenter:
        first = pickcenter[0]
        if isinstance(first, dict):
            fav_ml = _pickcenter_favorite_ml(first)
            favorite_side = _pickcenter_favorite_side(first)
            home_relative_spread = _american(first.get("spread"))
            if favorite_side is None and home_relative_spread not in (None, 0.0):
                favorite_side = "home" if home_relative_spread < 0 else "away"
    if fav_ml is None or favorite_side is None:
        return _finalize(
            [
                _uncovered_row(
                    source=SOURCE_ESPN_SUMMARY,
                    season_end_year=season_end_year,
                    game_date=game_date,
                    away_id=away_id,
                    home_id=home_id,
                    away_name=away_name,
                    home_name=home_name,
                    neutral=False,
                )
            ]
        )
    return _finalize(
        [
            _favorite_only_row(
                source=SOURCE_ESPN_SUMMARY,
                season_end_year=season_end_year,
                game_date=game_date,
                away_id=away_id,
                home_id=home_id,
                away_name=away_name,
                home_name=home_name,
                favorite_ml=fav_ml,
                favorite_side=favorite_side,
                neutral=False,
            )
        ]
    )


def _pickcenter_favorite_ml(pickcenter: Mapping[str, Any]) -> float | None:
    """Extract the favorite's moneyline from an ESPN ``pickcenter`` entry."""
    from draft_oracle.ingest.odds import _american

    for side_key in ("homeTeamOdds", "awayTeamOdds"):
        side = pickcenter.get(side_key)
        if isinstance(side, dict) and side.get("favorite"):
            ml = side.get("moneyLine")
            coerced = _american(ml)
            if coerced is not None:
                return coerced
    # Fall back to a top-level moneyLine if the per-side flags are absent.
    return _american(pickcenter.get("moneyLine"))


def _dig(obj: Any, *keys: str) -> Any:
    """Safely walk nested mappings; return ``None`` on any miss."""
    current = obj
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current
