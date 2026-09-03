"""Backtest replay result and config records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from draft_oracle import __version__
from draft_oracle.optimize.recommend import RecommendConfig
from draft_oracle.projection_artifact import ProjectArtifactConfig

Strategy = Literal["oracle", "greedy_vor", "one_step", "random_legal"]
STRATEGIES: tuple[Strategy, ...] = ("oracle", "greedy_vor", "one_step", "random_legal")

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
        self._validate_minimums()
        self._validate_strategies()

    def _validate_minimums(self) -> None:
        for value, name, minimum in (
            (self.managers, "managers", 2),
            (self.n_drafts, "n_drafts", 1),
        ):
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}, got {value}")

    def _validate_strategies(self) -> None:
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


@dataclass(frozen=True)
class SeriesEval:
    """One backtested series: the model's win probability vs. the actual winner.

    ``p_top_stat`` is the stat-only series-model probability the top seed wins its
    round (the number the projection artifact actually drafted from). ``p_top_market``
    is a market-aware probability derived from the series' game-1 (pre-series) de-vigged
    betting line for the same series, or ``None`` where no historical odds cover it. Both
    are scored against ``top_won`` (1 if the top seed won the series) via the Brier score
    in reporting.
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
    scored_rounds: list[int] = field(default_factory=list)
    slot_results: list[SlotResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    projection_eval: ProjectionEval | None = None
    series_evals: list[SeriesEval] = field(default_factory=list)

    def manifest(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "season_id": self.season_id,
            "playoff_round": self.playoff_round,
            "scored_rounds": self.scored_rounds or [self.playoff_round],
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
    across the snake slots for the round; ``managers`` are one named league's real
    active-roster scores through the same rules engine. Separate leagues always produce
    separate comparison rows.
    """

    season: int
    playoff_round: int
    draft_event: str
    managers: list[LeagueManagerRoster]
    oracle_mean_points: float
    oracle_best_points: float
    league_name: str | None = None

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
            "league_name": self.league_name,
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
