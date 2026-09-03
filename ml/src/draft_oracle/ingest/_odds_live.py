"""Live odds clients and conversion helpers."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import httpx
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from draft_oracle.ingest.nhl_api import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT,
    NHLApiError,
    ResponseCache,
)

if TYPE_CHECKING:
    from draft_oracle.ingest.odds import OddsRowGame

# ── Live odds: The Odds API (future games only) ──────────────────────────

DEFAULT_ODDS_CACHE_DIR = Path("data/raw/odds-api")
DEFAULT_ESPN_CACHE_DIR = Path("data/raw/espn-odds")
SOURCE_ODDS_API = "odds_api"
SOURCE_ESPN_SUMMARY = "espn_summary"

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_SPORT = "icehockey_nhl"
ESPN_SUMMARY_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
DEFAULT_ODDS_API_DELAY = 1.0


@dataclass(frozen=True)
class _FavoritePrice:
    moneyline: float | None
    side: str | None


@dataclass(frozen=True)
class OddsApiClientConfig:
    api_key: str | None = None
    base: str = ODDS_API_BASE
    sport: str = ODDS_API_SPORT
    delay: float = DEFAULT_ODDS_API_DELAY
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retry_backoff: float = 1.0
    timeout: float = DEFAULT_TIMEOUT


@dataclass(frozen=True)
class EspnGameOddsClientConfig:
    base: str = ESPN_SUMMARY_BASE
    delay: float = 1.0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retry_backoff: float = 1.0
    timeout: float = DEFAULT_TIMEOUT


def _odds_api_config(
    config: OddsApiClientConfig | None, legacy: Mapping[str, object]
) -> OddsApiClientConfig:
    _reject_unexpected_options(
        "OddsApiClient",
        legacy,
        {"api_key", "base", "sport", "delay", "max_attempts", "retry_backoff", "timeout"},
    )
    base_config = config or OddsApiClientConfig()
    api_key = legacy.get("api_key", base_config.api_key)
    return OddsApiClientConfig(
        api_key=str(api_key) if api_key is not None else None,
        base=str(legacy.get("base", base_config.base)),
        sport=str(legacy.get("sport", base_config.sport)),
        delay=_float_option(legacy, "delay", base_config.delay),
        max_attempts=_int_option(legacy, "max_attempts", base_config.max_attempts),
        retry_backoff=_float_option(legacy, "retry_backoff", base_config.retry_backoff),
        timeout=_float_option(legacy, "timeout", base_config.timeout),
    )


def _espn_game_config(
    config: EspnGameOddsClientConfig | None, legacy: Mapping[str, object]
) -> EspnGameOddsClientConfig:
    _reject_unexpected_options(
        "EspnGameOddsClient",
        legacy,
        {"base", "delay", "max_attempts", "retry_backoff", "timeout"},
    )
    base_config = config or EspnGameOddsClientConfig()
    return EspnGameOddsClientConfig(
        base=str(legacy.get("base", base_config.base)),
        delay=_float_option(legacy, "delay", base_config.delay),
        max_attempts=_int_option(legacy, "max_attempts", base_config.max_attempts),
        retry_backoff=_float_option(legacy, "retry_backoff", base_config.retry_backoff),
        timeout=_float_option(legacy, "timeout", base_config.timeout),
    )


def _reject_unexpected_options(
    owner: str, legacy: Mapping[str, object], allowed: set[str]
) -> None:
    unexpected = set(legacy) - allowed
    if unexpected:
        raise TypeError(f"unexpected {owner} option(s): {sorted(unexpected)}")


def _float_option(options: Mapping[str, object], name: str, default: float) -> float:
    return float(cast("float | int", options.get(name, default)))


def _int_option(options: Mapping[str, object], name: str, default: int) -> int:
    return int(cast("float | int", options.get(name, default)))


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
        config: OddsApiClientConfig | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        **legacy: object,
    ) -> None:
        config = _odds_api_config(config, legacy)
        if config.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.api_key = (
            config.api_key if config.api_key is not None else os.environ.get("ODDS_API_KEY", "")
        )
        self.base = config.base.rstrip("/")
        self.sport = config.sport
        self.delay = config.delay
        self.max_attempts = config.max_attempts
        self.retry_backoff = config.retry_backoff
        self._cache = ResponseCache(Path(cache_dir))
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=config.timeout)
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
            parsed, last_error = self._get_attempt(path, query, attempt, last_error)
            if parsed is not None:
                self._cache.put(cache_key, {"data": parsed})
                return parsed
        raise NHLApiError(
            f"Odds API request failed after {self.max_attempts} attempts: {path}"
        ) from last_error

    def _get_attempt(
        self,
        path: str,
        query: Mapping[str, str],
        attempt: int,
        last_error: Exception | None,
    ) -> tuple[object | None, Exception | None]:
        if self.delay > 0:
            self._sleep(self.delay)
        try:
            response = self._client.get(f"{self.base}{path}", params=dict(query))
            response.raise_for_status()
            self._capture_quota(response.headers)
            return response.json(), last_error
        except (httpx.HTTPError, ValueError) as error:
            if attempt + 1 < self.max_attempts:
                self._sleep(self.retry_backoff * (2**attempt))
            return None, error

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
    from draft_oracle.ingest.odds import _finalize

    rows: list[dict[str, Any]] = []
    for event in events:
        row = _odds_api_event_row(event)
        if row is not None:
            rows.append(row)
    return _finalize(rows)


def _odds_api_event_row(event: OddsApiEvent) -> dict[str, Any] | None:
    from draft_oracle.ingest.odds import _two_sided_row, _uncovered_row

    game = _odds_api_game(event)
    if game is None:
        return None
    home_prices, away_prices = _odds_api_h2h_prices(event, game.home_id, game.away_id)
    if not _has_price_pair(home_prices, away_prices):
        return cast("dict[str, Any]", _uncovered_row(game))
    return _two_sided_row(
        game,
        away_ml=_median(away_prices),
        home_ml=_median(home_prices),
    )


def _has_price_pair(home_prices: list[float], away_prices: list[float]) -> bool:
    return bool(home_prices) and bool(away_prices)


def _odds_api_game(event: OddsApiEvent) -> OddsRowGame | None:
    from draft_oracle.ingest.odds import OddsRowGame, _parse_utc_date, resolve_team_id

    if event.home_team is None:
        return None
    if event.away_team is None:
        return None
    home_id = resolve_team_id(event.home_team)
    away_id = resolve_team_id(event.away_team)
    game_date = _parse_utc_date(event.commence_time)
    if home_id is None:
        return None
    if away_id is None:
        return None
    if game_date is None:
        return None
    season_end_year = game_date.year + 1 if game_date.month >= 8 else game_date.year
    return OddsRowGame(
        source=SOURCE_ODDS_API,
        season_end_year=season_end_year,
        game_date=game_date,
        away_id=away_id,
        home_id=home_id,
        away_name=event.away_team,
        home_name=event.home_team,
        neutral=False,
    )


def _odds_api_h2h_prices(
    event: OddsApiEvent, home_id: int, away_id: int
) -> tuple[list[float], list[float]]:
    from draft_oracle.ingest.odds import resolve_team_id

    home_prices: list[float] = []
    away_prices: list[float] = []
    prices_by_id = {home_id: home_prices, away_id: away_prices}
    outcomes = [
        outcome
        for book in event.bookmakers
        for market in book.markets
        if market.key == "h2h"
        for outcome in market.outcomes
    ]
    for outcome in outcomes:
        bucket = _price_bucket(prices_by_id, resolve_team_id(outcome.name))
        _append_price(bucket, outcome.price)
    return home_prices, away_prices


def _price_bucket(
    prices_by_id: dict[int, list[float]], outcome_id: int | None
) -> list[float] | None:
    if outcome_id is None:
        return None
    return prices_by_id.get(outcome_id)


def _append_price(bucket: list[float] | None, price: float) -> None:
    if bucket is not None:
        bucket.append(price)


# ── Live odds: ESPN summary (favorite-only, future games) ────────────────


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
        config: EspnGameOddsClientConfig | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        **legacy: object,
    ) -> None:
        config = _espn_game_config(config, legacy)
        if config.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.base = config.base.rstrip("/")
        self.delay = config.delay
        self.max_attempts = config.max_attempts
        self.retry_backoff = config.retry_backoff
        self._cache = ResponseCache(Path(cache_dir))
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=config.timeout)

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
            parsed, last_error = self._summary_attempt(path, params, attempt, last_error)
            if parsed is not None:
                self._cache.put(cache_key, parsed)
                return parsed
        raise NHLApiError(
            f"ESPN summary request failed after {self.max_attempts} attempts: event={event_id}"
        ) from last_error

    def _summary_attempt(
        self,
        path: str,
        params: Mapping[str, str],
        attempt: int,
        last_error: Exception | None,
    ) -> tuple[dict[str, Any] | None, Exception | None]:
        if self.delay > 0:
            self._sleep(self.delay)
        try:
            response = self._client.get(f"{self.base}{path}", params=dict(params))
            response.raise_for_status()
            parsed: dict[str, Any] = response.json()
            return parsed, last_error
        except (httpx.HTTPError, ValueError) as error:
            if attempt + 1 < self.max_attempts:
                self._sleep(self.retry_backoff * (2**attempt))
            return None, error

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
        _empty_odds_frame,
        _favorite_only_row,
        _finalize,
        _uncovered_row,
    )

    game = _espn_summary_game(summary)
    if game is None:
        return _empty_odds_frame()
    favorite = _espn_pickcenter_favorite(summary.get("pickcenter"))
    if favorite.moneyline is None or favorite.side is None:
        return _finalize([_uncovered_row(game)])
    return _finalize(
        [
            _favorite_only_row(
                game,
                favorite_ml=favorite.moneyline,
                favorite_side=favorite.side,
            )
        ]
    )


def _espn_summary_game(summary: Mapping[str, Any]) -> OddsRowGame | None:
    from draft_oracle.ingest.odds import OddsRowGame, _parse_utc_date, resolve_team_id

    competition = _first_espn_competition(summary)
    if competition is None:
        return None
    home_name, away_name = _espn_competitor_names(competition)
    game_date = _parse_utc_date(competition.get("date"))
    if home_name is None:
        return None
    if away_name is None:
        return None
    if game_date is None:
        return None
    home_id = resolve_team_id(home_name)
    away_id = resolve_team_id(away_name)
    if home_id is None or away_id is None:
        return None
    season_end_year = game_date.year if game_date.month < 8 else game_date.year + 1
    return OddsRowGame(
        source=SOURCE_ESPN_SUMMARY,
        season_end_year=season_end_year,
        game_date=game_date,
        away_id=away_id,
        home_id=home_id,
        away_name=away_name,
        home_name=home_name,
        neutral=False,
    )


def _first_espn_competition(summary: Mapping[str, Any]) -> dict[str, Any] | None:
    competitions = _dig(summary, "header", "competitions")
    if not isinstance(competitions, list):
        return None
    if not competitions:
        return None
    first = competitions[0]
    return first if isinstance(first, dict) else None


def _espn_competitor_names(competition: Mapping[str, Any]) -> tuple[str | None, str | None]:
    competitors = competition.get("competitors", [])
    if not isinstance(competitors, list):
        return None, None
    names = {
        side: name
        for side, name in (_espn_competitor_side_name(item) for item in competitors)
        if side is not None
    }
    return names.get("home"), names.get("away")


def _espn_competitor_side_name(competitor: object) -> tuple[str | None, str | None]:
    if not isinstance(competitor, Mapping):
        return None, None
    team = competitor.get("team", {})
    name = team.get("displayName") if isinstance(team, Mapping) else None
    side = competitor.get("homeAway")
    return str(side) if side is not None else None, str(name) if name is not None else None


def _espn_pickcenter_favorite(pickcenter: object) -> _FavoritePrice:
    from draft_oracle.ingest.odds import _american, _pickcenter_favorite_side

    if not isinstance(pickcenter, list):
        return _FavoritePrice(None, None)
    if not pickcenter:
        return _FavoritePrice(None, None)
    first = pickcenter[0]
    if not isinstance(first, Mapping):
        return _FavoritePrice(None, None)
    favorite_ml = _pickcenter_favorite_ml(first)
    favorite_side = _pickcenter_favorite_side(first)
    home_relative_spread = _american(first.get("spread"))
    if favorite_side is None and home_relative_spread not in (None, 0.0):
        favorite_side = "home" if home_relative_spread < 0 else "away"
    return _FavoritePrice(favorite_ml, favorite_side)


def _pickcenter_favorite_ml(pickcenter: Mapping[str, Any]) -> float | None:
    """Extract the favorite's moneyline from an ESPN ``pickcenter`` entry."""
    from draft_oracle.ingest.odds import _american

    for side_key in ("homeTeamOdds", "awayTeamOdds"):
        coerced = _favorite_side_moneyline(pickcenter.get(side_key))
        if coerced is not None:
            return coerced
    # Fall back to a top-level moneyLine if the per-side flags are absent.
    return _american(pickcenter.get("moneyLine"))


def _favorite_side_moneyline(side: object) -> float | None:
    from draft_oracle.ingest.odds import _american

    if not isinstance(side, Mapping):
        return None
    if not side.get("favorite"):
        return None
    return _american(side.get("moneyLine"))


def _dig(obj: Any, *keys: str) -> Any:
    """Safely walk nested mappings; return ``None`` on any miss."""
    current = obj
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current
