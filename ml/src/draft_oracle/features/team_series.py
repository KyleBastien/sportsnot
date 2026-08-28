"""As-of team/series feature engineering (US-010, PRD US-004 part 2).

Produces one feature row per team *as of a playoff-round (series) start* so the
per-game win model (US-011) and series simulator (US-013) never train on future
information. Every game input funnels through
:mod:`draft_oracle.features.leakage` (strict, exclusive cutoff), so a round-``N``
feature can only read games played strictly before round ``N`` began.

Feature groups (each column documented in :data:`TEAM_FEATURE_COLUMNS`):

* **Team form** — regular-season goal differential per game, GF/GA per game,
  game-averaged power-play and penalty-kill percentages, shots for/against per
  game, rest days, and average days between games.
* **Elo** — a cross-season Elo rating replayed game-by-game with a unit-tested
  update rule (:func:`expected_score` / :func:`update_rating`) and a
  between-seasons regression toward the mean (:func:`compute_elo_ratings`).
* **Goaltender situation** — team-level save-percentage proxies (season and last
  15 games), team shutout rate, and a ``starter_unavailability_risk`` flag driven
  by the injuries table.
* **Market** — de-vigged implied win probability joined from the odds table with
  an explicit ``market_available`` missing-flag, plus an optional series price.
* **Round context / matchup** — round number, head-to-head record vs. the series
  opponent, home-ice advantage, and expected opponent strength (opponent Elo),
  each guarded by a ``*_available`` missing-flag.

Data-availability caveats (documented, never hidden):
    * The committed NHL archive has **no goalie-level game rows**, so per-goalie
      "starter" / "backup" save percentages cannot be computed. The goalie slot
      in this league is an entire *team's* goaltending (SPEC §1), so save
      percentage is a **team-level proxy** ``1 - GA / shots-against``.
      ``backup_save_pct`` is therefore left missing and flagged, never fabricated.
    * ``power_play_pct`` / ``penalty_kill_pct`` are **game-averaged** single-game
      special-teams rates (equal weight per game), not opportunity-weighted.
    * The injuries table carries **current** status only, so
      ``starter_unavailability_risk`` is meaningful for the current/upcoming
      round only; historical rounds pass no injuries frame and the flag stays
      ``False`` with ``goalie_injury_data_available == False``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from draft_oracle.features.leakage import as_of, assert_no_leakage, to_cutoff

__all__ = [
    "TEAM_FEATURE_COLUMNS",
    "TEAM_FEATURE_SET_VERSION",
    "EloConfig",
    "TeamSeriesFeatureConfig",
    "build_round_team_series_matrix",
    "build_team_series_features",
    "compute_elo_ratings",
    "days_between",
    "expected_score",
    "goal_differential_per_game",
    "regress_to_mean",
    "save_pct",
    "update_rating",
]

TEAM_FEATURE_SET_VERSION = "team-series-v1"

DEFAULT_FEATURES_DIR = Path("data/features")

REGULAR_SEASON_GAME_TYPE = 2

# Injury statuses that make a goalie unavailable (mirrors ingest.injuries).
UNAVAILABLE_STATUSES: frozenset[str] = frozenset({"out", "ir", "day_to_day"})

TEAM_FEATURE_COLUMNS: tuple[str, ...] = (
    "season_id",
    "playoff_round",
    "as_of_date",
    "team_id",
    "team_abbrev",
    "games_played",
    "goals_for_per_game",
    "goals_against_per_game",
    "goal_differential_per_game",
    "power_play_pct",
    "penalty_kill_pct",
    "shots_for_per_game",
    "shots_against_per_game",
    "faceoff_win_pct",
    "rest_days",
    "days_between_games",
    "elo_rating",
    # Goaltender situation (team-level proxy — see module docstring).
    "starter_save_pct_season",
    "starter_save_pct_l15",
    "backup_save_pct",
    "team_shutout_rate",
    "goalie_split_available",
    "starter_unavailability_risk",
    "goalie_injury_data_available",
    # Market.
    "market_implied_win_prob",
    "market_available",
    "series_implied_win_prob",
    "series_market_available",
    # Round context / matchup.
    "opponent_team_abbrev",
    "matchup_available",
    "home_ice_advantage",
    "head_to_head_win_pct",
    "head_to_head_games",
    "expected_opponent_strength",
)


@dataclass(frozen=True)
class EloConfig:
    """Elo update knobs.

    ``k``: learning rate per game. ``home_advantage``: rating points added to the
    home team before computing the expectation. ``initial``: rating for a
    first-seen team (and the mean that seasons regress toward).
    ``season_regression``: fraction of a team's deviation from the mean shed at
    each season boundary (0 = full carryover, 1 = full reset).
    """

    k: float = 20.0
    home_advantage: float = 50.0
    initial: float = 1500.0
    season_regression: float = 0.25


@dataclass(frozen=True)
class TeamSeriesFeatureConfig:
    """Tunable knobs for team/series feature construction.

    ``goalie_last_n``: window for the last-N save-percentage proxy (AC: 15).
    ``min_games``: minimum regular-season games before the cutoff for a team to
    appear in the matrix.
    """

    goalie_last_n: int = 15
    min_games: int = 1


# ── Scalar / small pure primitives (each unit-tested) ────────────────────


def goal_differential_per_game(goals_for: float, goals_against: float, games: float) -> float:
    """As-of goal differential per game ``(GF - GA) / GP`` (0.0 when GP is 0)."""
    if games == 0:
        return 0.0
    return (float(goals_for) - float(goals_against)) / float(games)


def save_pct(goals_against: float, shots_against: float) -> float:
    """Team-level save percentage ``1 - GA / shots-against`` over as-of games.

    Returns ``0.0`` when no shots were faced. This is a *team* goaltending proxy
    (the league's goalie slot is a team's goaltending), not a per-goalie figure.
    """
    if shots_against == 0:
        return 0.0
    return 1.0 - (float(goals_against) / float(shots_against))


def days_between(dates: list[pd.Timestamp]) -> float:
    """Mean gap in days between consecutive sorted game dates.

    Schedule-density proxy. Returns ``0.0`` for fewer than two dates (no gap).
    """
    if len(dates) < 2:
        return 0.0
    ordered = sorted(dates)
    diffs = [(b - a).days for a, b in itertools.pairwise(ordered)]
    return float(sum(diffs)) / float(len(diffs))


def expected_score(rating_a: float, rating_b: float, home_advantage: float = 0.0) -> float:
    """Elo win expectation for team A vs. team B (A optionally home).

    Standard logistic Elo: ``1 / (1 + 10 ** ((Rb - (Ra + home_adv)) / 400))``.
    ``home_advantage`` is added to A's rating before the comparison.
    """
    return float(1.0 / (1.0 + 10.0 ** ((rating_b - (rating_a + home_advantage)) / 400.0)))


def update_rating(rating: float, expected: float, actual: float, k: float) -> float:
    """Elo post-game rating ``R + k * (actual - expected)`` (unit-tested)."""
    return float(rating) + float(k) * (float(actual) - float(expected))


def regress_to_mean(rating: float, mean: float, fraction: float) -> float:
    """Shrink a rating toward ``mean`` by ``fraction`` (season carryover)."""
    return float(mean) + (float(rating) - float(mean)) * (1.0 - float(fraction))


# ── Elo replay ───────────────────────────────────────────────────────────


def compute_elo_ratings(
    team_games: pd.DataFrame,
    *,
    as_of_date: str | pd.Timestamp,
    config: EloConfig | None = None,
) -> dict[str, float]:
    """As-of Elo rating per team, replayed across seasons before the cutoff.

    Each game is processed once (from the home row), in chronological order,
    using only games strictly before ``as_of_date`` (leakage-guarded). At every
    season boundary each rating regresses toward :attr:`EloConfig.initial`. A
    tie (impossible in real playoff/regulation-or-OT hockey but tolerated in
    fixtures) scores 0.5 for both sides.
    """
    config = config or EloConfig()
    cutoff = to_cutoff(as_of_date)
    before = as_of(team_games, cutoff)
    assert_no_leakage(before, cutoff)

    home = before.loc[before["home_road"] == "H"].copy()
    home = home.sort_values(["game_date", "game_id"], kind="stable")

    ratings: dict[str, float] = {}
    last_season: int | None = None
    for record in home.to_dict("records"):
        season = int(record["season_id"])
        if last_season is not None and season != last_season:
            ratings = {
                team: regress_to_mean(rating, config.initial, config.season_regression)
                for team, rating in ratings.items()
            }
        last_season = season

        home_team = str(record["team_abbrev"])
        away_team = str(record["opponent_team_abbrev"])
        rating_home = ratings.setdefault(home_team, config.initial)
        rating_away = ratings.setdefault(away_team, config.initial)

        exp_home = expected_score(rating_home, rating_away, config.home_advantage)
        gf = float(record["goals_for"])
        ga = float(record["goals_against"])
        if gf > ga:
            actual_home = 1.0
        elif gf < ga:
            actual_home = 0.0
        else:
            actual_home = 0.5

        ratings[home_team] = update_rating(rating_home, exp_home, actual_home, config.k)
        ratings[away_team] = update_rating(rating_away, 1.0 - exp_home, 1.0 - actual_home, config.k)
    return ratings


# ── Frame-level helpers ──────────────────────────────────────────────────


def _team_reg_aggregates(reg: pd.DataFrame) -> pd.DataFrame:
    """Per-team regular-season aggregates as of the cutoff."""
    grouped = reg.groupby("team_abbrev", as_index=False).agg(
        team_id=("team_id", "first"),
        games_played=("game_id", "nunique"),
        goals_for=("goals_for", "sum"),
        goals_against=("goals_against", "sum"),
        wins=("win", "sum"),
        shutout_wins=("shutout_win", "sum"),
        shots_for_sum=("shots_for", "sum"),
        shots_against_sum=("shots_against", "sum"),
        power_play_pct=("power_play_pct", "mean"),
        penalty_kill_pct=("penalty_kill_pct", "mean"),
        faceoff_win_pct=("faceoff_win_pct", "mean"),
        shots_for_per_game=("shots_for", "mean"),
        shots_against_per_game=("shots_against", "mean"),
    )
    return grouped


def _save_pct_l15(reg: pd.DataFrame, last_n: int) -> pd.DataFrame:
    """Team save-percentage proxy over each team's most recent ``last_n`` games."""
    ordered = reg.sort_values(["team_abbrev", "game_date"])
    recent = ordered.groupby("team_abbrev", as_index=False, group_keys=False).tail(last_n)
    agg = recent.groupby("team_abbrev", as_index=False).agg(
        ga=("goals_against", "sum"),
        sa=("shots_against", "sum"),
    )
    agg["starter_save_pct_l15"] = [
        save_pct(ga, sa) for ga, sa in zip(agg["ga"], agg["sa"], strict=True)
    ]
    return agg[["team_abbrev", "starter_save_pct_l15"]]


def _rest_and_density(before: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Rest days (cutoff minus last game) and mean days-between-games per team."""
    cutoff_date = cutoff.date()
    rows: list[dict[str, object]] = []
    for team, group in before.groupby("team_abbrev"):
        dates = sorted({pd.Timestamp(d) for d in pd.to_datetime(group["game_date"]).tolist()})
        last_game = dates[-1]
        rows.append(
            {
                "team_abbrev": team,
                "rest_days": float((cutoff_date - last_game.date()).days),
                "days_between_games": days_between(dates),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["team_abbrev", "rest_days", "days_between_games"])
    return pd.DataFrame(rows)


def _market_implied(
    odds: pd.DataFrame, *, season_end_year: int, cutoff: pd.Timestamp
) -> pd.DataFrame:
    """Average de-vigged implied win probability per team from the odds table.

    Uses regular-season games in ``season_end_year`` played strictly before the
    cutoff. Returns one row per ``team_id`` with ``market_implied_win_prob``.
    """
    empty = pd.DataFrame(columns=["team_id", "market_implied_win_prob"])
    if odds.empty:
        return empty
    scoped = odds.loc[odds["season_end_year"] == season_end_year].copy()
    scoped["_date"] = pd.to_datetime(scoped["game_date"], errors="coerce")
    scoped = scoped.loc[scoped["_date"] < cutoff]
    if "is_playoff" in scoped.columns:
        scoped = scoped.loc[~scoped["is_playoff"].fillna(False).astype(bool)]
    if scoped.empty:
        return empty

    home = scoped[["home_team_id", "home_implied"]].rename(
        columns={"home_team_id": "team_id", "home_implied": "implied"}
    )
    away = scoped[["away_team_id", "away_implied"]].rename(
        columns={"away_team_id": "team_id", "away_implied": "implied"}
    )
    stacked = pd.concat([home, away], ignore_index=True)
    stacked = stacked.dropna(subset=["team_id", "implied"])
    if stacked.empty:
        return empty
    stacked["team_id"] = stacked["team_id"].astype(int)
    out = stacked.groupby("team_id", as_index=False).agg(
        market_implied_win_prob=("implied", "mean")
    )
    return out


def _injured_goalie_teams(injuries: pd.DataFrame | None) -> set[str]:
    """Team abbrevs with an unavailable goalie in the (current) injuries table."""
    if injuries is None or injuries.empty:
        return set()
    if "position" not in injuries.columns or "status" not in injuries.columns:
        return set()
    goalies = injuries.loc[injuries["position"].fillna("").str.upper() == "G"]
    unavailable = goalies.loc[goalies["status"].isin(UNAVAILABLE_STATUSES)]
    abbrevs = unavailable["team_abbrev"].dropna().astype(str)
    return set(abbrevs.tolist())


def _apply_matchups(out: pd.DataFrame, reg: pd.DataFrame, matchups: pd.DataFrame | None) -> None:
    """Attach opponent, home-ice, head-to-head, and expected-strength columns.

    Mutates ``out`` in place. When ``matchups`` is ``None`` every matchup-derived
    column stays at its missing default and ``matchup_available`` is ``False``.
    """
    if matchups is None or matchups.empty:
        return
    lookup = matchups.set_index("team_abbrev")
    elo = dict(zip(out["team_abbrev"], out["elo_rating"], strict=True))
    for idx, team in out["team_abbrev"].items():
        if team not in lookup.index:
            continue
        row = lookup.loc[team]
        opponent = row.get("opponent_team_abbrev")
        home_ice = bool(row.get("home_ice", False))
        out.at[idx, "matchup_available"] = True
        out.at[idx, "opponent_team_abbrev"] = opponent
        out.at[idx, "home_ice_advantage"] = 1.0 if home_ice else 0.0
        if opponent is not None and not (isinstance(opponent, float) and pd.isna(opponent)):
            h2h = reg.loc[(reg["team_abbrev"] == team) & (reg["opponent_team_abbrev"] == opponent)]
            games = int(h2h["game_id"].nunique())
            wins = int(h2h["win"].fillna(False).astype(bool).sum())
            out.at[idx, "head_to_head_games"] = float(games)
            out.at[idx, "head_to_head_win_pct"] = (wins / games) if games else 0.0
            if opponent in elo:
                out.at[idx, "expected_opponent_strength"] = float(elo[opponent])
        series_prob = row.get("series_implied_win_prob")
        if series_prob is not None and not (
            isinstance(series_prob, float) and pd.isna(series_prob)
        ):
            out.at[idx, "series_implied_win_prob"] = float(series_prob)
            out.at[idx, "series_market_available"] = True


def build_team_series_features(
    team_games: pd.DataFrame,
    *,
    season_id: int,
    as_of_date: str | pd.Timestamp,
    playoff_round: int | None = None,
    matchups: pd.DataFrame | None = None,
    odds: pd.DataFrame | None = None,
    injuries: pd.DataFrame | None = None,
    elo_config: EloConfig | None = None,
    config: TeamSeriesFeatureConfig | None = None,
) -> pd.DataFrame:
    """Build the as-of team/series feature matrix for one round start.

    One row per team with at least ``config.min_games`` regular-season games in
    ``season_id`` before ``as_of_date``. Every game input is leakage-guarded, so
    no round-``N`` game can enter a round-``N`` feature. Optional ``matchups``,
    ``odds``, and ``injuries`` frames enrich the row and set the corresponding
    ``*_available`` missing-flags; when omitted those columns stay at their
    documented missing defaults.
    """
    config = config or TeamSeriesFeatureConfig()
    cutoff = to_cutoff(as_of_date)

    season_rows = team_games.loc[team_games["season_id"] == season_id]
    before = as_of(season_rows, cutoff)
    assert_no_leakage(before, cutoff)

    reg = before.loc[before["game_type_id"] == REGULAR_SEASON_GAME_TYPE]
    if reg.empty:
        return pd.DataFrame(columns=list(TEAM_FEATURE_COLUMNS))

    agg = _team_reg_aggregates(reg)
    agg = agg.loc[agg["games_played"] >= config.min_games]
    if agg.empty:
        return pd.DataFrame(columns=list(TEAM_FEATURE_COLUMNS))

    agg["goals_for_per_game"] = agg["goals_for"] / agg["games_played"]
    agg["goals_against_per_game"] = agg["goals_against"] / agg["games_played"]
    agg["goal_differential_per_game"] = [
        goal_differential_per_game(gf, ga, gp)
        for gf, ga, gp in zip(
            agg["goals_for"], agg["goals_against"], agg["games_played"], strict=True
        )
    ]
    agg["starter_save_pct_season"] = [
        save_pct(ga, sa)
        for ga, sa in zip(agg["goals_against"], agg["shots_against_sum"], strict=True)
    ]
    agg["team_shutout_rate"] = agg["shutout_wins"] / agg["games_played"]

    save_l15 = _save_pct_l15(reg, config.goalie_last_n)
    rest = _rest_and_density(before, cutoff)
    ratings = compute_elo_ratings(team_games, as_of_date=cutoff, config=elo_config)

    out = agg.merge(save_l15, on="team_abbrev", how="left").merge(
        rest, on="team_abbrev", how="left"
    )
    out["elo_rating"] = out["team_abbrev"].map(ratings).fillna((elo_config or EloConfig()).initial)

    # Goaltender situation — team-level proxy; per-goalie split unavailable.
    out["backup_save_pct"] = pd.NA
    out["goalie_split_available"] = False
    injured_teams = _injured_goalie_teams(injuries)
    out["goalie_injury_data_available"] = injuries is not None and not injuries.empty
    out["starter_unavailability_risk"] = out["team_abbrev"].isin(injured_teams)

    # Market join (explicit missing-flags).
    season_end_year = season_id % 10000
    market = (
        _market_implied(odds, season_end_year=season_end_year, cutoff=cutoff)
        if odds is not None
        else pd.DataFrame(columns=["team_id", "market_implied_win_prob"])
    )
    out = out.merge(market, on="team_id", how="left")
    out["market_available"] = out["market_implied_win_prob"].notna()
    out["market_implied_win_prob"] = out["market_implied_win_prob"].astype(float)

    # Matchup / round-context defaults, then enrichment.
    out["season_id"] = season_id
    out["playoff_round"] = playoff_round
    out["as_of_date"] = cutoff.strftime("%Y-%m-%d")
    out["opponent_team_abbrev"] = pd.NA
    out["matchup_available"] = False
    out["home_ice_advantage"] = 0.0
    out["head_to_head_win_pct"] = 0.0
    out["head_to_head_games"] = 0.0
    out["expected_opponent_strength"] = pd.NA
    out["series_implied_win_prob"] = pd.NA
    out["series_market_available"] = False

    out = out.reset_index(drop=True)
    _apply_matchups(out, reg, matchups)

    numeric_defaults = {
        "starter_save_pct_l15": 0.0,
        "rest_days": 0.0,
        "days_between_games": 0.0,
        "power_play_pct": 0.0,
        "penalty_kill_pct": 0.0,
        "faceoff_win_pct": 0.0,
    }
    out = out.fillna(numeric_defaults)

    out = out.reindex(columns=list(TEAM_FEATURE_COLUMNS))
    return out.sort_values(
        ["goal_differential_per_game", "team_abbrev"], ascending=[False, True]
    ).reset_index(drop=True)


def build_round_team_series_matrix(
    team_games: pd.DataFrame,
    *,
    season_id: int,
    round_start_dates: dict[int, str],
    matchups_by_round: dict[int, pd.DataFrame] | None = None,
    odds: pd.DataFrame | None = None,
    injuries: pd.DataFrame | None = None,
    elo_config: EloConfig | None = None,
    config: TeamSeriesFeatureConfig | None = None,
) -> pd.DataFrame:
    """Stack per-round team/series features for one season.

    ``round_start_dates`` maps a playoff round to its start date (the exclusive
    as-of cutoff). Each round is built independently, so a round-``N`` feature can
    never see round-``N`` (or later) games. Per-round matchup frames may be
    supplied via ``matchups_by_round``.
    """
    matchups_by_round = matchups_by_round or {}
    frames = [
        build_team_series_features(
            team_games,
            season_id=season_id,
            as_of_date=start,
            playoff_round=rnd,
            matchups=matchups_by_round.get(rnd),
            odds=odds,
            injuries=injuries,
            elo_config=elo_config,
            config=config,
        )
        for rnd, start in sorted(round_start_dates.items())
    ]
    if not frames:
        return pd.DataFrame(columns=list(TEAM_FEATURE_COLUMNS))
    return pd.concat(frames, ignore_index=True)
