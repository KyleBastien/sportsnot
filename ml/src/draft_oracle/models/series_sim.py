"""Best-of-7 series simulator and goalie-slot valuation (US-013, PRD US-005 part 3).

Composes the per-game win model (US-011) and the per-game shutout model (US-012)
into a full best-of-7 series-outcome distribution. Every playoff round in this
league is a best-of-7 with the **2-2-1-1-1** home-ice pattern (SPEC section 1):
the higher seed hosts games 1, 2, 5, and 7; the lower seed hosts games 3, 4, 6.

For a single series the simulator returns, per team, ``P(win series)``, the
distribution over 4/5/6/7-game outcomes, ``E[wins]``, ``E[games]``, and
``E[goalie-slot points]``. The goalie slot is an entire NHL team's goaltending,
scored through the rules engine (SPEC section 1): a win is worth
:data:`~draft_oracle.rules.WIN_POINTS` and a shutout win *replaces* that with
:data:`~draft_oracle.rules.SHUTOUT_POINTS` (never additive). Expected goalie
points are therefore linear in expected wins::

    E[goalie points] = E[wins] * (WIN_POINTS + (SHUTOUT_POINTS - WIN_POINTS) * P(shutout | win))

which is exactly ``2 * E[wins] + 2 * E[shutout wins]`` — the mean of
:func:`draft_oracle.rules.goalie_series_points` over the series.

**Exact enumeration, not Monte Carlo.** A best-of-7 has at most ``2**7 = 128``
game sequences, so the outcome distribution is enumerated exactly
(:func:`simulate_series`) — deterministic with no seed required. A seeded
Monte-Carlo variant (:func:`simulate_series_monte_carlo`) exists only to
cross-check the exact result and to satisfy the "deterministic under a fixed
seed" contract for any stochastic path.

The evaluation entry point (:func:`evaluate_series_sim_from_normalized`) fits the
per-game win and shutout models on the non-held-out seasons, replays every
historical series through the simulator, and writes a calibration report:
reliability curve + Brier score for series winners, predicted-vs-actual
series-length distribution, and predicted-vs-actual shutouts per round. Honesty
rules (SPEC section 7) apply: held-out seasons never touch model training, and
every metric is reported as measured.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from draft_oracle.features.elo import (
    EloConfig,
    expected_score,
    regress_to_mean,
    update_rating,
)
from draft_oracle.models.game_win import (
    PLAYOFF_GAME_TYPE,
    REGULAR_SEASON_GAME_TYPE,
    GameWinConfig,
    GameWinModel,
    TeamState,
    brier_score,
    train_game_win_model,
)
from draft_oracle.models.shutout import (
    ShutoutConfig,
    ShutoutModel,
    ShutoutTeamState,
    train_shutout_model,
)
from draft_oracle.models.skater_production import (
    QUALIFYING_ROUND_GAME_DIGIT,
    _playoff_round_digit,
    _series_round_map,
    playoff_round_cutoffs,
)
from draft_oracle.provenance import add_git_provenance
from draft_oracle.rules import SHUTOUT_POINTS, WIN_POINTS

__all__ = [
    "HOME_ICE_PATTERN",
    "SERIES_SIM_VERSION",
    "WINS_NEEDED",
    "LengthBin",
    "SeriesCalibrationBin",
    "SeriesOutcome",
    "SeriesSimConfig",
    "SeriesSimResult",
    "evaluate_series_sim_from_normalized",
    "expected_goalie_points",
    "game_win_probs",
    "series_length_labels",
    "simulate_series",
    "simulate_series_monte_carlo",
    "train_series_sim_from_normalized",
]

SERIES_SIM_VERSION = "series-sim-v1"

# First team to this many wins takes the best-of-7 series.
WINS_NEEDED = 4

# 2-2-1-1-1 home-ice pattern, games 1..7 (SPEC section 1). "A" is the higher seed
# (home-ice team); "B" is the lower seed. A hosts games 1, 2, 5, 7; B hosts 3, 4, 6.
HOME_ICE_PATTERN: tuple[str, ...] = ("A", "A", "B", "B", "A", "B", "A")

# Possible series lengths for a best-of-7.
_SERIES_LENGTHS: tuple[int, ...] = (4, 5, 6, 7)


def series_length_labels() -> tuple[int, ...]:
    """The four possible best-of-7 series lengths, ``(4, 5, 6, 7)``."""
    return _SERIES_LENGTHS


def game_win_probs(p_a_home: float, p_a_away: float) -> tuple[float, ...]:
    """Per-game ``P(team A wins game i)`` for the seven games of the series.

    ``p_a_home`` is the probability A wins a game it hosts; ``p_a_away`` the
    probability A wins a game it visits. The venue for each game follows
    :data:`HOME_ICE_PATTERN` (2-2-1-1-1), so games 1, 2, 5, 7 use ``p_a_home`` and
    games 3, 4, 6 use ``p_a_away``. The returned tuple is length 7 regardless of
    how many games the series actually needs.
    """
    return tuple(float(p_a_home) if venue == "A" else float(p_a_away) for venue in HOME_ICE_PATTERN)


def expected_goalie_points(expected_wins: float, shutout_prob: float) -> float:
    """Expected goalie-slot points for a team, through the rules engine.

    A win scores :data:`~draft_oracle.rules.WIN_POINTS`; a shutout win *replaces*
    it with :data:`~draft_oracle.rules.SHUTOUT_POINTS`. With each win independently
    a shutout with probability ``shutout_prob`` the expectation is linear in
    expected wins::

        E[pts] = E[wins] * (WIN_POINTS + (SHUTOUT_POINTS - WIN_POINTS) * shutout_prob)

    which equals the mean of :func:`draft_oracle.rules.goalie_series_points`.
    """
    per_win = WIN_POINTS + (SHUTOUT_POINTS - WIN_POINTS) * float(shutout_prob)
    return float(expected_wins) * per_win


@dataclass(frozen=True)
class SeriesOutcome:
    """The full outcome distribution of one best-of-7 series (A = higher seed).

    ``length_probs`` maps each series length (4/5/6/7) to its probability; the
    four values sum to 1. ``e_goalie_points_*`` route expected wins + shutout
    upside through the rules engine (:func:`expected_goalie_points`).
    """

    p_a_win_series: float
    p_b_win_series: float
    length_probs: dict[int, float]
    e_games: float
    e_wins_a: float
    e_wins_b: float
    e_goalie_points_a: float
    e_goalie_points_b: float


def _enumerate_paths(per_game: Sequence[float]) -> list[tuple[float, str, int, int]]:
    """Exhaustively enumerate every series path and its probability.

    ``per_game[i]`` is ``P(A wins game i)``. Each returned tuple is
    ``(probability, winner, wins_a, wins_b)`` for one distinct series path (the
    series stops the instant a team reaches :data:`WINS_NEEDED`, so games beyond
    the clinch are never played). Path probabilities sum to 1.
    """
    paths: list[tuple[float, str, int, int]] = []

    def recurse(game_index: int, wins_a: int, wins_b: int, prob: float) -> None:
        if wins_a == WINS_NEEDED:
            paths.append((prob, "A", wins_a, wins_b))
            return
        if wins_b == WINS_NEEDED:
            paths.append((prob, "B", wins_a, wins_b))
            return
        p = per_game[game_index]
        recurse(game_index + 1, wins_a + 1, wins_b, prob * p)
        recurse(game_index + 1, wins_a, wins_b + 1, prob * (1.0 - p))

    recurse(0, 0, 0, 1.0)
    return paths


def simulate_series(
    p_a_home: float,
    p_a_away: float,
    *,
    shutout_prob_a: float = 0.0,
    shutout_prob_b: float = 0.0,
) -> SeriesOutcome:
    """Exact best-of-7 outcome distribution from per-venue win probabilities.

    ``p_a_home`` / ``p_a_away`` are A's win probabilities at home / away; the
    venue schedule is the 2-2-1-1-1 :data:`HOME_ICE_PATTERN`. ``shutout_prob_*``
    are ``P(shutout | that team wins a game)`` (venue-independent, from the
    shutout model). The distribution is enumerated exactly over all series paths —
    deterministic, no seed. Probabilities are clamped to ``[0, 1]``.
    """
    p_home = min(max(float(p_a_home), 0.0), 1.0)
    p_away = min(max(float(p_a_away), 0.0), 1.0)
    per_game = game_win_probs(p_home, p_away)

    length_probs: dict[int, float] = dict.fromkeys(_SERIES_LENGTHS, 0.0)
    p_a = 0.0
    e_games = 0.0
    e_wins_a = 0.0
    e_wins_b = 0.0

    for prob, winner, wins_a, wins_b in _enumerate_paths(per_game):
        length = wins_a + wins_b
        length_probs[length] += prob
        e_games += prob * length
        e_wins_a += prob * wins_a
        e_wins_b += prob * wins_b
        if winner == "A":
            p_a += prob

    return SeriesOutcome(
        p_a_win_series=p_a,
        p_b_win_series=1.0 - p_a,
        length_probs=length_probs,
        e_games=e_games,
        e_wins_a=e_wins_a,
        e_wins_b=e_wins_b,
        e_goalie_points_a=expected_goalie_points(e_wins_a, shutout_prob_a),
        e_goalie_points_b=expected_goalie_points(e_wins_b, shutout_prob_b),
    )


def simulate_series_monte_carlo(
    p_a_home: float,
    p_a_away: float,
    *,
    shutout_prob_a: float = 0.0,
    shutout_prob_b: float = 0.0,
    n_sims: int = 20000,
    seed: int = 20260827,
) -> SeriesOutcome:
    """Seeded Monte-Carlo estimate of :func:`simulate_series` (cross-check only).

    Deterministic given ``seed``. :func:`simulate_series` is exact and preferred;
    this exists to validate the enumeration and to honor the "deterministic under a
    fixed seed" contract for any stochastic component (SPEC section 3).
    """
    rng = np.random.default_rng(seed)
    p_home = min(max(float(p_a_home), 0.0), 1.0)
    p_away = min(max(float(p_a_away), 0.0), 1.0)
    per_game = game_win_probs(p_home, p_away)

    length_counts: dict[int, int] = dict.fromkeys(_SERIES_LENGTHS, 0)
    a_series_wins = 0
    total_wins_a = 0
    total_wins_b = 0
    total_games = 0

    for _ in range(int(n_sims)):
        wins_a = 0
        wins_b = 0
        game_index = 0
        while wins_a < WINS_NEEDED and wins_b < WINS_NEEDED:
            if rng.random() < per_game[game_index]:
                wins_a += 1
            else:
                wins_b += 1
            game_index += 1
        length = wins_a + wins_b
        length_counts[length] += 1
        total_games += length
        total_wins_a += wins_a
        total_wins_b += wins_b
        if wins_a == WINS_NEEDED:
            a_series_wins += 1

    n = float(n_sims)
    p_a = a_series_wins / n
    e_wins_a = total_wins_a / n
    e_wins_b = total_wins_b / n
    return SeriesOutcome(
        p_a_win_series=p_a,
        p_b_win_series=1.0 - p_a,
        length_probs={length: length_counts[length] / n for length in _SERIES_LENGTHS},
        e_games=total_games / n,
        e_wins_a=e_wins_a,
        e_wins_b=e_wins_b,
        e_goalie_points_a=expected_goalie_points(e_wins_a, shutout_prob_a),
        e_goalie_points_b=expected_goalie_points(e_wins_b, shutout_prob_b),
    )


# ── Historical series reconstruction (leakage-free pre-series states) ───────


@dataclass
class _MatchupRecord:
    """Captured pre-series team snapshots + observed playoff shutouts for a matchup."""

    win_snapshots: dict[int, dict[str, float]] = field(default_factory=dict)
    shutout_snapshots: dict[int, dict[str, float]] = field(default_factory=dict)
    observed_shutouts: int = 0
    playoff_games: int = 0


def _pivot_all_games(team_games: pd.DataFrame) -> pd.DataFrame:
    """One row per archive-decided game, sorted chronologically.

    Shootouts retain tied goal totals because their deciding goal is absent from
    ``goals_for``. The archive's ``win`` column is therefore authoritative; rows
    without exactly one winner are excluded with a warning.
    """
    tg = team_games.copy()
    tg["game_date"] = pd.to_datetime(tg["game_date"])
    home = tg.loc[tg["home_road"] == "H"]
    away = tg.loc[tg["home_road"] == "R"]
    merged = home.merge(away, on="game_id", suffixes=("_home", "_away"))
    home_won = merged["win_home"].fillna(False).astype(bool)
    away_won = merged["win_away"].fillna(False).astype(bool)
    decided = home_won.ne(away_won)
    undecided_count = int((~decided).sum())
    if undecided_count:
        warnings.warn(
            f"_pivot_all_games excluded {undecided_count} games without exactly one "
            "archive winner",
            RuntimeWarning,
            stacklevel=2,
        )
    merged = merged.loc[decided].copy()
    home_won = home_won.loc[decided]
    games = pd.DataFrame(
        {
            "game_id": merged["game_id"],
            "season_id": merged["season_id_home"].astype(int),
            "season_end_year": (merged["season_id_home"] % 10000).astype(int),
            "game_type_id": merged["game_type_id_home"].astype(int),
            "game_date": merged["game_date_home"],
            "home_team_id": merged["team_id_home"].astype(int),
            "away_team_id": merged["team_id_away"].astype(int),
            "home_abbrev": merged["team_abbrev_home"],
            "away_abbrev": merged["team_abbrev_away"],
            "home_goals": merged["goals_for_home"].astype(int),
            "away_goals": merged["goals_for_away"].astype(int),
            "home_points": merged["points_home"].fillna(0).astype(int),
            "away_points": merged["points_away"].fillna(0).astype(int),
            "home_shots_against": merged["shots_against_home"].fillna(0).astype(int),
            "away_shots_against": merged["shots_against_away"].fillna(0).astype(int),
            "home_win": home_won.astype(int),
        }
    )
    return games.sort_values(["game_date", "game_id"], kind="stable").reset_index(drop=True)


def _matchup_key(year: int, team_a: int, team_b: int) -> tuple[int, int, int]:
    """Order-independent key for a season's matchup between two team ids."""
    lo, hi = sorted((int(team_a), int(team_b)))
    return (int(year), lo, hi)


@dataclass
class _MatchupPlan:
    """A real best-of-seven matchup's declared round cutoff and its two teams."""

    cutoff: pd.Timestamp
    year: int
    id_a: int
    id_b: int
    abbrev_a: str
    abbrev_b: str
    frozen: bool = False


def _matchup_cutoff_plan(team_games: pd.DataFrame, series: pd.DataFrame) -> list[_MatchupPlan]:
    """Every real series' pre-round freeze target: its declared round-start cutoff.

    Freezing a matchup's pre-series snapshot at the *round's* start (not the
    matchup's own first game) keeps a slower series from absorbing games played on
    or after the declared ``as_of_cutoff`` when rounds overlap (CODE_REVIEW m-3). A
    round with no games yet (a genuine pre-round build) freezes at the previous
    round's completion boundary instead of its own first game (CODE_REVIEW M-1).
    """
    round_map = _series_round_map(series)
    round_starts = playoff_round_cutoffs(team_games, series)

    abbrev_to_id: dict[tuple[int, str], int] = {}
    tg = team_games[["season_id", "team_abbrev", "team_id"]]
    for rec in tg.drop_duplicates().to_dict("records"):
        abbrev_to_id[(int(rec["season_id"]), str(rec["team_abbrev"]))] = int(rec["team_id"])

    plans: list[_MatchupPlan] = []
    for (season_id, pair), rnd in round_map.items():
        cutoff_str = round_starts.get(season_id, {}).get(rnd)
        if cutoff_str is None:
            continue
        id_a = abbrev_to_id.get((season_id, pair[0]))
        id_b = abbrev_to_id.get((season_id, pair[1]))
        if id_a is None or id_b is None:
            continue
        plans.append(
            _MatchupPlan(
                cutoff=pd.Timestamp(cutoff_str),
                year=season_id % 10000,
                id_a=id_a,
                id_b=id_b,
                abbrev_a=pair[0],
                abbrev_b=pair[1],
            )
        )
    plans.sort(key=lambda p: p.cutoff)
    return plans


def _freeze_due_matchups(
    plans: list[_MatchupPlan],
    records: dict[tuple[int, int, int], _MatchupRecord],
    win_states: dict[str, TeamState],
    sho_states: dict[str, ShutoutTeamState],
    as_of: pd.Timestamp,
    *,
    initial_elo: float,
) -> None:
    """Freeze pre-series snapshots for every planned matchup whose cutoff has arrived."""
    for plan in plans:
        if plan.frozen or plan.cutoff > as_of:
            continue
        a_win = win_states.setdefault(plan.abbrev_a, TeamState(elo=initial_elo))
        b_win = win_states.setdefault(plan.abbrev_b, TeamState(elo=initial_elo))
        a_sho = sho_states.setdefault(plan.abbrev_a, ShutoutTeamState())
        b_sho = sho_states.setdefault(plan.abbrev_b, ShutoutTeamState())
        key = _matchup_key(plan.year, plan.id_a, plan.id_b)
        matchup = records.get(key)
        if matchup is None:
            matchup = _MatchupRecord()
            records[key] = matchup
        matchup.win_snapshots[plan.id_a] = a_win.snapshot()
        matchup.win_snapshots[plan.id_b] = b_win.snapshot()
        matchup.shutout_snapshots[plan.id_a] = a_sho.snapshot()
        matchup.shutout_snapshots[plan.id_b] = b_sho.snapshot()
        plan.frozen = True


def reconstruct_series_matchups(
    team_games: pd.DataFrame,
    *,
    series: pd.DataFrame | None = None,
    elo_config: EloConfig | None = None,
) -> dict[tuple[int, int, int], _MatchupRecord]:
    """Replay all games once, capturing pre-series states + observed shutouts.

    A single chronological pass maintains, per team, the win model's
    :class:`~draft_oracle.models.game_win.TeamState` (Elo + offensive proxies) and
    the shutout model's :class:`~draft_oracle.models.shutout.ShutoutTeamState`
    (goaltending proxies), using the exact same update rules as those models so the
    features line up.

    When ``series`` is supplied each matchup's pre-series snapshot is frozen at its
    **round's declared start cutoff** (the earliest game of that round), so a series
    that starts later than its round cannot absorb games played on or after that
    cutoff (CODE_REVIEW m-3). Without ``series`` the legacy per-series freeze (at the
    matchup's own first game) is used. In both modes the 2019-20 bubble qualifying
    round and round-robin games (``game_id`` round digit ``0``) never form or count
    toward a matchup (CODE_REVIEW m-6); they still feed Elo like any played game.
    Snapshots read only games strictly before the freeze point, so there is no
    leakage (SPEC section 6).
    """
    elo_config = elo_config or EloConfig()
    games = _pivot_all_games(team_games)

    win_states: dict[str, TeamState] = {}
    sho_states: dict[str, ShutoutTeamState] = {}
    records: dict[tuple[int, int, int], _MatchupRecord] = {}
    last_season: int | None = None

    plans = _matchup_cutoff_plan(team_games, series) if series is not None else None

    for record in games.to_dict("records"):
        season = int(record["season_id"])
        if last_season is not None and season != last_season:
            for win_state in win_states.values():
                win_state.elo = regress_to_mean(
                    win_state.elo, elo_config.initial, elo_config.season_regression
                )
                win_state.reg_games = 0
                win_state.reg_points = 0
                win_state.reg_goals_for = 0
                win_state.reg_goals_against = 0
                win_state.reg_wins = 0
            for sho_state in sho_states.values():
                sho_state.reset_season()
        last_season = season

        home_abbrev = str(record["home_abbrev"])
        away_abbrev = str(record["away_abbrev"])
        home_win = win_states.setdefault(home_abbrev, TeamState(elo=elo_config.initial))
        away_win = win_states.setdefault(away_abbrev, TeamState(elo=elo_config.initial))
        home_sho = sho_states.setdefault(home_abbrev, ShutoutTeamState())
        away_sho = sho_states.setdefault(away_abbrev, ShutoutTeamState())

        if plans is not None:
            _freeze_due_matchups(
                plans,
                records,
                win_states,
                sho_states,
                pd.Timestamp(record["game_date"]),
                initial_elo=elo_config.initial,
            )

        home_goals = int(record["home_goals"])
        away_goals = int(record["away_goals"])
        home_won = bool(record["home_win"])

        is_qualifying = _playoff_round_digit(record["game_id"]) == QUALIFYING_ROUND_GAME_DIGIT
        if int(record["game_type_id"]) == PLAYOFF_GAME_TYPE and not is_qualifying:
            year = int(record["season_end_year"])
            home_id = int(record["home_team_id"])
            away_id = int(record["away_team_id"])
            key = _matchup_key(year, home_id, away_id)
            matchup = records.get(key)
            if matchup is None and plans is None:
                matchup = _MatchupRecord()
                matchup.win_snapshots[home_id] = home_win.snapshot()
                matchup.win_snapshots[away_id] = away_win.snapshot()
                matchup.shutout_snapshots[home_id] = home_sho.snapshot()
                matchup.shutout_snapshots[away_id] = away_sho.snapshot()
                records[key] = matchup
            if matchup is not None:
                matchup.playoff_games += 1
                if (home_won and away_goals == 0) or (not home_won and home_goals == 0):
                    matchup.observed_shutouts += 1

        # Elo update (all games), then regular-season-only counters + goalie state.
        exp_home = expected_score(home_win.elo, away_win.elo, elo_config.home_advantage)
        actual_home = 1.0 if home_won else 0.0
        home_win.elo = update_rating(home_win.elo, exp_home, actual_home, elo_config.k)
        away_win.elo = update_rating(away_win.elo, 1.0 - exp_home, 1.0 - actual_home, elo_config.k)
        if int(record["game_type_id"]) == REGULAR_SEASON_GAME_TYPE:
            home_win.record_regular_season(
                points=int(record["home_points"]),
                goals_for=home_goals,
                goals_against=away_goals,
                won=home_won,
            )
            away_win.record_regular_season(
                points=int(record["away_points"]),
                goals_for=away_goals,
                goals_against=home_goals,
                won=not home_won,
            )
            home_sho.record_regular_season(
                goals_for=home_goals,
                goals_against=away_goals,
                shots_against=int(record["home_shots_against"]),
                won=home_won,
            )
            away_sho.record_regular_season(
                goals_for=away_goals,
                goals_against=home_goals,
                shots_against=int(record["away_shots_against"]),
                won=not home_won,
            )

    if plans is not None:
        # Freeze any matchup whose declared cutoff is after every played game -- a
        # genuine pre-round build (round N has no games yet) freezes at the state
        # reached after the previous round, the correct pre-round-N snapshot
        # (CODE_REVIEW M-1). In backtests over complete seasons no such matchup
        # exists, so this pass is a no-op.
        _freeze_due_matchups(
            plans,
            records,
            win_states,
            sho_states,
            pd.Timestamp.max,
            initial_elo=elo_config.initial,
        )

    return records


# ── Calibration on held-out seasons ─────────────────────────────────────────


@dataclass(frozen=True)
class SeriesCalibrationBin:
    """One predicted-P(higher-seed-wins) bucket: predicted vs. observed frequency."""

    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float


@dataclass(frozen=True)
class LengthBin:
    """Predicted vs. observed frequency for one series length (4/5/6/7)."""

    length: int
    predicted_rate: float
    observed_rate: float


def _series_calibration_bins(
    probs: np.ndarray, labels: np.ndarray, *, n_bins: int
) -> list[SeriesCalibrationBin]:
    """Equal-width predicted-probability bins over ``[0, 1]``."""
    if probs.size == 0:
        return []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[SeriesCalibrationBin] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        upper_inclusive = i == n_bins - 1
        mask = (probs >= lo) & (probs <= hi if upper_inclusive else probs < hi)
        count = int(mask.sum())
        if count == 0:
            continue
        bins.append(
            SeriesCalibrationBin(
                lower=lo,
                upper=hi,
                count=count,
                mean_predicted=float(probs[mask].mean()),
                observed_rate=float(labels[mask].mean()),
            )
        )
    return bins


@dataclass(frozen=True)
class SeriesSimConfig:
    """Evaluation knobs; every stochastic step is seeded (SPEC section 3)."""

    seed: int = 20260827
    n_test_seasons: int = 2
    calibration_bins: int = 5


@dataclass
class SeriesSimResult:
    """Outcome of the series-simulator calibration on held-out seasons."""

    config: SeriesSimConfig
    test_years: tuple[int, ...]
    n_series_scored: int
    n_series_skipped: int
    brier_series: float
    brier_higher_seed: float
    brier_coin_flip: float
    calibration_bins: list[SeriesCalibrationBin]
    length_bins: list[LengthBin]
    predicted_shutouts_by_round: dict[int, float]
    observed_shutouts_by_round: dict[int, int]

    @property
    def beats_higher_seed_baseline(self) -> bool:
        return self.brier_series < self.brier_higher_seed

    @property
    def beats_coin_flip(self) -> bool:
        return self.brier_series < self.brier_coin_flip

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable run summary (seed, split, metrics)."""
        return {
            "model_version": SERIES_SIM_VERSION,
            "seed": self.config.seed,
            "test_years": list(self.test_years),
            "counts": {
                "series_scored": self.n_series_scored,
                "series_skipped": self.n_series_skipped,
            },
            "brier": {
                "series_model": self.brier_series,
                "higher_seed_baseline": self.brier_higher_seed,
                "coin_flip_baseline": self.brier_coin_flip,
            },
            "beats_higher_seed_baseline": self.beats_higher_seed_baseline,
            "beats_coin_flip": self.beats_coin_flip,
            "series_winner_reliability": [
                {
                    "lower": b.lower,
                    "upper": b.upper,
                    "count": b.count,
                    "mean_predicted": b.mean_predicted,
                    "observed_rate": b.observed_rate,
                }
                for b in self.calibration_bins
            ],
            "series_length_distribution": [
                {
                    "length": b.length,
                    "predicted_rate": b.predicted_rate,
                    "observed_rate": b.observed_rate,
                }
                for b in self.length_bins
            ],
            "shutouts_by_round": {
                str(rnd): {
                    "predicted": self.predicted_shutouts_by_round.get(rnd, 0.0),
                    "observed": self.observed_shutouts_by_round.get(rnd, 0),
                }
                for rnd in sorted(
                    set(self.predicted_shutouts_by_round) | set(self.observed_shutouts_by_round)
                )
            },
        }

    def report_lines(self) -> list[str]:
        """Human-readable calibration report (Markdown; ASCII only)."""
        cfg = self.config
        lines = [
            f"# Best-of-7 series simulator ({SERIES_SIM_VERSION})",
            "",
            "Composes the per-game win model (US-011) and shutout model (US-012) into a",
            "full best-of-7 outcome distribution with the 2-2-1-1-1 home-ice pattern. The",
            "distribution is enumerated exactly over all series paths (no Monte Carlo). Per",
            "series it yields P(win series), the 4/5/6/7-game length distribution, E[wins],",
            "E[games], and E[goalie-slot points] scored through the rules engine (a shutout",
            "win replaces a normal win: 4 pts vs 2).",
            "",
            "## Reproducibility",
            f"- Seed: {cfg.seed}",
            f"- Held-out test seasons (end year): {list(self.test_years)}",
            "- The per-game win and shutout models are trained ONLY on seasons before the",
            "  held-out set; test-season series never touch training (SPEC section 6).",
            f"- Series scored: {self.n_series_scored} (skipped for missing pre-series "
            f"state: {self.n_series_skipped}).",
            "",
            "## Series-winner calibration (held out)",
            "Brier score for P(higher seed wins the series), lower is better:",
            f"- series simulator:        {self.brier_series:.4f}",
            f"- baseline higher seed=1:  {self.brier_higher_seed:.4f}",
            f"- baseline coin flip=0.5:  {self.brier_coin_flip:.4f}",
            f"- Beats higher-seed baseline: {'yes' if self.beats_higher_seed_baseline else 'NO'}",
            f"- Beats coin flip: {'yes' if self.beats_coin_flip else 'NO'}",
            "",
            "### Reliability bins (predicted P(higher seed wins) -> observed)",
            "| predicted range | n | mean predicted | observed |",
            "| --- | --- | --- | --- |",
        ]
        for b in self.calibration_bins:
            lines.append(
                f"| {b.lower:.2f}-{b.upper:.2f} | {b.count} | "
                f"{b.mean_predicted:.3f} | {b.observed_rate:.3f} |"
            )
        lines += [
            "",
            "## Series-length distribution: predicted vs. observed",
            "| games | predicted | observed |",
            "| --- | --- | --- |",
        ]
        for lb in self.length_bins:
            lines.append(f"| {lb.length} | {lb.predicted_rate:.3f} | {lb.observed_rate:.3f} |")
        lines += [
            "",
            "## Shutouts per playoff round: predicted E[shutouts] vs. observed",
            "| round | predicted | observed |",
            "| --- | --- | --- |",
        ]
        for rnd in sorted(
            set(self.predicted_shutouts_by_round) | set(self.observed_shutouts_by_round)
        ):
            predicted = self.predicted_shutouts_by_round.get(rnd, 0.0)
            observed = self.observed_shutouts_by_round.get(rnd, 0)
            lines.append(f"| {rnd} | {predicted:.2f} | {observed} |")
        lines += [
            "",
            "## Honesty note (SPEC section 7)",
            "Metrics are reported exactly as measured. With ~40 playoff series held out the",
            "sample is small, so the series-winner Brier is noisy and may not beat the",
            "higher-seed baseline every split; the number is printed as-is. Series prices",
            "are unavailable, so per-game probabilities come from the stat-only win model.",
            "",
        ]
        return lines


def _held_out_years(series: pd.DataFrame, n_test: int) -> tuple[int, ...]:
    years = sorted({int(y) for y in series["year"].dropna().unique()})
    return tuple(years[-n_test:]) if n_test > 0 else ()


def _predict_series(
    win_model: GameWinModel,
    shutout_model: ShutoutModel,
    matchup: _MatchupRecord,
    top_id: int,
    bottom_id: int,
) -> tuple[SeriesOutcome, float, float]:
    """Run the simulator for one matchup; return outcome + per-team shutout probs."""
    top_win = matchup.win_snapshots[top_id]
    bottom_win = matchup.win_snapshots[bottom_id]
    top_sho = matchup.shutout_snapshots[top_id]
    bottom_sho = matchup.shutout_snapshots[bottom_id]

    # Top seed holds home ice. p_top_home from the top-home matchup; p_top_away is
    # 1 - P(bottom wins when bottom hosts).
    p_top_home = win_model.predict_matchup(top_win, bottom_win, is_playoff=True)
    p_top_away = 1.0 - win_model.predict_matchup(bottom_win, top_win, is_playoff=True)

    shutout_top = shutout_model.predict_matchup(top_sho, bottom_sho)
    shutout_bottom = shutout_model.predict_matchup(bottom_sho, top_sho)

    outcome = simulate_series(
        p_top_home,
        p_top_away,
        shutout_prob_a=shutout_top,
        shutout_prob_b=shutout_bottom,
    )
    return outcome, shutout_top, shutout_bottom


def evaluate_series_sim(
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    *,
    config: SeriesSimConfig | None = None,
) -> SeriesSimResult:
    """Train the per-game models off-test and calibrate the series simulator.

    Steps: pick the held-out test seasons (newest ``n_test_seasons``); fit the
    win and shutout models on the remaining seasons only; replay every game once to
    freeze leakage-free pre-series team states + observed playoff shutouts; run each
    held-out series through :func:`simulate_series`; and score the predictions
    against the actual winner, length, and shutout counts. Every number in the
    returned :class:`SeriesSimResult` is what the report and manifest print.
    """
    config = config or SeriesSimConfig()
    test_years = _held_out_years(series, config.n_test_seasons)
    test_year_set = set(test_years)

    train_games = team_games.loc[~((team_games["season_id"] % 10000).isin(test_year_set))].copy()
    if train_games.empty:
        raise ValueError("no training seasons remain after holding out the test set")

    win_result = train_game_win_model(
        train_games, odds=None, config=GameWinConfig(seed=config.seed)
    )
    shutout_result = train_shutout_model(train_games, config=ShutoutConfig(seed=config.seed))
    win_model = win_result.model
    shutout_model = shutout_result.model

    matchups = reconstruct_series_matchups(team_games)

    predicted_probs: list[float] = []
    actual_top_wins: list[float] = []
    predicted_length: dict[int, float] = dict.fromkeys(_SERIES_LENGTHS, 0.0)
    observed_length: dict[int, int] = dict.fromkeys(_SERIES_LENGTHS, 0)
    predicted_shutouts: dict[int, float] = {}
    observed_shutouts: dict[int, int] = {}
    n_scored = 0
    n_skipped = 0

    held_out = series.loc[series["year"].isin(test_year_set)]
    for row in held_out.to_dict("records"):
        top_id = row["top_seed_team_id"]
        bottom_id = row["bottom_seed_team_id"]
        winner_id = row["winning_team_id"]
        if pd.isna(top_id) or pd.isna(bottom_id) or pd.isna(winner_id):
            n_skipped += 1
            continue
        top_id = int(top_id)
        bottom_id = int(bottom_id)
        key = _matchup_key(int(row["year"]), top_id, bottom_id)
        matchup = matchups.get(key)
        if (
            matchup is None
            or top_id not in matchup.win_snapshots
            or bottom_id not in matchup.win_snapshots
        ):
            n_skipped += 1
            continue

        outcome, shutout_top, shutout_bottom = _predict_series(
            win_model, shutout_model, matchup, top_id, bottom_id
        )

        top_won = 1.0 if int(winner_id) == top_id else 0.0
        predicted_probs.append(outcome.p_a_win_series)
        actual_top_wins.append(top_won)

        actual_len = int(row["top_seed_wins"]) + int(row["bottom_seed_wins"])
        if actual_len in observed_length:
            observed_length[actual_len] += 1
        for length, prob in outcome.length_probs.items():
            predicted_length[length] += prob

        rnd = int(row["playoff_round"]) if not pd.isna(row["playoff_round"]) else 0
        predicted_shutouts[rnd] = predicted_shutouts.get(rnd, 0.0) + (
            outcome.e_wins_a * shutout_top + outcome.e_wins_b * shutout_bottom
        )
        observed_shutouts[rnd] = observed_shutouts.get(rnd, 0) + matchup.observed_shutouts
        n_scored += 1

    probs_arr = np.asarray(predicted_probs, dtype=float)
    labels_arr = np.asarray(actual_top_wins, dtype=float)
    brier_series = brier_score(probs_arr, labels_arr) if n_scored else float("nan")
    brier_higher = brier_score(np.ones_like(labels_arr), labels_arr) if n_scored else float("nan")
    brier_coin = (
        brier_score(np.full_like(labels_arr, 0.5), labels_arr) if n_scored else float("nan")
    )

    total_pred_len = sum(predicted_length.values())
    total_obs_len = sum(observed_length.values())
    length_bins = [
        LengthBin(
            length=length,
            predicted_rate=(predicted_length[length] / total_pred_len)
            if total_pred_len > 0
            else 0.0,
            observed_rate=(observed_length[length] / total_obs_len) if total_obs_len > 0 else 0.0,
        )
        for length in _SERIES_LENGTHS
    ]

    return SeriesSimResult(
        config=config,
        test_years=test_years,
        n_series_scored=n_scored,
        n_series_skipped=n_skipped,
        brier_series=brier_series,
        brier_higher_seed=brier_higher,
        brier_coin_flip=brier_coin,
        calibration_bins=_series_calibration_bins(
            probs_arr, labels_arr, n_bins=config.calibration_bins
        ),
        length_bins=length_bins,
        predicted_shutouts_by_round=predicted_shutouts,
        observed_shutouts_by_round=observed_shutouts,
    )


DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_MODEL_ARTIFACT_DIR = Path("artifacts/models/series-sim")


def evaluate_series_sim_from_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Path = DEFAULT_MODEL_ARTIFACT_DIR,
    config: SeriesSimConfig | None = None,
) -> SeriesSimResult:
    """Load ``team_games`` + ``series``, calibrate, and write report + manifest.

    Runs :func:`evaluate_series_sim` and commits the Markdown report and JSON
    manifest under ``artifact_dir`` (both re-included in .gitignore, like the
    per-game win and shutout models).
    """
    import json

    team_games = pd.read_parquet(normalized_dir / "team_games.parquet")
    series = pd.read_parquet(normalized_dir / "series.parquet")
    result = evaluate_series_sim(team_games, series, config=config)
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result


# Alias kept for CLI/story naming symmetry with the other models.
train_series_sim_from_normalized = evaluate_series_sim_from_normalized
