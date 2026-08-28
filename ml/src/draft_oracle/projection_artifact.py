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
  feature-set version, the git SHA, the seeds, the VOR scarcity summary, and a UTC
  timestamp.
* ``cheatsheet.md`` -- the value-over-replacement (VOR) draft board (US-018): every
  skater and team priced against its position's replacement level and sorted by VOR.

Composition (no new estimator is learned here):

1. The **bracket state** for ``(season, round)`` comes from the normalized ``series``
   table -- eliminated teams simply do not appear in that round's series, so they and
   their players are excluded automatically (SPEC section 1).
2. The per-game **win** (US-011) and **shutout** (US-012) models plus the **skater
   production** model (US-014) are trained only on games strictly *before* the round
   start (the as-of cutoff). Leakage-free pre-series team snapshots are frozen at the
   round start via :func:`reconstruct_series_matchups` (SPEC section 6).
3. Each matchup runs through the best-of-7 **series simulator** (US-013) for
   ``E[wins]``, ``E[games]``, ``P(series win)``, goalie-slot points, and the series
   length distribution; each eligible skater runs through the seeded round-point
   **projection** (US-016) for its team's length distribution.

Determinism (SPEC section 3): every stochastic step is seeded and the Monte-Carlo
seed for a skater is derived from ``(seed, season, round, player)``, so re-running on
the same snapshot reproduces byte-identical Parquet outputs. The wall-clock timestamp
and git SHA live only in ``run_manifest.json`` -- never in the Parquet payload.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from draft_oracle import __version__
from draft_oracle.features.skater import FEATURE_SET_VERSION, build_skater_features
from draft_oracle.models.game_win import (
    GAME_WIN_MODEL_VERSION,
    GameWinConfig,
    train_game_win_model,
)
from draft_oracle.models.projections import (
    DEFAULT_HORIZON,
    DEFAULT_N_SIMS,
    PROJECTION_VERSION,
    _row_seed,
    project_skater_round,
)
from draft_oracle.models.returns import (
    STATUS_MEAN_GAMES,
    ReturnTimeModel,
    derive_absence_spells,
    fit_return_time_model,
)
from draft_oracle.models.series_sim import (
    SERIES_SIM_VERSION,
    _matchup_key,
    _predict_series,
    reconstruct_series_matchups,
)
from draft_oracle.models.shutout import (
    SHUTOUT_MODEL_VERSION,
    ShutoutConfig,
    train_shutout_model,
)
from draft_oracle.models.skater_production import (
    SKATER_PRODUCTION_VERSION,
    SkaterProductionConfig,
    playoff_round_starts,
    train_skater_production_model,
)
from draft_oracle.optimize.ir_value import (
    StashInput,
    StashValuation,
    build_stash_valuations,
    render_ir_section,
)
from draft_oracle.optimize.vor import (
    CheatSheet,
    VorConfig,
    build_cheatsheet,
    write_cheatsheet,
)

__all__ = [
    "LIVE_PROJECTION_VERSION",
    "SKATER_COLUMNS",
    "TEAM_COLUMNS",
    "ProjectArtifactConfig",
    "ProjectArtifactResult",
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
    production_config: SkaterProductionConfig | None = field(default=None)

    @property
    def vor_config(self) -> VorConfig:
        """League parameters that drive VOR replacement levels + cheat-sheet layout."""
        return VorConfig(managers=self.managers, ir=self.ir)


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


def _git_sha() -> str | None:
    """Current git commit SHA, or ``None`` when git is unavailable (e.g. tests)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - env dependent
        return None
    sha = out.stdout.strip()
    return sha or None


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


def _team_meta(team_games: pd.DataFrame) -> dict[int, str]:
    """Map ``team_id -> team_abbrev`` from the team-games table."""
    pairs = team_games[["team_id", "team_abbrev"]].drop_duplicates()
    return {int(rec["team_id"]): str(rec["team_abbrev"]) for rec in pairs.to_dict("records")}


def _build_team_rows(
    round_series: pd.DataFrame,
    matchups: dict[tuple[int, int, int], Any],
    win_model: Any,
    shutout_model: Any,
    season: int,
    playoff_round: int,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[int, float]]]:
    """Predict each round matchup; return team rows + per-team length distributions."""
    team_rows: list[dict[str, Any]] = []
    length_by_abbrev: dict[str, dict[int, float]] = {}

    for row in round_series.to_dict("records"):
        top_id_raw = row["top_seed_team_id"]
        bottom_id_raw = row["bottom_seed_team_id"]
        if pd.isna(top_id_raw) or pd.isna(bottom_id_raw):
            warnings.append(f"series {row.get('series_abbrev')} missing a seed team id; skipped")
            continue
        top_id = int(top_id_raw)
        bottom_id = int(bottom_id_raw)
        top_abbrev = str(row["top_seed_abbrev"])
        bottom_abbrev = str(row["bottom_seed_abbrev"])

        matchup = matchups.get(_matchup_key(season, top_id, bottom_id))
        if (
            matchup is None
            or top_id not in matchup.win_snapshots
            or bottom_id not in matchup.win_snapshots
        ):
            warnings.append(
                f"no pre-series snapshot for {top_abbrev} vs {bottom_abbrev}; series skipped"
            )
            continue

        outcome, shutout_top, shutout_bottom = _predict_series(
            win_model, shutout_model, matchup, top_id, bottom_id
        )
        length_by_abbrev[top_abbrev] = dict(outcome.length_probs)
        length_by_abbrev[bottom_abbrev] = dict(outcome.length_probs)

        team_rows.append(
            {
                "team_id": top_id,
                "team_abbrev": top_abbrev,
                "opponent_abbrev": bottom_abbrev,
                "is_top_seed": True,
                "playoff_round": playoff_round,
                "p_series_win": outcome.p_a_win_series,
                "e_wins": outcome.e_wins_a,
                "e_games": outcome.e_games,
                "e_goalie_points": outcome.e_goalie_points_a,
                "e_shutout_wins": outcome.e_wins_a * float(shutout_top),
            }
        )
        team_rows.append(
            {
                "team_id": bottom_id,
                "team_abbrev": bottom_abbrev,
                "opponent_abbrev": top_abbrev,
                "is_top_seed": False,
                "playoff_round": playoff_round,
                "p_series_win": outcome.p_b_win_series,
                "e_wins": outcome.e_wins_b,
                "e_games": outcome.e_games,
                "e_goalie_points": outcome.e_goalie_points_b,
                "e_shutout_wins": outcome.e_wins_b * float(shutout_bottom),
            }
        )

    return team_rows, length_by_abbrev


def _build_skater_rows(
    projected: pd.DataFrame,
    length_by_abbrev: dict[str, dict[int, float]],
    injured_ids: set[int],
    *,
    season_id: int,
    playoff_round: int,
    config: ProjectArtifactConfig,
) -> list[dict[str, Any]]:
    """Project each eligible skater's round points with a seeded Monte Carlo."""
    rows: list[dict[str, Any]] = []
    for rec in projected.to_dict("records"):
        team_abbrev = str(rec["team_abbrev"])
        length_probs = length_by_abbrev.get(team_abbrev)
        if length_probs is None:
            continue
        player_id = int(rec["player_id"])
        ppg = float(rec["projected_points_per_game"])
        projection = project_skater_round(
            ppg,
            length_probs,
            seed=_row_seed(config.seed, season_id, playoff_round, player_id),
            n_sims=config.n_sims,
            horizon=config.horizon,
        )
        rows.append(
            {
                "player_id": player_id,
                "player_name": str(rec.get("player_name", "")),
                "team_abbrev": team_abbrev,
                "position": str(rec["position"]),
                "expected_points": projection.expected_points,
                "p10": projection.p10,
                "p50": projection.p50,
                "p90": projection.p90,
                "pts_per_game": projection.pts_per_game,
                "expected_games": projection.expected_games,
                "availability_multiplier": projection.availability_multiplier,
                "injured": player_id in injured_ids,
                "low_confidence": bool(rec.get("low_confidence", False)),
                "ir_stash_ev": float("nan"),
                "ir_stash_value": float("nan"),
                "ir_verdict": "",
            }
        )
    return rows


def _fit_return_model(
    train_sk: pd.DataFrame, train_tg: pd.DataFrame, horizon: int
) -> ReturnTimeModel:
    """Fit the US-015 return-time model from pre-cutoff archive spells (leakage-free).

    The absence spells come only from games before the round start, so nothing about
    the target round leaks. A fixture too small to yield any spell falls back to a
    degenerate model whose curve is still driven by the documented status means.
    """
    spells = derive_absence_spells(train_sk, train_tg)
    if spells.empty:
        return ReturnTimeModel(
            spell_lengths=(), horizon=horizon, status_mean_games=dict(STATUS_MEAN_GAMES)
        )
    return fit_return_time_model(spells, horizon=horizon)


def _apply_ir_stash(
    skaters: pd.DataFrame,
    cheatsheet: CheatSheet,
    injuries: pd.DataFrame | None,
    length_by_abbrev: dict[str, dict[int, float]],
    train_sk: pd.DataFrame,
    train_tg: pd.DataFrame,
    config: ProjectArtifactConfig,
) -> list[StashValuation]:
    """Value injured F/D as IR stashes and fold the result into the sheet + table.

    Composes the US-015 return-time curve with each injured skater's US-016 per-game
    production and the retroactive-swap rule (US-022). Mutates ``skaters`` (fills the
    ``ir_stash_ev`` / ``ir_stash_value`` / ``ir_verdict`` columns) and attaches the
    rendered IR section to ``cheatsheet``; returns the valuations for the manifest.
    """
    if not config.ir or skaters.empty:
        return []
    injured = skaters.loc[skaters["injured"] & skaters["position"].isin(("F", "D"))]
    if injured.empty:
        return []

    status_by_id: dict[int, str] = {}
    if injuries is not None and not injuries.empty:
        for rec in injuries.to_dict("records"):
            pid = rec.get("player_id")
            if pid is not None and pd.notna(pid):
                status_by_id[int(pid)] = str(rec.get("status") or "out")

    model = _fit_return_model(train_sk, train_tg, config.horizon)
    inputs: list[StashInput] = []
    for rec in injured.to_dict("records"):
        team_abbrev = str(rec["team_abbrev"])
        length_probs = length_by_abbrev.get(team_abbrev)
        if length_probs is None:
            continue
        player_id = int(rec["player_id"])
        status = status_by_id.get(player_id, "out")
        curve = model.availability_curve(status)
        inputs.append(
            StashInput(
                player_id=player_id,
                player_name=str(rec.get("player_name", "")),
                position=str(rec["position"]),
                team_abbrev=team_abbrev,
                status=status,
                pts_per_game=float(rec["pts_per_game"]),
                length_probs=length_probs,
                availability_curve=curve,
                expected_games_available=float(sum(curve)),
            )
        )

    replacement_by_position = {
        "F": cheatsheet.replacement_forward,
        "D": cheatsheet.replacement_defense,
    }
    valuations = build_stash_valuations(
        inputs,
        replacement_by_position,
        seed=config.seed,
        n_sims=config.n_sims,
        horizon=config.horizon,
    )

    by_id = {val.player_id: val for val in valuations}
    for column, attr in (
        ("ir_stash_ev", "stash_ev"),
        ("ir_stash_value", "stash_value"),
    ):
        skaters[column] = skaters["player_id"].map(
            lambda pid, a=attr: getattr(by_id[int(pid)], a) if int(pid) in by_id else float("nan")
        )
    skaters["ir_verdict"] = skaters["player_id"].map(
        lambda pid: by_id[int(pid)].verdict if int(pid) in by_id else ""
    )
    cheatsheet.ir_section = render_ir_section(valuations)
    return valuations


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
    prod_config = config.production_config or SkaterProductionConfig(seed=config.seed)
    warnings: list[str] = []

    round_series = series.loc[
        (series["year"].astype(int) == int(season))
        & (series["playoff_round"].astype("Int64") == int(playoff_round))
    ]
    if round_series.empty:
        raise ValueError(
            f"no series found for season {season} round {playoff_round}; "
            "run ingest/normalize so the bracket is available"
        )
    season_id = _resolve_season_id(round_series, season)

    starts = playoff_round_starts(team_games, series)
    cutoff = starts.get(season_id, {}).get(int(playoff_round))
    if cutoff is None:
        raise ValueError(
            f"cannot derive the round-start cutoff for season {season} round {playoff_round}; "
            "the round has no games in the archive yet"
        )
    cutoff_ts = pd.Timestamp(cutoff)

    tg = team_games.copy()
    tg["game_date"] = pd.to_datetime(tg["game_date"])
    sk = skater_games.copy()
    sk["game_date"] = pd.to_datetime(sk["game_date"])
    train_tg = tg.loc[tg["game_date"] < cutoff_ts]
    train_sk = sk.loc[sk["game_date"] < cutoff_ts]
    if train_tg.empty or train_sk.empty:
        raise ValueError("no games available before the round start to train on")

    win_model = train_game_win_model(
        train_tg, odds=None, config=GameWinConfig(seed=config.seed)
    ).model
    shutout_model = train_shutout_model(train_tg, config=ShutoutConfig(seed=config.seed)).model
    prod_model = train_skater_production_model(
        train_sk, players, train_tg, series, config=prod_config
    ).model

    matchups = reconstruct_series_matchups(team_games)
    team_rows, length_by_abbrev = _build_team_rows(
        round_series, matchups, win_model, shutout_model, int(season), int(playoff_round), warnings
    )

    injured_ids = _injured_player_ids(injuries)
    feats = build_skater_features(
        skater_games,
        players,
        team_games,
        season_id=season_id,
        as_of_date=cutoff,
        playoff_round=int(playoff_round),
    )
    eligible_feats = feats.loc[feats["team_abbrev"].isin(length_by_abbrev)]
    skater_rows: list[dict[str, Any]] = []
    if not eligible_feats.empty:
        projected = prod_model.project(eligible_feats)
        skater_rows = _build_skater_rows(
            projected,
            length_by_abbrev,
            injured_ids,
            season_id=season_id,
            playoff_round=int(playoff_round),
            config=config,
        )

    skaters = _finalize_skaters(skater_rows)
    teams = _finalize_teams(team_rows)
    cheatsheet = build_cheatsheet(skaters, teams, config=config.vor_config)
    ir_valuations = _apply_ir_stash(
        skaters, cheatsheet, injuries, length_by_abbrev, train_sk, train_tg, config
    )

    manifest = {
        "artifact_version": LIVE_PROJECTION_VERSION,
        "package_version": __version__,
        "season": int(season),
        "playoff_round": int(playoff_round),
        "snapshot_id": snapshot_id,
        "as_of_cutoff": cutoff,
        "feature_version": FEATURE_SET_VERSION,
        "model_versions": {
            "game_win": GAME_WIN_MODEL_VERSION,
            "shutout": SHUTOUT_MODEL_VERSION,
            "skater_production": SKATER_PRODUCTION_VERSION,
            "series_sim": SERIES_SIM_VERSION,
            "projection": PROJECTION_VERSION,
        },
        "git_sha": git_sha if git_sha is not None else _git_sha(),
        "seeds": {"base": config.seed, "n_sims": config.n_sims, "horizon": config.horizon},
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "scarcity": cheatsheet.summary(),
        "counts": {
            "eligible_series": int(len(teams) // 2),
            "eligible_teams": len(teams),
            "skaters_projected": len(skaters),
            "skaters_injured": int(skaters["injured"].sum()) if not skaters.empty else 0,
        },
        "eligible_team_abbrevs": sorted(length_by_abbrev),
        "ir_stash": {
            "enabled": config.ir,
            "candidates": len(ir_valuations),
            "stash_verdicts": sum(1 for v in ir_valuations if v.verdict == "stash"),
        },
        "warnings": warnings,
    }

    return ProjectArtifactResult(
        season=int(season),
        playoff_round=int(playoff_round),
        as_of_cutoff=cutoff,
        skaters=skaters,
        teams=teams,
        cheatsheet=cheatsheet,
        manifest=manifest,
        warnings=warnings,
    )


def _finalize_skaters(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Deterministically ordered skater table with the fixed column layout."""
    if not rows:
        return pd.DataFrame({col: pd.Series(dtype="object") for col in SKATER_COLUMNS})
    df = pd.DataFrame(rows)[list(SKATER_COLUMNS)]
    df = df.sort_values(
        ["expected_points", "player_id"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    df["player_id"] = df["player_id"].astype("int64")
    df["injured"] = df["injured"].astype(bool)
    df["low_confidence"] = df["low_confidence"].astype(bool)
    return df


def _finalize_teams(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Deterministically ordered team table with the fixed column layout."""
    if not rows:
        return pd.DataFrame({col: pd.Series(dtype="object") for col in TEAM_COLUMNS})
    df = pd.DataFrame(rows)[list(TEAM_COLUMNS)]
    df = df.sort_values(
        ["p_series_win", "team_id"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    df["team_id"] = df["team_id"].astype("int64")
    df["playoff_round"] = df["playoff_round"].astype("int64")
    df["is_top_seed"] = df["is_top_seed"].astype(bool)
    return df


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
    (out_dir / "run_manifest.json").write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out_dir


DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_ARTIFACTS_ROOT = Path("artifacts")
SNAPSHOTS_SUBDIR = "snapshots"


def _load_tables(source_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the four normalized tables the projection needs from ``source_dir``."""
    return {
        name: pd.read_parquet(source_dir / f"{name}.parquet")
        for name in ("skater_games", "players", "team_games", "series")
    }


def _load_injuries(normalized_dir: Path) -> pd.DataFrame | None:
    """Load the current-status injuries table if it has been ingested, else ``None``."""
    path = normalized_dir / "injuries.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _snapshot_id_for(source_dir: Path, snapshot: str | None) -> str:
    """Resolve the recorded snapshot id: the pinned id, or the source signature."""
    if snapshot:
        return snapshot
    manifest_path = source_dir / "_manifest.json"
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            sources = loaded.get("sources")
            if isinstance(sources, dict):
                total = sum(int(v) for v in sources.values())
                return f"live-{len(sources)}src-{total}b"
    return "live"


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

    When ``snapshot`` is given the tables are read from
    ``normalized_dir/snapshots/<snapshot>/`` (a frozen copy); otherwise the live
    ``normalized_dir`` is used and the snapshot id is derived from its source
    signature. The artifact is written to ``artifacts_root/<season>-r<round>/``.
    """
    source_dir = normalized_dir / SNAPSHOTS_SUBDIR / snapshot if snapshot else normalized_dir
    tables = _load_tables(source_dir)
    injuries = _load_injuries(normalized_dir)
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
        config=config,
    )
    out_dir = artifacts_root / f"{season}-r{playoff_round}"
    write_projection_artifact(result, out_dir)
    return result, out_dir
