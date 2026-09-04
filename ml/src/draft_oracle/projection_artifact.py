"""Batch projection command and artifact format (US-017, PRD US-007).

Produces a single, self-contained *precomputed* prediction artifact for one
upcoming playoff round so that drafting never depends on live inference. The
artifact is a directory ``artifacts/<season>-r<round>/`` containing:

* ``skaters.parquet`` / ``skaters.csv`` -- one row per draft-eligible skater with
  ``expected_points`` (mean round fantasy points), the ``p10/p50/p90`` uncertainty
  quantiles, the ``pts_per_game`` x ``expected_games`` decomposition, and an
  ``injured`` flag.
* ``teams.parquet`` / ``teams.csv`` -- one row per draft-eligible team (the goalie
  slot is a whole team's goaltending, SPEC section 1) with goalie-slot
  ``e_goalie_points``, ``e_wins``, ``e_games``, ``p_series_win``, and the expected
  shutout wins.
* ``run_manifest.json`` -- the data snapshot id, every sub-model version, the
  feature-set version, git SHA, seeds, generating CLI flags, OS/Python/numpy
  versions, the VOR scarcity summary, and a UTC timestamp.
* ``cheatsheet.md`` -- the value-over-replacement (VOR) draft board (US-018): every
  skater and team priced against its position's replacement level and sorted by VOR.

Composition (no new estimator is learned here):

1. The **bracket state** for ``(season, round)`` comes from the normalized ``series``
   table -- eliminated teams simply do not appear in that round's series, so they and
   their players are excluded automatically (SPEC section 1).
2. The per-game **win** (US-011) and **shutout** (US-012) models plus the **skater
   production** model (US-014) are trained only on games strictly *before* the round
   start (the as-of cutoff). For a genuine pre-round build (round N has no games yet)
   the cutoff derives from the previous round's completion / bracket-announcement
   boundary via :func:`playoff_round_cutoffs`, so the tool runs at the moment it is
   used -- after round N-1 ends, before round N begins (CODE_REVIEW M-1).
   Leakage-free pre-series team snapshots are frozen at that boundary via
   :func:`reconstruct_series_matchups` (SPEC section 6).
3. Each matchup runs through the best-of-7 **series simulator** (US-013) for
   ``E[wins]``, ``E[games]``, ``P(series win)``, goalie-slot points, and the series
   length distribution; each eligible skater runs through the seeded round-point
   **projection** (US-016) for its team's length distribution.

Determinism (SPEC section 3): every stochastic step is seeded and the Monte-Carlo
seed for a skater is derived from ``(seed, season, round, player)``. The same snapshot
reproduces outputs to float-ULP across platforms and byte-identically on the generating
platform. The wall-clock timestamp and git SHA live only in ``run_manifest.json`` --
never in the Parquet payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from draft_oracle._projection_combined import (
    _COMBINED_CHEATSHEET_NOTE,
    _COMBINED_DRAFT_ROUND,
    CombinedValuationInput,
    _apply_combined_valuation,
)
from draft_oracle._projection_io import (
    DEFAULT_ARTIFACTS_ROOT,
    DEFAULT_NORMALIZED_DIR,
    SNAPSHOTS_SUBDIR,
    _load_injuries,
    _load_league_picks,
    _load_tables,
    _require_complete_snapshot,
    _snapshot_id_for,
)
from draft_oracle._projection_ir import _apply_ir_stash, _IrStashInput
from draft_oracle._projection_manifest import ProjectionManifestInput, _projection_manifest
from draft_oracle._projection_rows import (
    _build_skater_rows,
    _build_team_rows,
    _BuildSkaterRowsRequest,
    _BuildTeamRowsRequest,
)
from draft_oracle._projection_slot_report import SlotReportInput, _build_slot_report
from draft_oracle.features.skater import (
    SkaterFeatureRequest,
    build_skater_features,
)
from draft_oracle.models.game_win import GameWinConfig, GameWinModel, train_game_win_model
from draft_oracle.models.projections import DEFAULT_HORIZON, DEFAULT_N_SIMS
from draft_oracle.models.series_sim import reconstruct_series_matchups
from draft_oracle.models.shutout import ShutoutConfig, ShutoutModel, train_shutout_model
from draft_oracle.models.skater_production import (
    SkaterProductionConfig,
    SkaterProductionModel,
    playoff_round_cutoffs,
    train_skater_production_model,
)
from draft_oracle.optimize.slot_strategies import (
    SlotStrategyConfig,
    SlotStrategyReport,
    write_slot_strategies,
)
from draft_oracle.optimize.vor import (
    CheatSheet,
    VorConfig,
    build_cheatsheet,
    write_cheatsheet,
)

__all__ = [
    "DEFAULT_ARTIFACTS_ROOT",
    "DEFAULT_NORMALIZED_DIR",
    "LIVE_PROJECTION_VERSION",
    "SKATER_COLUMNS",
    "SNAPSHOTS_SUBDIR",
    "TEAM_COLUMNS",
    "_COMBINED_CHEATSHEET_NOTE",
    "ProjectArtifactConfig",
    "ProjectArtifactResult",
    "_load_league_picks",
    "_load_tables",
    "_require_complete_snapshot",
    "_snapshot_id_for",
    "build_projection_artifact",
    "build_projection_artifact_from_normalized",
    "write_projection_artifact",
]

LIVE_PROJECTION_VERSION = "live-projection-v1"

# Injury statuses that make a skater doubtful/unavailable (see ingest.injuries).
_INJURED_STATUSES = frozenset({"out", "ir", "day_to_day"})

# Fixed, deterministic column order for the two artifact tables.
SKATER_COLUMNS: tuple[str, ...] = (
    "player_id",
    "player_name",
    "team_abbrev",
    "position",
    "expected_points",
    "p10",
    "p50",
    "p90",
    "pts_per_game",
    "expected_games",
    "availability_multiplier",
    "injured",
    "low_confidence",
    "ir_stash_ev",
    "ir_stash_value",
    "ir_verdict",
)
TEAM_COLUMNS: tuple[str, ...] = (
    "team_id",
    "team_abbrev",
    "opponent_abbrev",
    "is_top_seed",
    "playoff_round",
    "p_series_win",
    "e_wins",
    "e_games",
    "e_goalie_points",
    "e_shutout_wins",
)


@dataclass(frozen=True)
class ProjectArtifactConfig:
    """Knobs for the batch projection; every stochastic step is seeded."""

    seed: int = 20260827
    n_sims: int = DEFAULT_N_SIMS
    horizon: int = DEFAULT_HORIZON
    managers: int = 4
    ir: bool = False
    slot_strategies: bool = True
    combine_final_rounds: bool = True
    no_refresh: bool | None = None
    slot_strategy_config: SlotStrategyConfig | None = field(default=None)
    production_config: SkaterProductionConfig | None = field(default=None)

    @property
    def vor_config(self) -> VorConfig:
        """League parameters that drive VOR replacement levels + cheat-sheet layout."""
        return VorConfig(managers=self.managers, ir=self.ir)

    @property
    def resolved_slot_config(self) -> SlotStrategyConfig:
        """The per-slot report config (seeded from the run seed when unset)."""
        return self.slot_strategy_config or SlotStrategyConfig(seed=self.seed)


@dataclass
class ProjectArtifactResult:
    """In-memory result of a batch projection run (before/after it is written)."""

    season: int
    playoff_round: int
    as_of_cutoff: str
    skaters: pd.DataFrame
    teams: pd.DataFrame
    cheatsheet: CheatSheet
    manifest: dict[str, Any]
    warnings: list[str]
    slot_strategies: SlotStrategyReport | None = None


@dataclass(frozen=True)
class _ProjectionRoundContext:
    config: ProjectArtifactConfig
    prod_config: SkaterProductionConfig
    warnings: list[str]
    round_series: pd.DataFrame
    season_id: int
    cutoff: str
    train_tg: pd.DataFrame
    train_sk: pd.DataFrame


@dataclass(frozen=True)
class _ProjectionRoundInputs:
    round_series: pd.DataFrame
    season_id: int
    cutoff: str


@dataclass(frozen=True)
class _ProjectionModels:
    win_model: GameWinModel
    shutout_model: ShutoutModel
    prod_model: SkaterProductionModel
    matchups: dict[tuple[int, int, int], Any]


@dataclass(frozen=True)
class _ProjectionOutputs:
    skaters: pd.DataFrame
    teams: pd.DataFrame
    cheatsheet: CheatSheet
    ir_valuations: list[Any]
    slot_report: SlotStrategyReport | None
    length_by_abbrev: dict[str, dict[int, float]]
    combined_diagnostics: list[dict[str, Any]] | None


@dataclass(frozen=True)
class _TeamProjectionRows:
    team_rows: list[dict[str, Any]]
    length_by_abbrev: dict[str, dict[int, float]]
    combined_by_abbrev: dict[str, tuple[float, dict[int, float]]] | None
    combined_diagnostics: list[dict[str, Any]] | None


def _injured_player_ids(injuries: pd.DataFrame | None) -> set[int]:
    """Skater player ids currently out/IR/day-to-day (goalies excluded here)."""
    if injuries is None or injuries.empty:
        return set()
    hurt = injuries.loc[injuries["status"].isin(_INJURED_STATUSES) & (injuries["position"] != "G")]
    return {int(pid) for pid in hurt["player_id"].tolist()}


def _resolve_season_id(round_series: pd.DataFrame, season: int) -> int:
    """The single ``season_id`` backing a playoff year (e.g. 2026 -> 20252026)."""
    season_ids = {int(s) for s in round_series["season_id"].dropna().unique()}
    if len(season_ids) != 1:
        raise ValueError(
            f"expected exactly one season_id for season {season}, found {sorted(season_ids)}"
        )
    return season_ids.pop()


def _projection_round_context(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    *,
    season: int,
    playoff_round: int,
    config: ProjectArtifactConfig,
) -> _ProjectionRoundContext:
    prod_config = config.production_config or SkaterProductionConfig(seed=config.seed)
    warnings: list[str] = []
    round_inputs = _projection_round_inputs(team_games, series, season, playoff_round)
    train_tg, train_sk = _require_training_frames(skater_games, team_games, round_inputs.cutoff)
    return _ProjectionRoundContext(
        config=config,
        prod_config=prod_config,
        warnings=warnings,
        round_series=round_inputs.round_series,
        season_id=round_inputs.season_id,
        cutoff=round_inputs.cutoff,
        train_tg=train_tg,
        train_sk=train_sk,
    )


def _projection_round_inputs(
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    season: int,
    playoff_round: int,
) -> _ProjectionRoundInputs:
    round_series = _round_series_for_context(series, season, playoff_round)
    if round_series.empty:
        raise ValueError(
            f"no series found for season {season} round {playoff_round}; "
            "run ingest/normalize so the bracket is available"
        )
    season_id = _resolve_season_id(round_series, season)
    cutoff = _round_cutoff(team_games, series, season_id, playoff_round)
    if cutoff is None:
        raise ValueError(
            f"cannot derive the round-start cutoff for season {season} round {playoff_round}; "
            "the previous round has no games in the archive yet"
        )
    return _ProjectionRoundInputs(round_series, season_id, cutoff)


def _round_series_for_context(
    series: pd.DataFrame,
    season: int,
    playoff_round: int,
) -> pd.DataFrame:
    return series.loc[
        (series["year"].astype(int) == int(season))
        & (series["playoff_round"].astype("Int64") == int(playoff_round))
    ]


def _round_cutoff(
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    season_id: int,
    playoff_round: int,
) -> str | None:
    starts = playoff_round_cutoffs(team_games, series)
    return starts.get(season_id, {}).get(int(playoff_round))


def _training_frames(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    cutoff: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff_ts = pd.Timestamp(cutoff)
    tg = team_games.copy()
    tg["game_date"] = pd.to_datetime(tg["game_date"])
    sk = skater_games.copy()
    sk["game_date"] = pd.to_datetime(sk["game_date"])
    return tg.loc[tg["game_date"] < cutoff_ts], sk.loc[sk["game_date"] < cutoff_ts]


def _require_training_frames(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    cutoff: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_tg, train_sk = _training_frames(skater_games, team_games, cutoff)
    if train_tg.empty or train_sk.empty:
        raise ValueError("no games available before the round start to train on")
    return train_tg, train_sk


def _train_projection_models(
    context: _ProjectionRoundContext,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    series: pd.DataFrame,
) -> _ProjectionModels:
    return _ProjectionModels(
        win_model=train_game_win_model(
            context.train_tg,
            odds=None,
            config=GameWinConfig(seed=context.config.seed),
        ).model,
        shutout_model=train_shutout_model(
            context.train_tg,
            config=ShutoutConfig(seed=context.config.seed),
        ).model,
        prod_model=train_skater_production_model(
            context.train_sk,
            players,
            context.train_tg,
            series,
            config=context.prod_config,
        ).model,
        matchups=reconstruct_series_matchups(team_games, series=series),
    )


def _projection_outputs(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    injuries: pd.DataFrame | None,
    league_picks: pd.DataFrame | None,
    *,
    season: int,
    playoff_round: int,
    context: _ProjectionRoundContext,
    models: _ProjectionModels,
) -> _ProjectionOutputs:
    team_projection = _team_projection_rows(context, models, season, playoff_round)
    skater_rows = _skater_projection_rows(
        skater_games,
        players,
        team_games,
        injuries,
        playoff_round,
        context,
        models,
        team_projection.length_by_abbrev,
        team_projection.combined_by_abbrev,
    )
    skaters = _finalize_skaters(skater_rows)
    teams = _finalize_teams(team_projection.team_rows)
    cheatsheet = build_cheatsheet(skaters, teams, config=context.config.vor_config)
    if team_projection.combined_diagnostics is not None:
        cheatsheet.note = _COMBINED_CHEATSHEET_NOTE
    return _ProjectionOutputs(
        skaters=skaters,
        teams=teams,
        cheatsheet=cheatsheet,
        ir_valuations=_apply_ir_stash(
            _IrStashInput(
                skaters,
                cheatsheet,
                injuries,
                team_projection.length_by_abbrev,
                context.train_sk,
                context.train_tg,
                context.config,
            )
        ),
        slot_report=_build_slot_report(
            SlotReportInput(skaters, teams, league_picks, context.warnings, context.config)
        ),
        length_by_abbrev=team_projection.length_by_abbrev,
        combined_diagnostics=team_projection.combined_diagnostics,
    )


def _team_projection_rows(
    context: _ProjectionRoundContext,
    models: _ProjectionModels,
    season: int,
    playoff_round: int,
) -> _TeamProjectionRows:
    team_rows, length_by_abbrev = _build_team_rows(
        _BuildTeamRowsRequest(
            round_series=context.round_series,
            matchups=models.matchups,
            win_model=models.win_model,
            shutout_model=models.shutout_model,
            season=int(season),
            playoff_round=int(playoff_round),
            warnings=context.warnings,
        )
    )
    combined_by_abbrev: dict[str, tuple[float, dict[int, float]]] | None = None
    combined_diagnostics: list[dict[str, Any]] | None = None
    if context.config.combine_final_rounds and int(playoff_round) == _COMBINED_DRAFT_ROUND:
        combined = _apply_combined_valuation(
            CombinedValuationInput(
                team_rows,
                context.round_series,
                models.matchups,
                models.win_model,
                models.shutout_model,
                int(season),
                context.warnings,
            )
        )
        if combined is not None:
            combined_by_abbrev, combined_diagnostics = combined
            if context.config.ir:
                context.warnings.append(
                    "combined R3+R4 valuation covers active-roster projections only; "
                    "IR-stash values remain single-round (R3)"
                )
    return _TeamProjectionRows(
        team_rows=team_rows,
        length_by_abbrev=length_by_abbrev,
        combined_by_abbrev=combined_by_abbrev,
        combined_diagnostics=combined_diagnostics,
    )


def _skater_projection_rows(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    injuries: pd.DataFrame | None,
    playoff_round: int,
    context: _ProjectionRoundContext,
    models: _ProjectionModels,
    length_by_abbrev: dict[str, dict[int, float]],
    combined_by_abbrev: dict[str, tuple[float, dict[int, float]]] | None,
) -> list[dict[str, Any]]:
    injured_ids = _injured_player_ids(injuries)
    feats = build_skater_features(
        skater_games,
        players,
        team_games,
        SkaterFeatureRequest(
            season_id=context.season_id,
            as_of_date=context.cutoff,
            playoff_round=int(playoff_round),
        ),
    )
    eligible_feats = feats.loc[feats["team_abbrev"].isin(length_by_abbrev)]
    if eligible_feats.empty:
        return []
    projected = models.prod_model.project(eligible_feats)
    return _build_skater_rows(
        _BuildSkaterRowsRequest(
            projected=projected,
            length_by_abbrev=length_by_abbrev,
            injured_ids=injured_ids,
            season_id=context.season_id,
            playoff_round=int(playoff_round),
            config=context.config,
            combined_by_abbrev=combined_by_abbrev,
        )
    )


def build_projection_artifact(
    skater_games: pd.DataFrame,
    players: pd.DataFrame,
    team_games: pd.DataFrame,
    series: pd.DataFrame,
    *,
    season: int,
    playoff_round: int,
    snapshot_id: str,
    injuries: pd.DataFrame | None = None,
    league_picks: pd.DataFrame | None = None,
    config: ProjectArtifactConfig | None = None,
    git_sha: str | None = None,
    generated_at: str | None = None,
) -> ProjectArtifactResult:
    """Compose the sub-models into a batch projection artifact for one round.

    ``season`` is the playoff end year (e.g. ``2026``) and ``playoff_round`` the
    round number (1-4). The bracket is read from the ``series`` table, so eliminated
    teams are excluded automatically. Sub-models train only on games strictly before
    the round start; every stochastic step is seeded for byte-identical reruns.
    """
    config = config or ProjectArtifactConfig()
    context = _projection_round_context(
        skater_games,
        team_games,
        series,
        season=season,
        playoff_round=playoff_round,
        config=config,
    )
    models = _train_projection_models(context, players, team_games, series)
    outputs = _projection_outputs(
        skater_games,
        players,
        team_games,
        injuries,
        league_picks,
        season=season,
        playoff_round=playoff_round,
        context=context,
        models=models,
    )

    manifest = _projection_manifest(
        ProjectionManifestInput(
            artifact_version=LIVE_PROJECTION_VERSION,
            season=int(season),
            playoff_round=int(playoff_round),
            snapshot_id=snapshot_id,
            context=context,
            outputs=outputs,
            config=config,
            git_sha=git_sha,
            generated_at=generated_at,
        )
    )

    return ProjectArtifactResult(
        season=int(season),
        playoff_round=int(playoff_round),
        as_of_cutoff=context.cutoff,
        skaters=outputs.skaters,
        teams=outputs.teams,
        cheatsheet=outputs.cheatsheet,
        manifest=manifest,
        warnings=context.warnings,
        slot_strategies=outputs.slot_report,
    )


def _finalize_skaters(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Deterministically ordered skater table with the fixed column layout."""
    df = _finalized_frame(
        rows, SKATER_COLUMNS, sort_columns=["expected_points", "player_id"]
    )
    df["player_id"] = df["player_id"].astype("int64")
    df["injured"] = df["injured"].astype(bool)
    df["low_confidence"] = df["low_confidence"].astype(bool)
    return df


def _finalize_teams(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Deterministically ordered team table with the fixed column layout."""
    df = _finalized_frame(rows, TEAM_COLUMNS, sort_columns=["p_series_win", "team_id"])
    df["team_id"] = df["team_id"].astype("int64")
    df["playoff_round"] = df["playoff_round"].astype("int64")
    df["is_top_seed"] = df["is_top_seed"].astype(bool)
    return df


def _finalized_frame(
    rows: list[dict[str, Any]], columns: tuple[str, ...], *, sort_columns: list[str]
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame({col: pd.Series(dtype="object") for col in columns})
    df = pd.DataFrame(rows)[list(columns)]
    return df.sort_values(sort_columns, ascending=[False, True], kind="stable").reset_index(
        drop=True
    )


def write_projection_artifact(result: ProjectArtifactResult, out_dir: Path) -> Path:
    """Write the artifact tables + manifest to ``out_dir`` (created if needed).

    Parquet is written with ``index=False`` so re-running on the same snapshot yields
    byte-identical files. The manifest is the only file carrying the wall-clock
    timestamp and git SHA.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result.skaters.to_parquet(out_dir / "skaters.parquet", index=False)
    result.skaters.to_csv(out_dir / "skaters.csv", index=False)
    result.teams.to_parquet(out_dir / "teams.parquet", index=False)
    result.teams.to_csv(out_dir / "teams.csv", index=False)
    write_cheatsheet(result.cheatsheet, out_dir / "cheatsheet.md")
    if result.slot_strategies is not None:
        write_slot_strategies(result.slot_strategies, out_dir / "slot_strategies.md")
    (out_dir / "run_manifest.json").write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out_dir


def build_projection_artifact_from_normalized(
    *,
    season: int,
    playoff_round: int,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT,
    snapshot: str | None = None,
    config: ProjectArtifactConfig | None = None,
) -> tuple[ProjectArtifactResult, Path]:
    """Load normalized tables, build the artifact, and write it to disk.

    When ``snapshot`` is given every input -- core tables, injuries, and league
    picks -- is read from the frozen copy under
    ``normalized_dir/snapshots/<snapshot>/`` so ``(snapshot, seed)`` fully
    determines the artifact; a snapshot that is not a complete, self-contained
    contract makes the pinned run fail loudly (M-10). Otherwise the live
    ``normalized_dir`` is used and the snapshot id is derived from its source
    signature. The artifact is written to ``artifacts_root/<season>-r<round>/``.
    """
    source_dir = normalized_dir / SNAPSHOTS_SUBDIR / snapshot if snapshot else normalized_dir
    if snapshot is not None:
        _require_complete_snapshot(source_dir)
    tables = _load_tables(source_dir)
    injuries = _load_injuries(source_dir)
    league_picks = _load_league_picks(source_dir)
    snapshot_id = _snapshot_id_for(source_dir, snapshot)

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
        config=config,
    )
    out_dir = artifacts_root / f"{season}-r{playoff_round}"
    write_projection_artifact(result, out_dir)
    return result, out_dir
