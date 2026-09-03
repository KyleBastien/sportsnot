"""As-of skater feature engineering (US-009, PRD US-004 part 1).

Produces one feature row per skater per playoff round, computed *as of the round
start* so the projection model (US-011+) never trains on future information. All
game inputs pass through :mod:`draft_oracle.features.leakage`, which enforces the
strict cutoff and fails the build on any leak.

Every feature is a small, unit-tested pure function with a docstring stating its
as-of semantics. The public entry points are :func:`build_skater_features` (one
round) and :func:`build_round_feature_matrix` (all rounds of a season). Matrices
are written under ``data/features/<FEATURE_SET_VERSION>/`` by
:func:`write_feature_matrix`.

As-of semantics (shared by every feature here):
    Inputs are filtered to a single ``season_id`` and to games played *strictly
    before* the round-start ``as_of_date``. Regular-season aggregates use only
    ``game_type_id == 2`` games; the "last N" window uses the most recent games
    of any type within the season before the cutoff. No game on/after the cutoff
    is ever read.

Data-availability caveats (documented, not hidden):
    * The committed NHL archive has no power-play *time* column, so
      "power-play time share" is proxied by power-play *production*:
      :func:`pp_point_share` (PP points / total points) plus a PP points/game
      rate. Documented here so the proxy is never mistaken for true PP TOI.
    * ``avg_toi_seconds`` is the mean of the per-game ``toi_seconds`` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from draft_oracle.features.leakage import as_of, assert_no_leakage, to_cutoff

__all__ = [
    "FEATURE_COLUMNS",
    "FEATURE_SET_VERSION",
    "RoundFeatureMatrixRequest",
    "SkaterFeatureConfig",
    "SkaterFeatureRequest",
    "age_years",
    "build_round_feature_matrix",
    "build_skater_features",
    "linemate_ppg",
    "per_game",
    "pp_point_share",
    "safe_ratio",
    "shooting_pct",
    "write_feature_matrix",
]

FEATURE_SET_VERSION = "skater-v1"

DEFAULT_FEATURES_DIR = Path("data/features")

REGULAR_SEASON_GAME_TYPE = 2

FEATURE_COLUMNS: tuple[str, ...] = (
    "season_id",
    "playoff_round",
    "as_of_date",
    "player_id",
    "player_name",
    "position",
    "team_abbrev",
    "games_played",
    "goals_per_game",
    "assists_per_game",
    "points_per_game",
    "goals_per_game_l25",
    "assists_per_game_l25",
    "points_per_game_l25",
    "pp_points_per_game",
    "pp_point_share",
    "avg_toi_seconds",
    "shots_per_game",
    "shooting_pct",
    "age_years",
    "linemate_ppg",
    "team_goals_for_per_game",
)


@dataclass(frozen=True)
class SkaterFeatureConfig:
    """Tunable knobs for skater feature construction.

    ``last_n_games``: window length for recent-form rates (SPEC lists 25).
    ``min_games``: minimum regular-season games before the cutoff for a skater to
    appear in the matrix (drops tiny, unstable samples).
    """

    last_n_games: int = 25
    min_games: int = 1


@dataclass(frozen=True)
class SkaterFeatureRequest:
    season_id: int
    as_of_date: str | pd.Timestamp
    playoff_round: int | None = None
    config: SkaterFeatureConfig | None = None


@dataclass(frozen=True)
class RoundFeatureMatrixRequest:
    season_id: int
    round_start_dates: dict[int, str]
    config: SkaterFeatureConfig | None = None


# ── Scalar feature primitives (each unit-tested) ─────────────────────────


def safe_ratio(numerator: float, denominator: float) -> float:
    """Return ``numerator / denominator`` or ``0.0`` when ``denominator`` is 0.

    Used for every per-game / share feature so a zero-sample skater yields a
    defined ``0.0`` rather than ``inf``/``NaN``.
    """
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def per_game(total: float, games_played: float) -> float:
    """Per-game rate of a counting stat as of the cutoff (``total / GP``)."""
    return safe_ratio(total, games_played)


def shooting_pct(goals: float, shots: float) -> float:
    """Shooting percentage ``goals / shots`` over as-of games (0.0 if no shots)."""
    return safe_ratio(goals, shots)


def pp_point_share(pp_points: float, points: float) -> float:
    """Share of a skater's as-of points that came on the power play.

    Proxy for "power-play time share": the archive has no PP TOI column, so PP
    *production* stands in. Range ``[0, 1]``; ``0.0`` when the skater has no
    points as of the cutoff.
    """
    return safe_ratio(pp_points, points)


def age_years(
    birth_date: str | pd.Timestamp | float | None, as_of_date: str | pd.Timestamp
) -> float:
    """Age in years as of the round start (``(cutoff - birth) / 365.25``).

    Returns ``0.0`` for an unknown/missing birth date so the feature stays
    numeric and leakage-free (age uses no game data).
    """
    missing_float = isinstance(birth_date, float) and pd.isna(birth_date)
    if birth_date is None or missing_float:
        return 0.0
    birth = pd.to_datetime(birth_date, errors="coerce")
    if pd.isna(birth):
        return 0.0
    cutoff = to_cutoff(as_of_date)
    return float((cutoff - birth).days) / 365.25


def linemate_ppg(team_points_per_game: list[float], player_index: int) -> float:
    """Leave-one-out mean points/game of a skater's regular-season teammates.

    Teammate-quality proxy: the average as-of PPG of every *other* skater who
    logged regular-season games on the same team. With a single-member team the
    skater's own PPG is returned (no teammates to average). Uses only pre-cutoff
    regular-season games, so it is leakage-free.
    """
    n = len(team_points_per_game)
    if n == 0:
        return 0.0
    if n == 1:
        return float(team_points_per_game[player_index])
    total = float(sum(team_points_per_game))
    others = total - float(team_points_per_game[player_index])
    return others / (n - 1)


# ── Frame-level builders ─────────────────────────────────────────────────


def _regular_aggregates(reg_games: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-player regular-season counting stats (as-of, pre-cutoff)."""
    if reg_games.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "games_played",
                "goals",
                "assists",
                "shots",
                "pp_points",
                "toi_seconds",
                "team_abbrev",
            ]
        )
    grouped = reg_games.groupby("player_id", as_index=False).agg(
        games_played=("game_id", "nunique"),
        goals=("goals", "sum"),
        assists=("assists", "sum"),
        shots=("shots", "sum"),
        pp_points=("pp_points", "sum"),
        toi_seconds=("toi_seconds", "mean"),
    )
    reg_team = _dominant_team(reg_games)
    return grouped.merge(reg_team, on="player_id", how="left")


def _dominant_team(games: pd.DataFrame) -> pd.DataFrame:
    """Most-frequent ``team_abbrev`` per player over ``games`` (ties → latest)."""
    counts = (
        games.groupby(["player_id", "team_abbrev"], as_index=False)
        .agg(n=("game_id", "nunique"), latest=("game_date", "max"))
        .sort_values(["player_id", "n", "latest"], ascending=[True, False, False])
    )
    top = counts.drop_duplicates(subset=["player_id"], keep="first")
    return top[["player_id", "team_abbrev"]].reset_index(drop=True)


def _last_n_rates(season_games: pd.DataFrame, last_n: int) -> pd.DataFrame:
    """Per-player rates over each skater's most recent ``last_n`` as-of games."""
    if season_games.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "goals_per_game_l25",
                "assists_per_game_l25",
                "points_per_game_l25",
            ]
        )
    ordered = season_games.sort_values(["player_id", "game_date"])
    recent = ordered.groupby("player_id", as_index=False, group_keys=False).tail(last_n)
    agg = recent.groupby("player_id", as_index=False).agg(
        gp=("game_id", "nunique"),
        goals=("goals", "sum"),
        assists=("assists", "sum"),
    )
    agg["goals_per_game_l25"] = [
        per_game(g, n) for g, n in zip(agg["goals"], agg["gp"], strict=True)
    ]
    agg["assists_per_game_l25"] = [
        per_game(a, n) for a, n in zip(agg["assists"], agg["gp"], strict=True)
    ]
    agg["points_per_game_l25"] = [
        per_game(g + a, n) for g, a, n in zip(agg["goals"], agg["assists"], agg["gp"], strict=True)
    ]
    return agg[
        [
            "player_id",
            "goals_per_game_l25",
            "assists_per_game_l25",
            "points_per_game_l25",
        ]
    ]


def _team_offense_rates(reg_team_games: pd.DataFrame) -> pd.DataFrame:
    """Regular-season goals-for per game per team, as of the cutoff."""
    if reg_team_games.empty:
        return pd.DataFrame(columns=["team_abbrev", "team_goals_for_per_game"])
    grouped = reg_team_games.groupby("team_abbrev", as_index=False).agg(
        gp=("game_id", "nunique"),
        goals_for=("goals_for", "sum"),
    )
    grouped["team_goals_for_per_game"] = [
        per_game(gf, gp) for gf, gp in zip(grouped["goals_for"], grouped["gp"], strict=True)
    ]
    return grouped[["team_abbrev", "team_goals_for_per_game"]]


def _linemate_frame(reg: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-out teammate PPG per player from regular-season aggregates."""
    reg = reg.copy()
    reg["ppg"] = [
        per_game(g + a, n)
        for g, a, n in zip(reg["goals"], reg["assists"], reg["games_played"], strict=True)
    ]
    rows: list[dict[str, object]] = []
    for _team, members in reg.groupby("team_abbrev"):
        ppgs = [float(x) for x in members["ppg"].tolist()]
        ids = members["player_id"].tolist()
        for idx, player_id in enumerate(ids):
            rows.append({"player_id": player_id, "linemate_ppg": linemate_ppg(ppgs, idx)})
    if not rows:
        return pd.DataFrame(columns=["player_id", "linemate_ppg"])
    return pd.DataFrame.from_records(rows)


def _player_meta(players: pd.DataFrame, as_of_date: str | pd.Timestamp) -> pd.DataFrame:
    """Position + age lookup per player from the players table (no game data)."""
    meta = players[["player_id", "player_name", "position", "birth_date"]].copy()
    meta["age_years"] = [age_years(b, as_of_date) for b in meta["birth_date"]]
    return meta[["player_id", "player_name", "position", "age_years"]]


def _empty_feature_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(FEATURE_COLUMNS))


def _season_as_of_skaters(
    skater_games: pd.DataFrame, season_id: int, cutoff: pd.Timestamp
) -> pd.DataFrame:
    season_skaters = skater_games.loc[skater_games["season_id"] == season_id]
    before = as_of(season_skaters, cutoff)
    assert_no_leakage(before, cutoff)
    return before


def _regular_feature_rates(reg_agg: pd.DataFrame) -> pd.DataFrame:
    reg_agg = reg_agg.copy()
    games_played = reg_agg["games_played"]
    goals = reg_agg["goals"]
    assists = reg_agg["assists"]
    reg_agg["goals_per_game"] = [
        per_game(g, n) for g, n in zip(goals, games_played, strict=True)
    ]
    reg_agg["assists_per_game"] = [
        per_game(a, n) for a, n in zip(assists, games_played, strict=True)
    ]
    reg_agg["points_per_game"] = [
        per_game(g + a, n) for g, a, n in zip(goals, assists, games_played, strict=True)
    ]
    reg_agg["pp_points_per_game"] = [
        per_game(p, n) for p, n in zip(reg_agg["pp_points"], games_played, strict=True)
    ]
    reg_agg["pp_point_share"] = [
        pp_point_share(p, g + a)
        for p, g, a in zip(reg_agg["pp_points"], goals, assists, strict=True)
    ]
    reg_agg["shots_per_game"] = [
        per_game(s, n) for s, n in zip(reg_agg["shots"], games_played, strict=True)
    ]
    reg_agg["shooting_pct"] = [
        shooting_pct(g, s) for g, s in zip(goals, reg_agg["shots"], strict=True)
    ]
    reg_agg["avg_toi_seconds"] = reg_agg["toi_seconds"].fillna(0.0).astype(float)
    return reg_agg


def _team_offense_for_cutoff(
    team_games: pd.DataFrame, season_id: int, cutoff: pd.Timestamp
) -> pd.DataFrame:
    team_scope = as_of(team_games.loc[team_games["season_id"] == season_id], cutoff)
    reg_team_games = team_scope.loc[
        lambda df: df["game_type_id"] == REGULAR_SEASON_GAME_TYPE
    ]
    return _team_offense_rates(reg_team_games)


def _final_feature_frame(
    out: pd.DataFrame,
    *,
    season_id: int,
    playoff_round: int | None,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    out["season_id"] = season_id
    out["playoff_round"] = playoff_round
    out["as_of_date"] = cutoff.strftime("%Y-%m-%d")
    out = out.fillna(
        {
            "goals_per_game_l25": 0.0,
            "assists_per_game_l25": 0.0,
            "points_per_game_l25": 0.0,
            "linemate_ppg": 0.0,
            "team_goals_for_per_game": 0.0,
            "age_years": 0.0,
        }
    )
    out = out.reindex(columns=list(FEATURE_COLUMNS))
    return out.sort_values(["points_per_game", "player_id"], ascending=[False, True]).reset_index(
        drop=True
    )


def build_skater_features(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    request: SkaterFeatureRequest,
) -> pd.DataFrame:
    """Build the as-of skater feature matrix for one round start.

    Filters every input to ``request.season_id`` and to games strictly before
    ``request.as_of_date`` (via :func:`as_of`), asserts the no-leakage invariant, then
    joins the per-feature builders into one row per pooled skater (position
    ``F``/``D``) with at least ``request.config.min_games`` regular-season games.
    """
    config = request.config or SkaterFeatureConfig()
    cutoff = to_cutoff(request.as_of_date)

    before = _season_as_of_skaters(skater_games, request.season_id, cutoff)
    reg = before.loc[before["game_type_id"] == REGULAR_SEASON_GAME_TYPE]
    reg_agg = _regular_aggregates(reg)
    reg_agg = reg_agg.loc[reg_agg["games_played"] >= config.min_games]

    if reg_agg.empty:
        return _empty_feature_frame()

    reg_agg = _regular_feature_rates(reg_agg)
    meta = _player_meta(players, cutoff)
    reg_agg = reg_agg.merge(meta, on="player_id", how="left")
    reg_agg = reg_agg.loc[reg_agg["position"].isin(["F", "D"])]
    if reg_agg.empty:
        return _empty_feature_frame()

    last_n = _last_n_rates(before, config.last_n_games)
    team_offense = _team_offense_for_cutoff(team_games, request.season_id, cutoff)
    linemates = _linemate_frame(reg_agg)

    out = (
        reg_agg.merge(last_n, on="player_id", how="left")
        .merge(linemates, on="player_id", how="left")
        .merge(team_offense, on="team_abbrev", how="left")
    )
    return _final_feature_frame(
        out,
        season_id=request.season_id,
        playoff_round=request.playoff_round,
        cutoff=cutoff,
    )


def build_round_feature_matrix(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    request: RoundFeatureMatrixRequest,
) -> pd.DataFrame:
    """Stack per-round skater features for one season.

    ``round_start_dates`` maps a playoff round number to its start date (the
    exclusive as-of cutoff). Each round is built independently, so a feature for
    round ``N`` can never see round-``N`` (or later) games.
    """
    frames = [
        build_skater_features(
            skater_games,
            players,
            team_games,
            SkaterFeatureRequest(
                season_id=request.season_id,
                as_of_date=start,
                playoff_round=rnd,
                config=request.config,
            ),
        )
        for rnd, start in sorted(request.round_start_dates.items())
    ]
    if not frames:
        return pd.DataFrame(columns=list(FEATURE_COLUMNS))
    return pd.concat(frames, ignore_index=True)


def write_feature_matrix(
    matrix: pd.DataFrame,
    *,
    features_dir: Path = DEFAULT_FEATURES_DIR,
    version: str = FEATURE_SET_VERSION,
    name: str = "skater_features",
) -> Path:
    """Write a feature matrix to ``<features_dir>/<version>/<name>.parquet``.

    The versioned directory keys the matrix to its feature-set version so a
    schema change is a new directory, never an in-place overwrite. Returns the
    written path. ``data/features/`` is gitignored (SPEC §4).
    """
    out_dir = features_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.parquet"
    matrix.to_parquet(path, index=False)
    return path
