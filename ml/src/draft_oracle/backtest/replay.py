"""Backtest replay engine (US-025).

Replays historical playoff rounds end-to-end so the oracle's edge is *measured*,
not assumed:

1. **As-of projections** — for every playoff round of a backtested season the
   US-017 projection artifact is rebuilt using only games played strictly before
   the round started (:func:`draft_oracle.projection_artifact.build_projection_artifact`
   enforces the cutoff; this harness re-asserts it with an independent guard).
2. **Simulated drafts** — the oracle is seated in *every* snake slot in turn and
   drafts against the opponents. Where the league's draft history covers the
   season the fitted US-020 opponent model drives the opponents (trained
   leave-one-season-out so the backtested season never leaks into its own
   opponents); otherwise the greedy fallback is used.
3. **Actual scoring** — every drafted roster is scored with the *actual*
   historical round results through :mod:`draft_oracle.rules` (skater goals +
   assists; the goalie slot via ``goalie_series_points`` over the team's real
   series). Projections drive the *decisions*; actuals only ever drive the
   *score*, never a pick.

A hard leakage guard (:func:`assert_round_inputs_leakfree`) fails the backtest
loudly if any round-``N`` game leaks into the as-of inputs for round ``N``. Runs
are seeded and reproducible: ``(snapshot, seed)`` fully determines every roster
and score. Per-round intermediate results are persisted under
``artifacts/backtests/<run-id>/rounds/`` so reporting (US-026) can run separately.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from draft_oracle import __version__
from draft_oracle.features.leakage import LeakageError, assert_no_leakage
from draft_oracle.models.series_sim import simulate_series
from draft_oracle.models.skater_production import (
    PLAYOFF_GAME_TYPE,
    _assign_rounds,
    _series_round_map,
    skater_round_production,
)
from draft_oracle.optimize.opponents import (
    FittedLeagueOpponents,
    OpponentFitConfig,
    fit_opponent_models,
)
from draft_oracle.optimize.recommend import (
    RecommendConfig,
    build_pool_from_frames,
    choose_pick,
    greedy_vor_pick,
    replacement_levels,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
    _resolve_model,
    roster_capacity,
)
from draft_oracle.projection_artifact import (
    DEFAULT_NORMALIZED_DIR,
    SNAPSHOTS_SUBDIR,
    ProjectArtifactConfig,
    _load_injuries,
    _load_league_picks,
    _load_tables,
    _snapshot_id_for,
    build_projection_artifact,
)
from draft_oracle.rules import goalie_series_points, player_points

__all__ = [
    "DEFAULT_BACKTEST_ROOT",
    "STRATEGIES",
    "BacktestConfig",
    "BacktestResult",
    "LeagueComparison",
    "LeagueManagerRoster",
    "ProjectionEval",
    "RoundResult",
    "SeriesEval",
    "SlotResult",
    "Strategy",
    "assert_round_inputs_leakfree",
    "round_game_ids",
    "run_backtest",
    "run_backtest_from_normalized",
    "skater_actual_points",
    "team_actual_goalie_points",
]

# Playoff round -> the league's redraft event covering it (rounds 3+4 share R3_4).
ROUND_TO_DRAFT_EVENT: dict[int, str] = {1: "R1", 2: "R2", 3: "R3_4", 4: "R3_4"}

DEFAULT_BACKTEST_ROOT = Path("artifacts/backtests")

Strategy = Literal["oracle", "greedy_vor", "one_step", "random_legal"]
STRATEGIES: tuple[Strategy, ...] = ("oracle", "greedy_vor", "one_step", "random_legal")


# ── Configuration ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BacktestConfig:
    """Knobs for a reproducible backtest run (all deterministic given the inputs).

    ``strategies`` is the set of oracle policies seated in each slot; ``"oracle"``
    is the multi-step rollout, the others are the US-026 baselines. ``n_drafts`` is
    the number of seeded drafts per (round, slot) — opponent stochasticity is
    averaged over them. ``managers`` sizes the league; ``ir`` toggles IR slots.
    """

    seed: int = 20260827
    managers: int = 4
    ir: bool = False
    n_drafts: int = 1
    rollouts: int = 40
    max_candidates: int = 6
    opponent_temperature: float = 0.75
    depth: int | None = None
    strategies: tuple[Strategy, ...] = ("oracle",)
    project_config: ProjectArtifactConfig | None = None
    run_id: str = ""

    def __post_init__(self) -> None:
        if self.managers < 2:
            raise ValueError(f"managers must be >= 2, got {self.managers}")
        if self.n_drafts < 1:
            raise ValueError(f"n_drafts must be >= 1, got {self.n_drafts}")
        if not self.strategies:
            raise ValueError("strategies must be non-empty")
        for strategy in self.strategies:
            if strategy not in STRATEGIES:
                raise ValueError(f"unknown strategy {strategy!r}; choose from {STRATEGIES}")

    def recommend_config(self) -> RecommendConfig:
        """The rollout config the multi-step / one-step oracle policies use."""
        return RecommendConfig(
            rollouts=self.rollouts,
            depth=self.depth,
            max_candidates=self.max_candidates,
            compute_survival=False,
            seed=self.seed,
        )

    def artifact_config(self) -> ProjectArtifactConfig:
        """The projection-artifact config (seeded sub-models), slot report disabled."""
        if self.project_config is not None:
            return self.project_config
        return ProjectArtifactConfig(seed=self.seed, managers=self.managers, ir=self.ir)

    def resolved_run_id(self, seasons: list[int]) -> str:
        """Deterministic run id from the seasons + seed unless one is pinned."""
        if self.run_id:
            return self.run_id
        seasons_part = "-".join(str(s) for s in sorted(seasons))
        return f"{seasons_part}-seed{self.seed}"


# ── Actual-result scoring lookups (through the rules engine) ────────────────


def skater_actual_points(
    skater_games: pd.DataFrame, series: pd.DataFrame
) -> dict[tuple[int, int, int], int]:
    """``(season_id, playoff_round, player_id) -> actual round points`` (G + A).

    Scored through :func:`draft_oracle.rules.player_points`, so every backtested
    skater is scored byte-identically to the real app. Uses only that round's
    observed playoff games.
    """
    production = skater_round_production(skater_games, series)
    out: dict[tuple[int, int, int], int] = {}
    for rec in production.to_dict("records"):
        key = (int(rec["season_id"]), int(rec["playoff_round"]), int(rec["player_id"]))
        out[key] = player_points(int(rec["round_goals"]), int(rec["round_assists"]))
    return out


def team_actual_goalie_points(
    team_games: pd.DataFrame, series: pd.DataFrame
) -> dict[tuple[int, int, int], int]:
    """``(season_id, playoff_round, team_id) -> actual goalie-slot points``.

    A team's goalie slot scores its real series through
    :func:`draft_oracle.rules.goalie_series_points`: wins and shutout wins are
    aggregated over the round's games, so a shutout upgrades a win from 2 to 4 (the
    goalie slot is never scored by fantasy points directly — SPEC section 8).
    """
    po = team_games.loc[team_games["game_type_id"] == PLAYOFF_GAME_TYPE].copy()
    if po.empty:
        return {}
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.dropna(subset=["playoff_round"])
    grouped = po.groupby(["season_id", "playoff_round", "team_id"], as_index=False).agg(
        wins=("win", "sum"),
        shutout_wins=("shutout_win", "sum"),
    )
    out: dict[tuple[int, int, int], int] = {}
    for rec in grouped.to_dict("records"):
        key = (int(rec["season_id"]), int(rec["playoff_round"]), int(rec["team_id"]))
        out[key] = goalie_series_points(int(rec["wins"]), int(rec["shutout_wins"]))
    return out


def _score_active_roster(
    state: DraftState,
    manager: str,
    skater_actual: dict[tuple[int, int, int], int],
    team_actual: dict[tuple[int, int, int], int],
    *,
    season_id: int,
    playoff_round: int,
) -> float:
    """Actual points of ``manager``'s *active* roster (F/D/G; IR slots excluded).

    IR retroactive swaps depend on in-round injuries the replay does not simulate, so
    the honest baseline scores the active roster only; a skater or team with no
    observed round production contributes 0.
    """
    total = 0.0
    for slot in state.roster_slots(manager):
        if slot.position in ("IR_F", "IR_D"):
            continue
        if slot.player_id is not None:
            total += skater_actual.get((season_id, playoff_round, slot.player_id), 0)
        elif slot.team_id is not None:
            total += team_actual.get((season_id, playoff_round, slot.team_id), 0)
    return total


# ── Leakage guard (SPEC section 6) ──────────────────────────────────────────


def round_game_ids(
    team_games: pd.DataFrame, series: pd.DataFrame, *, season_id: int, playoff_round: int
) -> set[int]:
    """The ``game_id`` set of ``season_id``'s round ``playoff_round`` playoff games."""
    po = team_games.loc[
        (team_games["game_type_id"] == PLAYOFF_GAME_TYPE)
        & (team_games["season_id"].astype(int) == int(season_id))
    ].copy()
    if po.empty:
        return set()
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.loc[po["playoff_round"] == playoff_round]
    return {int(gid) for gid in po["game_id"].unique()}


def assert_round_inputs_leakfree(
    games: pd.DataFrame,
    round_ids: set[int],
    cutoff: str | pd.Timestamp,
    *,
    date_col: str = "game_date",
    label: str = "games",
) -> None:
    """Fail loudly if the as-of inputs for a round contain that round's data.

    Two independent checks on the as-of training slice (``date < cutoff``):

    * no game is dated on/after the round-start ``cutoff`` (delegated to
      :func:`draft_oracle.features.leakage.assert_no_leakage`); and
    * none of the round's own ``game_id`` values appear in the slice — a direct
      identity check that does not rely on date arithmetic.

    Either violation raises :class:`~draft_oracle.features.leakage.LeakageError`,
    which the backtest turns into a hard failure.
    """
    cutoff_ts = pd.Timestamp(cutoff)
    frame = games.copy()
    frame[date_col] = pd.to_datetime(frame[date_col])
    train = frame.loc[frame[date_col] < cutoff_ts]
    assert_no_leakage(train, cutoff_ts, date_col=date_col)
    if "game_id" in train.columns and round_ids:
        leaked = {int(gid) for gid in train["game_id"].unique()} & round_ids
        if leaked:
            raise LeakageError(
                f"{len(leaked)} round game(s) leaked into the as-of {label} inputs "
                f"before cutoff {cutoff_ts.date()} (e.g. game_id {sorted(leaked)[:3]})."
            )


# ── Result records ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SeriesEval:
    """One backtested series: the model's win probability vs. the actual winner.

    ``p_top_stat`` is the stat-only series-model probability the top seed wins its
    round (the number the projection artifact actually drafted from). ``p_top_market``
    is a market-aware probability derived from de-vigged per-game betting odds for the
    same series, or ``None`` where no historical odds cover it. Both are scored against
    ``top_won`` (1 if the top seed won the series) via the Brier score in reporting.
    """

    top_id: int
    bottom_id: int
    top_seed_abbrev: str
    bottom_seed_abbrev: str
    top_won: int
    p_top_stat: float
    p_top_market: float | None

    def manifest(self) -> dict[str, Any]:
        return {
            "top_id": self.top_id,
            "bottom_id": self.bottom_id,
            "top": self.top_seed_abbrev,
            "bottom": self.bottom_seed_abbrev,
            "top_won": self.top_won,
            "p_top_stat": round(self.p_top_stat, 6),
            "p_top_market": None if self.p_top_market is None else round(self.p_top_market, 6),
        }


@dataclass(frozen=True)
class ProjectionEval:
    """As-of projections paired with the realized outcome for one round.

    ``skaters`` is ``(player_id, projected_points, actual_points)`` for every eligible
    skater; ``teams`` is ``(team_id, projected_goalie_points, actual_goalie_points)``
    for every eligible team. Reporting turns these into projection MAE and rank
    correlation per season and in aggregate — actuals only ever score, never a pick.
    """

    skaters: list[tuple[int, float, float]] = field(default_factory=list)
    teams: list[tuple[int, float, float]] = field(default_factory=list)

    def manifest(self) -> dict[str, Any]:
        return {
            "skaters": [[pid, round(p, 6), round(a, 6)] for pid, p, a in self.skaters],
            "teams": [[tid, round(p, 6), round(a, 6)] for tid, p, a in self.teams],
        }


@dataclass(frozen=True)
class SlotResult:
    """One seeded draft of one strategy seated at one snake slot."""

    strategy: str
    seat: int
    oracle_manager: str
    draft_index: int
    oracle_points: float
    opponent_points: dict[str, float]
    roster_keys: list[str]

    @property
    def is_win(self) -> bool:
        """Whether the oracle roster strictly outscored every opponent this draft."""
        if not self.opponent_points:
            return False
        return self.oracle_points > max(self.opponent_points.values())

    def manifest(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "seat": self.seat,
            "oracle_manager": self.oracle_manager,
            "draft_index": self.draft_index,
            "oracle_points": round(self.oracle_points, 6),
            "opponent_points": {k: round(v, 6) for k, v in self.opponent_points.items()},
            "roster_keys": self.roster_keys,
        }


@dataclass(frozen=True)
class RoundResult:
    """Replay of one playoff round: as-of cutoff, opponents, and per-slot scores."""

    season: int
    season_id: int
    playoff_round: int
    as_of_cutoff: str
    opponents_kind: str
    eligible_team_abbrevs: list[str]
    leakage_ok: bool
    slot_results: list[SlotResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    projection_eval: ProjectionEval | None = None
    series_evals: list[SeriesEval] = field(default_factory=list)

    def manifest(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "season_id": self.season_id,
            "playoff_round": self.playoff_round,
            "as_of_cutoff": self.as_of_cutoff,
            "opponents_kind": self.opponents_kind,
            "eligible_team_abbrevs": self.eligible_team_abbrevs,
            "leakage_ok": self.leakage_ok,
            "slot_results": [s.manifest() for s in self.slot_results],
            "warnings": self.warnings,
            "projection_eval": (
                self.projection_eval.manifest() if self.projection_eval is not None else None
            ),
            "series_evals": [s.manifest() for s in self.series_evals],
        }


@dataclass(frozen=True)
class LeagueManagerRoster:
    """A real league manager's actual active-roster points for a backtested round."""

    manager: str
    actual_points: float

    def manifest(self) -> dict[str, Any]:
        return {"manager": self.manager, "actual_points": round(self.actual_points, 6)}


@dataclass(frozen=True)
class LeagueComparison:
    """Oracle simulated rosters vs. what the league's managers actually drafted.

    Populated only where a backtested season/round overlaps the committed league draft
    history. ``oracle_mean_points`` / ``oracle_best_points`` aggregate the oracle policy
    across the snake slots for the round; ``managers`` are the league's real active-
    roster scores through the same rules engine.
    """

    season: int
    playoff_round: int
    draft_event: str
    managers: list[LeagueManagerRoster]
    oracle_mean_points: float
    oracle_best_points: float

    @property
    def league_mean_points(self) -> float:
        if not self.managers:
            return float("nan")
        return sum(m.actual_points for m in self.managers) / len(self.managers)

    @property
    def league_best_points(self) -> float:
        if not self.managers:
            return float("nan")
        return max(m.actual_points for m in self.managers)

    def manifest(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "playoff_round": self.playoff_round,
            "draft_event": self.draft_event,
            "oracle_mean_points": round(self.oracle_mean_points, 6),
            "oracle_best_points": round(self.oracle_best_points, 6),
            "league_mean_points": round(self.league_mean_points, 6),
            "league_best_points": round(self.league_best_points, 6),
            "managers": [m.manifest() for m in self.managers],
        }


@dataclass(frozen=True)
class BacktestResult:
    """A full backtest run: config, per-round replays, and a written manifest."""

    run_id: str
    seasons: list[int]
    config: BacktestConfig
    rounds: list[RoundResult]
    generated_at: str
    league_comparisons: list[LeagueComparison] = field(default_factory=list)

    def manifest(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "package_version": __version__,
            "seasons": self.seasons,
            "generated_at": self.generated_at,
            "config": {
                "seed": self.config.seed,
                "managers": self.config.managers,
                "ir": self.config.ir,
                "n_drafts": self.config.n_drafts,
                "rollouts": self.config.rollouts,
                "max_candidates": self.config.max_candidates,
                "opponent_temperature": self.config.opponent_temperature,
                "depth": self.config.depth,
                "strategies": list(self.config.strategies),
            },
            "rounds": [
                {
                    "season": r.season,
                    "playoff_round": r.playoff_round,
                    "as_of_cutoff": r.as_of_cutoff,
                    "opponents_kind": r.opponents_kind,
                    "leakage_ok": r.leakage_ok,
                    "slots": len({s.seat for s in r.slot_results}),
                    "drafts": len(r.slot_results),
                }
                for r in self.rounds
            ],
            "league_comparisons": [c.manifest() for c in self.league_comparisons],
            "leakage_ok": all(r.leakage_ok for r in self.rounds),
        }


# ── Opponents ───────────────────────────────────────────────────────────────


def _top_managers(fitted: FittedLeagueOpponents, limit: int) -> list[str]:
    """The ``limit`` most active historical managers (deterministic tie-break)."""
    ranked = sorted(fitted.manager_pick_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [manager for manager, _ in ranked[:limit]]


def _fit_opponents_for_season(
    league_picks: pd.DataFrame | None, season: int, config: BacktestConfig
) -> FittedLeagueOpponents | None:
    """Fit opponents leave-one-season-out; ``None`` when history omits the season.

    The fitted model trains on every league season *except* the one being
    backtested, so a season never informs its own opponents (SPEC section 6). If the
    league history does not cover ``season`` (or nothing is left after excluding it),
    the caller falls back to the greedy opponent.
    """
    if league_picks is None or "season" not in league_picks.columns:
        return None
    seasons = {int(s) for s in league_picks["season"].unique()}
    if season not in seasons:
        return None
    train = league_picks.loc[league_picks["season"].astype(int) != season]
    if train.empty:
        return None
    return fit_opponent_models(train, OpponentFitConfig(temperature=config.opponent_temperature))


def _managers_and_opponents(
    fitted: FittedLeagueOpponents | None, config: BacktestConfig
) -> tuple[list[str], OpponentModel | dict[str, OpponentModel], str]:
    """Resolve the manager ids, opponent policy, and a label for the round."""
    if fitted is not None:
        managers_list = _top_managers(fitted, config.managers)
        while len(managers_list) < config.managers:
            managers_list.append(f"seat{len(managers_list) + 1}")
        return managers_list, fitted.as_mapping(managers_list), "fitted-league"
    managers_list = [f"seat{i + 1}" for i in range(config.managers)]
    greedy = GreedyOpponentModel(temperature=config.opponent_temperature)
    return managers_list, greedy, "greedy"


# ── Draft playout ───────────────────────────────────────────────────────────


def _oracle_pick(
    strategy: Strategy,
    state: DraftState,
    oracle: str,
    opponent_model: OpponentModel | dict[str, OpponentModel],
    config: BacktestConfig,
    rng: random.Random,
) -> DraftAsset:
    """The asset the oracle drafts under ``strategy`` at the current slot."""
    if strategy == "random_legal":
        legal = state.legal_assets(oracle)
        if not legal:
            raise ValueError(f"oracle {oracle!r} has no legal pick")
        return legal[rng.randrange(len(legal))]
    if strategy == "greedy_vor":
        replacement = replacement_levels(state, config.managers)
        return greedy_vor_pick(state, oracle, replacement)
    cfg = config.recommend_config()
    if strategy == "one_step":
        cfg = replace(cfg, depth=1)
    return choose_pick(state, oracle, opponent_model, config=cfg, managers=config.managers)


def _play_oracle_draft(
    base_state: DraftState,
    oracle: str,
    strategy: Strategy,
    opponent_model: OpponentModel | dict[str, OpponentModel],
    config: BacktestConfig,
    seed: int,
) -> DraftState:
    """Play a full draft with ``oracle`` seated under ``strategy`` vs. opponents.

    Opponents draw from one seeded ``rng`` so the whole playout is determined by
    ``(base_state, seed)``; the oracle's own policy is deterministic given the state.
    """
    state = base_state.copy()
    rng = random.Random(seed)
    while not state.is_complete:
        current = state.current_manager
        if current == oracle:
            asset = _oracle_pick(strategy, state, oracle, opponent_model, config, rng)
        else:
            model = _resolve_model(opponent_model, current)
            asset = model.pick(state, current, rng)
        state.apply_pick(asset)
    return state


# ── As-of projection & series evaluation capture (US-026) ───────────────────


def _round_series(series: pd.DataFrame, season: int, playoff_round: int) -> pd.DataFrame:
    """The ``series`` rows for one backtested season+round."""
    return series.loc[
        (series["year"].astype(int) == int(season))
        & (series["playoff_round"].astype("Int64") == int(playoff_round))
    ]


def _market_series_prob(
    odds: pd.DataFrame | None, top_id: int, bottom_id: int, season: int
) -> float | None:
    """Market-implied ``P(top seed wins the series)`` from de-vigged per-game odds.

    Locates the historical playoff games between the two teams that season, reads the
    de-vigged implied win probability for the top seed at home and away, and runs those
    per-venue probabilities through the exact best-of-7 series model. ``None`` when no
    committed odds cover the matchup. This is a *post-hoc* calibration measurement of
    the series model under market inputs — it is never used to make a pick.
    """
    if odds is None or odds.empty:
        return None
    scoped = odds.loc[
        (odds["season_end_year"].astype(int) == int(season))
        & odds["is_playoff"].astype(bool)
        & (
            ((odds["home_team_id"] == top_id) & (odds["away_team_id"] == bottom_id))
            | ((odds["home_team_id"] == bottom_id) & (odds["away_team_id"] == top_id))
        )
    ].dropna(subset=["home_implied", "away_implied"])
    if scoped.empty:
        return None
    top_home = scoped.loc[scoped["home_team_id"] == top_id, "home_implied"].astype(float)
    top_away = scoped.loc[scoped["away_team_id"] == top_id, "away_implied"].astype(float)
    home_mean = float(top_home.mean()) if not top_home.empty else None
    away_mean = float(top_away.mean()) if not top_away.empty else None
    if home_mean is None and away_mean is None:
        return None
    p_home = home_mean if home_mean is not None else away_mean
    p_away = away_mean if away_mean is not None else home_mean
    assert p_home is not None and p_away is not None
    return simulate_series(p_home, p_away).p_a_win_series


def _build_projection_eval(
    result: Any,
    skater_actual: dict[tuple[int, int, int], int],
    team_actual: dict[tuple[int, int, int], int],
    *,
    season_id: int,
    playoff_round: int,
) -> ProjectionEval:
    """Pair every as-of projection with its realized round outcome."""
    skaters: list[tuple[int, float, float]] = []
    for rec in result.skaters.to_dict("records"):
        pid = int(rec["player_id"])
        projected = float(rec["expected_points"])
        actual = float(skater_actual.get((season_id, playoff_round, pid), 0))
        skaters.append((pid, projected, actual))
    teams: list[tuple[int, float, float]] = []
    for rec in result.teams.to_dict("records"):
        tid = int(rec["team_id"])
        projected = float(rec["e_goalie_points"])
        actual = float(team_actual.get((season_id, playoff_round, tid), 0))
        teams.append((tid, projected, actual))
    return ProjectionEval(skaters=skaters, teams=teams)


def _build_series_evals(
    result: Any,
    round_series: pd.DataFrame,
    odds: pd.DataFrame | None,
    *,
    season: int,
) -> list[SeriesEval]:
    """Per-series stat-only + market-aware win probabilities vs. the actual winner."""
    stat_by_team = {
        int(rec["team_id"]): float(rec["p_series_win"])
        for rec in result.teams.to_dict("records")
    }
    evals: list[SeriesEval] = []
    for row in round_series.to_dict("records"):
        top_raw = row.get("top_seed_team_id")
        bottom_raw = row.get("bottom_seed_team_id")
        winner_raw = row.get("winning_team_id")
        if pd.isna(top_raw) or pd.isna(bottom_raw) or pd.isna(winner_raw):
            continue
        top_id = int(top_raw)
        bottom_id = int(bottom_raw)
        if top_id not in stat_by_team:
            continue
        top_won = 1 if int(winner_raw) == top_id else 0
        evals.append(
            SeriesEval(
                top_id=top_id,
                bottom_id=bottom_id,
                top_seed_abbrev=str(row.get("top_seed_abbrev", "")),
                bottom_seed_abbrev=str(row.get("bottom_seed_abbrev", "")),
                top_won=top_won,
                p_top_stat=stat_by_team[top_id],
                p_top_market=_market_series_prob(odds, top_id, bottom_id, season),
            )
        )
    return evals


# ── Round / season / run orchestration ─────────────────────────────────────


def replay_round(
    tables: dict[str, pd.DataFrame],
    *,
    season: int,
    playoff_round: int,
    league_picks: pd.DataFrame | None,
    injuries: pd.DataFrame | None,
    odds: pd.DataFrame | None = None,
    snapshot_id: str,
    skater_actual: dict[tuple[int, int, int], int],
    team_actual: dict[tuple[int, int, int], int],
    config: BacktestConfig,
) -> RoundResult:
    """Replay one playoff round: as-of projections, drafts in every slot, scoring."""
    result = build_projection_artifact(
        tables["skater_games"],
        tables["players"],
        tables["team_games"],
        tables["series"],
        season=season,
        playoff_round=playoff_round,
        snapshot_id=snapshot_id,
        injuries=injuries,
        league_picks=league_picks,
        config=replace(config.artifact_config(), slot_strategies=False),
    )
    season_id = _season_id_for(tables["series"], season)
    cutoff = result.as_of_cutoff

    round_series = _round_series(tables["series"], season, playoff_round)
    projection_eval = _build_projection_eval(
        result, skater_actual, team_actual, season_id=season_id, playoff_round=playoff_round
    )
    series_evals = _build_series_evals(result, round_series, odds, season=season)

    round_ids = round_game_ids(
        tables["team_games"], tables["series"], season_id=season_id, playoff_round=playoff_round
    )
    assert_round_inputs_leakfree(tables["team_games"], round_ids, cutoff, label="team")
    assert_round_inputs_leakfree(tables["skater_games"], round_ids, cutoff, label="skater")

    fitted = _fit_opponents_for_season(league_picks, season, config)
    managers_list, opponent_model, opponents_kind = _managers_and_opponents(fitted, config)

    pool = build_pool_from_frames(result.skaters, result.teams, ir=config.ir)
    warnings = list(result.warnings)

    shortfall = _draft_shortfall(pool, config.managers, config.ir)
    if shortfall is not None:
        warnings.append(
            f"round skipped: pool cannot fill a {config.managers}-manager draft "
            f"({shortfall}); late rounds have too few eligible teams"
        )
        return RoundResult(
            season=season,
            season_id=season_id,
            playoff_round=playoff_round,
            as_of_cutoff=cutoff,
            opponents_kind=opponents_kind,
            eligible_team_abbrevs=list(result.manifest["eligible_team_abbrevs"]),
            leakage_ok=True,
            slot_results=[],
            warnings=warnings,
            projection_eval=projection_eval,
            series_evals=series_evals,
        )

    base_state = DraftState.new(managers_list, pool, allow_ir=config.ir)

    slot_results: list[SlotResult] = []
    for strategy in config.strategies:
        for seat in range(1, config.managers + 1):
            oracle = managers_list[seat - 1]
            for draft_index in range(config.n_drafts):
                draft_seed = config.seed + draft_index
                final = _play_oracle_draft(
                    base_state, oracle, strategy, opponent_model, config, draft_seed
                )
                opponent_points = {
                    manager: _score_active_roster(
                        final,
                        manager,
                        skater_actual,
                        team_actual,
                        season_id=season_id,
                        playoff_round=playoff_round,
                    )
                    for manager in managers_list
                    if manager != oracle
                }
                oracle_points = _score_active_roster(
                    final,
                    oracle,
                    skater_actual,
                    team_actual,
                    season_id=season_id,
                    playoff_round=playoff_round,
                )
                roster_keys = [a.key for a in final.rosters[oracle].all_assets()]
                slot_results.append(
                    SlotResult(
                        strategy=strategy,
                        seat=seat,
                        oracle_manager=oracle,
                        draft_index=draft_index,
                        oracle_points=oracle_points,
                        opponent_points=opponent_points,
                        roster_keys=roster_keys,
                    )
                )

    return RoundResult(
        season=season,
        season_id=season_id,
        playoff_round=playoff_round,
        as_of_cutoff=cutoff,
        opponents_kind=opponents_kind,
        eligible_team_abbrevs=list(result.manifest["eligible_team_abbrevs"]),
        leakage_ok=True,
        slot_results=slot_results,
        warnings=warnings,
        projection_eval=projection_eval,
        series_evals=series_evals,
    )


def _draft_shortfall(pool: list[DraftAsset], managers: int, allow_ir: bool) -> str | None:
    """Describe why ``pool`` cannot fill a ``managers``-way draft, or ``None`` if it can.

    Late playoff rounds have too few eligible teams to seat a full league — the Cup
    Final's two teams cannot supply four managers a unique goalie, for instance. This
    reports the first unmet positional demand so the round is skipped honestly rather
    than crashing mid-draft (SPEC section 7).
    """
    capacity = roster_capacity(allow_ir)
    have = {"F": 0, "D": 0, "G": 0}
    for asset in pool:
        have[asset.position] += 1
    demand = {
        "F": capacity.forwards * managers,
        "D": capacity.defense * managers,
        "G": capacity.goalies * managers,
    }
    for position in ("F", "D", "G"):
        if have[position] < demand[position]:
            return f"{position}: {have[position]} available < {demand[position]} needed"
    return None


def _season_id_for(series: pd.DataFrame, season: int) -> int:
    """Resolve the numeric ``season_id`` for a backtested season from the series table."""
    scoped = series.loc[series["year"].astype(int) == int(season)]
    if scoped.empty:
        raise ValueError(f"no series rows for season {season}")
    return int(scoped["season_id"].iloc[0])


def _season_rounds(series: pd.DataFrame, season: int) -> list[int]:
    """Best-of-7 playoff rounds (1-4) present for ``season`` (round 0 excluded)."""
    scoped = series.loc[series["year"].astype(int) == int(season)]
    rounds = sorted({int(r) for r in scoped["playoff_round"].unique() if int(r) >= 1})
    return rounds


def _score_league_roster(
    picks: pd.DataFrame,
    skater_actual: dict[tuple[int, int, int], int],
    team_actual: dict[tuple[int, int, int], int],
    *,
    season_id: int,
    playoff_round: int,
) -> float:
    """Actual active-roster points of one league manager's real picks for a round.

    Scores F/D via :data:`skater_actual` and the goalie slot via :data:`team_actual`,
    skipping IR slots and de-duplicating by asset so a manager is scored the same way
    the oracle rosters are (SPEC section 8).
    """
    total = 0.0
    seen: set[tuple[str, int]] = set()
    for rec in picks.to_dict("records"):
        position = str(rec.get("position", ""))
        if position in ("IR_F", "IR_D"):
            continue
        pid = rec.get("player_id")
        tid = rec.get("team_id")
        if position == "G" and not pd.isna(tid):
            key = ("team", int(tid))
            if key in seen:
                continue
            seen.add(key)
            total += team_actual.get((season_id, playoff_round, int(tid)), 0)
        elif not pd.isna(pid):
            key = ("player", int(pid))
            if key in seen:
                continue
            seen.add(key)
            total += skater_actual.get((season_id, playoff_round, int(pid)), 0)
    return total


def _league_comparisons(
    rounds: list[RoundResult],
    league_picks: pd.DataFrame | None,
    skater_actual: dict[tuple[int, int, int], int],
    team_actual: dict[tuple[int, int, int], int],
) -> list[LeagueComparison]:
    """Compare oracle simulated rosters to real league rosters where seasons overlap.

    For each backtested round whose ``(season, draft_event)`` appears in the committed
    league draft history, score every real manager's active roster through the rules
    engine and pair it with the oracle policy's mean/best simulated points that round.
    Rounds without league overlap are simply omitted.
    """
    if league_picks is None or league_picks.empty or "season" not in league_picks.columns:
        return []
    comparisons: list[LeagueComparison] = []
    for rnd in rounds:
        event = ROUND_TO_DRAFT_EVENT.get(rnd.playoff_round)
        if event is None:
            continue
        scoped = league_picks.loc[
            (league_picks["season"].astype(int) == int(rnd.season))
            & (league_picks["draft_event"].astype(str) == event)
        ]
        if scoped.empty:
            continue
        oracle_points = [
            s.oracle_points for s in rnd.slot_results if s.strategy == "oracle"
        ]
        if not oracle_points:
            continue
        managers = [
            LeagueManagerRoster(
                manager=str(manager),
                actual_points=_score_league_roster(
                    picks,
                    skater_actual,
                    team_actual,
                    season_id=rnd.season_id,
                    playoff_round=rnd.playoff_round,
                ),
            )
            for manager, picks in scoped.groupby("manager")
        ]
        comparisons.append(
            LeagueComparison(
                season=rnd.season,
                playoff_round=rnd.playoff_round,
                draft_event=event,
                managers=sorted(managers, key=lambda m: (-m.actual_points, m.manager)),
                oracle_mean_points=sum(oracle_points) / len(oracle_points),
                oracle_best_points=max(oracle_points),
            )
        )
    return comparisons


def run_backtest(
    tables: dict[str, pd.DataFrame],
    seasons: list[int],
    *,
    league_picks: pd.DataFrame | None = None,
    injuries: pd.DataFrame | None = None,
    odds: pd.DataFrame | None = None,
    snapshot_id: str = "backtest",
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Replay every playoff round of each season in ``seasons`` end-to-end.

    Builds the actual-result lookups once, then replays each round (as-of
    projections, drafts in every slot, actual scoring) under the leakage guard.
    ``odds`` (de-vigged historical betting lines) power the market-aware series-Brier
    track and are never used to make a pick. Deterministic given ``(tables, seed)``.
    """
    cfg = config or BacktestConfig()
    if not seasons:
        raise ValueError("seasons must be non-empty")
    skater_actual = skater_actual_points(tables["skater_games"], tables["series"])
    team_actual = team_actual_goalie_points(tables["team_games"], tables["series"])

    rounds: list[RoundResult] = []
    for season in seasons:
        for playoff_round in _season_rounds(tables["series"], season):
            rounds.append(
                replay_round(
                    tables,
                    season=season,
                    playoff_round=playoff_round,
                    league_picks=league_picks,
                    injuries=injuries,
                    odds=odds,
                    snapshot_id=snapshot_id,
                    skater_actual=skater_actual,
                    team_actual=team_actual,
                    config=cfg,
                )
            )

    comparisons = _league_comparisons(rounds, league_picks, skater_actual, team_actual)

    return BacktestResult(
        run_id=cfg.resolved_run_id(seasons),
        seasons=list(seasons),
        config=cfg,
        rounds=rounds,
        generated_at=datetime.now(UTC).isoformat(),
        league_comparisons=comparisons,
    )


def write_backtest(result: BacktestResult, root: Path = DEFAULT_BACKTEST_ROOT) -> Path:
    """Persist the run manifest + per-round intermediates under ``root/<run-id>/``.

    ``manifest.json`` is committed; the per-round JSON files under ``rounds/`` are
    regenerable intermediates (gitignored) that reporting (US-026) reads back.
    """
    out_dir = root / result.run_id
    rounds_dir = out_dir / "rounds"
    rounds_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(result.manifest(), indent=2) + "\n", encoding="utf-8"
    )
    for round_result in result.rounds:
        name = f"{round_result.season}-r{round_result.playoff_round}.json"
        (rounds_dir / name).write_text(
            json.dumps(round_result.manifest(), indent=2) + "\n", encoding="utf-8"
        )
    return out_dir


def _load_odds(normalized_dir: Path) -> pd.DataFrame | None:
    """Load committed de-vigged betting odds if present, else ``None``.

    Powers the market-aware series-Brier track in reporting; never used to make a pick.
    """
    path = normalized_dir / "odds.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def run_backtest_from_normalized(
    *,
    seasons: list[int],
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    backtest_root: Path = DEFAULT_BACKTEST_ROOT,
    snapshot: str | None = None,
    config: BacktestConfig | None = None,
) -> tuple[BacktestResult, Path]:
    """Load normalized tables, run the backtest, and persist it to disk.

    When ``snapshot`` is pinned the tables are read from the frozen snapshot copy;
    otherwise the live normalized tables are used. Writes ``manifest.json`` and a
    committed ``report.md`` under ``backtest_root/<run-id>/`` and returns the result
    and that run directory.
    """
    from draft_oracle.backtest.report import write_report

    source_dir = normalized_dir / SNAPSHOTS_SUBDIR / snapshot if snapshot else normalized_dir
    tables = _load_tables(source_dir)
    injuries = _load_injuries(normalized_dir)
    league_picks = _load_league_picks(source_dir)
    odds = _load_odds(normalized_dir)
    snapshot_id = _snapshot_id_for(source_dir, snapshot)

    result = run_backtest(
        tables,
        seasons,
        league_picks=league_picks,
        injuries=injuries,
        odds=odds,
        snapshot_id=snapshot_id,
        config=config,
    )
    out_dir = write_backtest(result, backtest_root)
    write_report(result, out_dir)
    return result, out_dir
