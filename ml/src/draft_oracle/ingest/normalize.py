"""Normalize raw NHL responses into documented Parquet tables (US-004).

Raw sources — the committed historical archive under ``data/raw/nhl-archive/``
(seasons 2015-16 … 2025-26, see its ``PROVENANCE.md``) and, for the current
season or gaps, the live :class:`~draft_oracle.ingest.nhl_api.NHLApiClient` — are
folded into five normalized tables written as Parquet under ``data/normalized/``:

``skater_games``  one row per skater-game (goalies excluded)
``team_games``    one row per team-game (with a derived ``team_abbrev``)
``series``        one row per playoff series (from the committed brackets)
``players``       one row per skater (bios dimension, goalies excluded)
``teams``         one row per team (id ↔ abbrev ↔ full name)

Schemas are documented in ``ml/README.md``. Position codes collapse per SPEC §1:
the NHL centre/wing codes ``C``/``L``/``R`` map to ``F``, ``D`` stays ``D``, and
goaltenders (``G``) are excluded from the skater pool entirely.

Ingestion is idempotent and incremental: a manifest records the size of every
source file consumed, so a re-run with unchanged sources is a no-op. Row-level
dedup on the natural keys means re-processing the same data never duplicates
rows. A snapshot command freezes a dated copy of the normalized tables so that
downstream stages can pin a reproducible ``snapshot_id`` (SPEC §3, §6).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from draft_oracle.ingest.nhl_api import PlayoffBracket

# ── Directory contract (SPEC §4) ─────────────────────────────────────────

DEFAULT_ARCHIVE_DIR = Path("data/raw/nhl-archive")
DEFAULT_NORMALIZED_DIR = Path("data/normalized")
SNAPSHOTS_SUBDIR = "snapshots"
MANIFEST_NAME = "_manifest.json"

# The five normalized tables, in dependency order.
TABLE_NAMES = ("skater_games", "team_games", "series", "players", "teams")

# Optional tables that pinned downstream runs consume (fitted-opponent league
# picks, market odds, injuries). Frozen into a snapshot when present so that a
# pin is self-contained (M-10). A consumer that finds one recorded ``"absent"``
# in the snapshot manifest knows that is the frozen truth at snapshot time, not
# a silent live read.
OPTIONAL_TABLE_NAMES = ("league_draft_picks", "odds", "injuries")

# ── Position mapping (SPEC §1) ───────────────────────────────────────────

_POSITION_MAP: dict[str, str] = {"C": "F", "L": "F", "R": "F", "D": "D"}


def map_position(code: str | None) -> str | None:
    """Collapse an NHL position code to the fantasy pool position.

    ``C``/``L``/``R`` → ``F``; ``D`` → ``D``; goalies (``G``) and anything
    unrecognized → ``None`` (excluded from the skater pool).
    """
    if code is None:
        return None
    return _POSITION_MAP.get(code.strip().upper())


# ── Column contracts ─────────────────────────────────────────────────────

_SKATER_RENAME: dict[str, str] = {
    "seasonId": "season_id",
    "gameTypeId": "game_type_id",
    "gameId": "game_id",
    "gameDate": "game_date",
    "playerId": "player_id",
    "skaterFullName": "player_name",
    "positionCode": "position_code",
    "shootsCatches": "shoots_catches",
    "teamAbbrev": "team_abbrev",
    "opponentTeamAbbrev": "opponent_team_abbrev",
    "homeRoad": "home_road",
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "shots": "shots",
    "timeOnIcePerGame": "toi_seconds",
    "ppGoals": "pp_goals",
    "ppPoints": "pp_points",
    "shGoals": "sh_goals",
    "shPoints": "sh_points",
    "evGoals": "ev_goals",
    "evPoints": "ev_points",
    "plusMinus": "plus_minus",
    "penaltyMinutes": "penalty_minutes",
    "gameWinningGoals": "game_winning_goals",
    "otGoals": "ot_goals",
    "shootingPct": "shooting_pct",
    "faceoffWinPct": "faceoff_win_pct",
}

_SKATER_COLUMNS: tuple[str, ...] = (
    "season_id",
    "game_type_id",
    "game_id",
    "game_date",
    "player_id",
    "player_name",
    "position_code",
    "position",
    "shoots_catches",
    "team_abbrev",
    "opponent_team_abbrev",
    "home_road",
    "goals",
    "assists",
    "points",
    "shots",
    "toi_seconds",
    "pp_goals",
    "pp_points",
    "sh_goals",
    "sh_points",
    "ev_goals",
    "ev_points",
    "plus_minus",
    "penalty_minutes",
    "game_winning_goals",
    "ot_goals",
    "shooting_pct",
    "faceoff_win_pct",
)

_TEAM_RENAME: dict[str, str] = {
    "seasonId": "season_id",
    "gameTypeId": "game_type_id",
    "gameId": "game_id",
    "gameDate": "game_date",
    "teamId": "team_id",
    "teamFullName": "team_full_name",
    "opponentTeamAbbrev": "opponent_team_abbrev",
    "homeRoad": "home_road",
    "goalsFor": "goals_for",
    "goalsAgainst": "goals_against",
    "wins": "wins",
    "losses": "losses",
    "otLosses": "ot_losses",
    "regulationAndOtWins": "regulation_and_ot_wins",
    "winsInRegulation": "wins_in_regulation",
    "winsInShootout": "wins_in_shootout",
    "points": "points",
    "shotsForPerGame": "shots_for",
    "shotsAgainstPerGame": "shots_against",
    "faceoffWinPct": "faceoff_win_pct",
    "powerPlayPct": "power_play_pct",
    "powerPlayNetPct": "power_play_net_pct",
    "penaltyKillPct": "penalty_kill_pct",
    "penaltyKillNetPct": "penalty_kill_net_pct",
    "teamShutouts": "team_shutouts",
}

_TEAM_COLUMNS: tuple[str, ...] = (
    "season_id",
    "game_type_id",
    "game_id",
    "game_date",
    "team_id",
    "team_abbrev",
    "team_full_name",
    "opponent_team_abbrev",
    "home_road",
    "goals_for",
    "goals_against",
    "wins",
    "losses",
    "ot_losses",
    "regulation_and_ot_wins",
    "wins_in_regulation",
    "wins_in_shootout",
    "points",
    "shots_for",
    "shots_against",
    "faceoff_win_pct",
    "power_play_pct",
    "power_play_net_pct",
    "penalty_kill_pct",
    "penalty_kill_net_pct",
    "team_shutouts",
    "win",
    "shutout_win",
)

_BIOS_RENAME: dict[str, str] = {
    "seasonId": "season_id",
    "playerId": "player_id",
    "skaterFullName": "player_name",
    "lastName": "last_name",
    "birthDate": "birth_date",
    "positionCode": "position_code",
    "shootsCatches": "shoots_catches",
    "height": "height",
    "weight": "weight",
    "birthCountryCode": "birth_country_code",
    "nationalityCode": "nationality_code",
    "draftYear": "draft_year",
    "draftRound": "draft_round",
    "draftOverall": "draft_overall",
    "currentTeamAbbrev": "current_team_abbrev",
}

_PLAYERS_COLUMNS: tuple[str, ...] = (
    "player_id",
    "player_name",
    "last_name",
    "birth_date",
    "position_code",
    "position",
    "shoots_catches",
    "height",
    "weight",
    "birth_country_code",
    "nationality_code",
    "draft_year",
    "draft_round",
    "draft_overall",
    "current_team_abbrev",
    "last_season_id",
)

_SERIES_COLUMNS: tuple[str, ...] = (
    "year",
    "season_id",
    "series_letter",
    "series_abbrev",
    "playoff_round",
    "top_seed_team_id",
    "top_seed_abbrev",
    "top_seed_wins",
    "bottom_seed_team_id",
    "bottom_seed_abbrev",
    "bottom_seed_wins",
    "winning_team_id",
    "losing_team_id",
)

_TEAMS_COLUMNS: tuple[str, ...] = ("team_id", "team_abbrev", "team_full_name")

_SEASON_LABEL_RE = re.compile(r"(\d{4})-(\d{2})")


# ── Season-label helpers ─────────────────────────────────────────────────


def season_id_from_label(label: str) -> int:
    """``"2015-16"`` → ``20152016`` (the NHL 8-digit ``seasonId``)."""
    match = _SEASON_LABEL_RE.fullmatch(label)
    if match is None:
        raise ValueError(f"Unrecognized season label: {label!r}")
    start = int(match.group(1))
    return start * 10000 + (start + 1)


def bracket_year_from_label(label: str) -> int:
    """``"2015-16"`` → ``2016`` (the season's ending year, used for brackets)."""
    match = _SEASON_LABEL_RE.fullmatch(label)
    if match is None:
        raise ValueError(f"Unrecognized season label: {label!r}")
    return int(match.group(1)) + 1


def season_id_from_year(year: int) -> int:
    """Ending ``year`` → ``seasonId`` (e.g. ``2026`` → ``20252026``)."""
    return (year - 1) * 10000 + year


def discover_season_labels(archive_dir: Path) -> list[str]:
    """Season labels present in the archive, sorted ascending."""
    labels: set[str] = set()
    for path in archive_dir.glob("skater-games-*.csv.gz"):
        match = _SEASON_LABEL_RE.search(path.name)
        if match is not None:
            labels.add(match.group(0))
    return sorted(labels)


# ── Per-table normalizers (pure, DataFrame-in / DataFrame-out) ───────────


def normalize_skater_games(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw ``skater/summary`` rows; drop goalies, dedup by game+player."""
    df = raw.rename(columns=_SKATER_RENAME).copy()
    df["position"] = df["position_code"].map(map_position)
    df = df[df["position"].notna()]
    df = _ensure_columns(df, _SKATER_COLUMNS)
    df = df.drop_duplicates(subset=["game_id", "player_id"], keep="first")
    df = df.sort_values(["season_id", "game_id", "player_id"], kind="stable")
    return df.reset_index(drop=True)


def build_team_abbrev_map(raw: pd.DataFrame) -> dict[int, str]:
    """Derive ``teamId → abbrev`` from the team-vs-team ``opponentTeamAbbrev``.

    ``team_games`` names its own team by id but the opponent by abbreviation
    (PROVENANCE §2). Within a game the two rows are mirror images, so a team's
    abbreviation is the *other* row's ``opponentTeamAbbrev``.
    """
    cols = raw[["gameId", "teamId", "opponentTeamAbbrev"]]
    merged = cols.merge(cols, on="gameId", suffixes=("", "_opp"))
    merged = merged[merged["teamId"] != merged["teamId_opp"]]
    pairs = merged[["teamId", "opponentTeamAbbrev_opp"]].dropna().drop_duplicates()
    return {int(tid): str(abbr) for tid, abbr in pairs.itertuples(index=False)}


def normalize_team_games(
    raw: pd.DataFrame, abbrev_map: Mapping[int, str] | None = None
) -> pd.DataFrame:
    """Normalize raw ``team/summary`` rows; attach ``team_abbrev`` + result flags."""
    resolved = dict(abbrev_map) if abbrev_map is not None else build_team_abbrev_map(raw)
    df = raw.rename(columns=_TEAM_RENAME).copy()
    df["team_abbrev"] = df["team_id"].map(resolved)
    df["win"] = df["wins"].fillna(0).astype(int) == 1
    df["shutout_win"] = df["win"] & (df["goals_against"].fillna(-1).astype(int) == 0)
    df = _ensure_columns(df, _TEAM_COLUMNS)
    df = df.drop_duplicates(subset=["game_id", "team_id"], keep="first")
    df = df.sort_values(["season_id", "game_id", "team_id"], kind="stable")
    return df.reset_index(drop=True)


def normalize_players(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw ``skater/bios`` rows into a per-player dimension.

    Goalies are excluded and each player keeps the row from their most recent
    season (latest ``current_team_abbrev``); dedup makes re-runs stable.
    """
    df = raw.rename(columns=_BIOS_RENAME).copy()
    df["position"] = df["position_code"].map(map_position)
    df = df[df["position"].notna()]
    df["last_season_id"] = df["season_id"]
    df = df.sort_values(["player_id", "last_season_id"], kind="stable")
    df = df.drop_duplicates(subset=["player_id"], keep="last")
    df = _ensure_columns(df, _PLAYERS_COLUMNS)
    df = df.sort_values(["player_id"], kind="stable")
    return df.reset_index(drop=True)


def normalize_teams(team_games: pd.DataFrame) -> pd.DataFrame:
    """Build the ``teams`` dimension from normalized ``team_games``."""
    cols = ["team_id", "team_abbrev", "team_full_name", "season_id"]
    df = team_games[cols].copy()
    df = df.sort_values(["team_id", "season_id"], kind="stable")
    df = df.drop_duplicates(subset=["team_id"], keep="last")
    df = _ensure_columns(df, _TEAMS_COLUMNS)
    df = df.sort_values(["team_id"], kind="stable")
    return df.reset_index(drop=True)


def normalize_series(bracket: PlayoffBracket, year: int) -> pd.DataFrame:
    """Flatten a parsed :class:`PlayoffBracket` into one row per series."""
    season_id = season_id_from_year(year)
    records: list[dict[str, object]] = []
    for series in bracket.series:
        top = series.top_seed_team
        bottom = series.bottom_seed_team
        records.append(
            {
                "year": year,
                "season_id": season_id,
                "series_letter": series.series_letter,
                "series_abbrev": series.series_abbrev,
                "playoff_round": series.playoff_round,
                "top_seed_team_id": top.id if top is not None else None,
                "top_seed_abbrev": top.abbrev if top is not None else None,
                "top_seed_wins": series.top_seed_wins,
                "bottom_seed_team_id": bottom.id if bottom is not None else None,
                "bottom_seed_abbrev": bottom.abbrev if bottom is not None else None,
                "bottom_seed_wins": series.bottom_seed_wins,
                "winning_team_id": series.winning_team_id,
                "losing_team_id": series.losing_team_id,
            }
        )
    df = pd.DataFrame.from_records(records, columns=list(_SERIES_COLUMNS))
    df = df.drop_duplicates(subset=["year", "series_letter"], keep="first")
    df = df.sort_values(["year", "series_letter"], kind="stable")
    return df.reset_index(drop=True)


def _ensure_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Select ``columns`` in order, adding any missing ones as null."""
    ordered = list(columns)
    out = df.copy()
    for column in ordered:
        if column not in out.columns:
            out[column] = pd.NA
    return out[ordered]


# ── Archive loaders ──────────────────────────────────────────────────────


def _read_csv_gz(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, compression="gzip")


def load_archive_skater_games(archive_dir: Path, labels: Iterable[str]) -> pd.DataFrame:
    frames = [_read_csv_gz(archive_dir / f"skater-games-{label}.csv.gz") for label in labels]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_archive_team_games(archive_dir: Path, labels: Iterable[str]) -> pd.DataFrame:
    frames = [_read_csv_gz(archive_dir / f"team-games-{label}.csv.gz") for label in labels]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_archive_bios(archive_dir: Path, labels: Iterable[str]) -> pd.DataFrame:
    frames = [_read_csv_gz(archive_dir / f"skater-bios-{label}.csv.gz") for label in labels]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_archive_series(archive_dir: Path, labels: Iterable[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for label in labels:
        year = bracket_year_from_label(label)
        path = archive_dir / f"bracket-{year}.json"
        if not path.exists():
            continue
        bracket = PlayoffBracket.model_validate_json(path.read_text(encoding="utf-8"))
        frames.append(normalize_series(bracket, year))
    if not frames:
        return pd.DataFrame(columns=list(_SERIES_COLUMNS))
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["year", "series_letter"], kind="stable")
    return out.reset_index(drop=True)


# ── Manifest / incremental machinery ─────────────────────────────────────


def _source_signature(archive_dir: Path, labels: Iterable[str]) -> dict[str, int]:
    """Map of relevant source filename → byte size (change detection)."""
    signature: dict[str, int] = {}
    for label in labels:
        signature.update(_label_source_signature(archive_dir, label))
    return signature


def _label_source_signature(archive_dir: Path, label: str) -> dict[str, int]:
    candidates = [
        f"skater-games-{label}.csv.gz",
        f"team-games-{label}.csv.gz",
        f"skater-bios-{label}.csv.gz",
        f"bracket-{bracket_year_from_label(label)}.json",
    ]
    return {
        name: (archive_dir / name).stat().st_size
        for name in candidates
        if (archive_dir / name).exists()
    }


def _read_manifest(out_dir: Path) -> dict[str, object] | None:
    path = out_dir / MANIFEST_NAME
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def _tables_present(out_dir: Path) -> bool:
    return all((out_dir / f"{name}.parquet").exists() for name in TABLE_NAMES)


# ── Result types ─────────────────────────────────────────────────────────


@dataclass
class NormalizeResult:
    """Outcome of :func:`normalize_archive`."""

    out_dir: Path
    seasons: list[str]
    row_counts: dict[str, int]
    skipped: bool = False


@dataclass
class SnapshotResult:
    """Outcome of :func:`create_snapshot`."""

    snapshot_id: str
    path: Path
    row_counts: dict[str, int] = field(default_factory=dict)


# ── Top-level ingestion ──────────────────────────────────────────────────


def build_tables(archive_dir: Path, labels: list[str]) -> dict[str, pd.DataFrame]:
    """Build all five normalized tables in memory from the archive."""
    raw_skaters = load_archive_skater_games(archive_dir, labels)
    raw_teams = load_archive_team_games(archive_dir, labels)
    raw_bios = load_archive_bios(archive_dir, labels)

    team_games = normalize_team_games(raw_teams)
    return {
        "skater_games": normalize_skater_games(raw_skaters),
        "team_games": team_games,
        "series": load_archive_series(archive_dir, labels),
        "players": normalize_players(raw_bios),
        "teams": normalize_teams(team_games),
    }


def normalize_archive(
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    out_dir: Path = DEFAULT_NORMALIZED_DIR,
    seasons: Iterable[str] | None = None,
    *,
    force: bool = False,
) -> NormalizeResult:
    """Normalize the committed archive into Parquet tables under ``out_dir``.

    Idempotent and incremental: if the source signature is unchanged from the
    recorded manifest and all tables exist, the write is skipped unless
    ``force`` is set. The live NHL API is reserved for the current season and
    gaps (US-011+); the committed archive already covers 2015-16 … 2025-26.
    """
    if not archive_dir.exists():
        raise FileNotFoundError(f"NHL archive directory not found: {archive_dir}")

    labels = _resolve_archive_labels(archive_dir, seasons)
    signature = _source_signature(archive_dir, labels)
    cached = _cached_normalize_result(out_dir, labels, signature, force)
    if cached is not None:
        return cached

    tables = build_tables(archive_dir, labels)
    out_dir.mkdir(parents=True, exist_ok=True)
    row_counts = _write_normalized_tables(tables, out_dir)
    _write_normalize_manifest(out_dir, labels, signature, row_counts)
    return NormalizeResult(out_dir=out_dir, seasons=labels, row_counts=row_counts)


def _resolve_archive_labels(archive_dir: Path, seasons: Iterable[str] | None) -> list[str]:
    labels = list(seasons) if seasons is not None else discover_season_labels(archive_dir)
    if labels:
        return labels
    raise FileNotFoundError(f"No season archives found under {archive_dir}")


def _cached_normalize_result(
    out_dir: Path, labels: list[str], signature: Mapping[str, int], force: bool
) -> NormalizeResult | None:
    if force:
        return None
    manifest = _read_manifest(out_dir)
    if manifest is None:
        return None
    if not _cached_manifest_matches(manifest, signature):
        return None
    if not _tables_present(out_dir):
        return None
    counts = manifest.get("row_counts")
    cached_counts = counts if isinstance(counts, dict) else {}
    return NormalizeResult(out_dir=out_dir, seasons=labels, row_counts=cached_counts, skipped=True)


def _cached_manifest_matches(
    manifest: Mapping[str, object], signature: Mapping[str, int]
) -> bool:
    return manifest.get("sources") == signature


def _write_normalized_tables(tables: Mapping[str, pd.DataFrame], out_dir: Path) -> dict[str, int]:
    row_counts: dict[str, int] = {}
    for name in TABLE_NAMES:
        frame = tables[name]
        frame.to_parquet(out_dir / f"{name}.parquet", index=False)
        row_counts[name] = len(frame)
    return row_counts


def _write_normalize_manifest(
    out_dir: Path,
    labels: list[str],
    signature: Mapping[str, int],
    row_counts: Mapping[str, int],
) -> None:
    manifest_out: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "seasons": labels,
        "sources": signature,
        "row_counts": row_counts,
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest_out, indent=2, sort_keys=True), encoding="utf-8"
    )


def create_snapshot(
    out_dir: Path = DEFAULT_NORMALIZED_DIR,
    snapshot_id: str | None = None,
) -> SnapshotResult:
    """Freeze a dated copy of the normalized tables under ``snapshots/<id>/``.

    ``snapshot_id`` defaults to a UTC timestamp. Downstream stages pin the id to
    train and backtest on reproducible data (SPEC §3). Every optional table a
    pinned run consumes (``league_draft_picks``, ``odds``, ``injuries``) is frozen
    when present and recorded in the snapshot manifest, so a pin is a complete,
    self-contained contract rather than a silent fallback to live tables (M-10).
    """
    if not _tables_present(out_dir):
        raise FileNotFoundError(
            f"Normalized tables missing under {out_dir}; run normalization first."
        )
    resolved_id = snapshot_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = out_dir / SNAPSHOTS_SUBDIR / resolved_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    row_counts: dict[str, int] = {}
    for name in TABLE_NAMES:
        frame = pd.read_parquet(out_dir / f"{name}.parquet")
        frame.to_parquet(snapshot_dir / f"{name}.parquet", index=False)
        row_counts[name] = len(frame)

    # Freeze every optional table a pinned run may consume so the snapshot is a
    # complete, self-contained contract (M-10). Absent tables are recorded
    # explicitly so a consumer never confuses "frozen truth: not present" with a
    # silent greedy fallback.
    optional_tables: dict[str, str] = {}
    for name in OPTIONAL_TABLE_NAMES:
        src = out_dir / f"{name}.parquet"
        if src.exists():
            frame = pd.read_parquet(src)
            frame.to_parquet(snapshot_dir / f"{name}.parquet", index=False)
            row_counts[name] = len(frame)
            optional_tables[name] = "frozen"
        else:
            optional_tables[name] = "absent"

    manifest: dict[str, object] = {
        "snapshot_id": resolved_id,
        "created_at": datetime.now(UTC).isoformat(),
        "row_counts": row_counts,
        "optional_tables": optional_tables,
        "complete": True,
    }
    (snapshot_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return SnapshotResult(snapshot_id=resolved_id, path=snapshot_dir, row_counts=row_counts)


def list_snapshots(out_dir: Path = DEFAULT_NORMALIZED_DIR) -> list[str]:
    """Snapshot ids present under ``out_dir/snapshots/``, sorted ascending."""
    root = out_dir / SNAPSHOTS_SUBDIR
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())
