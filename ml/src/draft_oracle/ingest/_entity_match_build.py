"""Build league draft pick entity-match outputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from draft_oracle.ingest.odds import NHL_TEAMS

if TYPE_CHECKING:
    from draft_oracle.ingest.entity_match import (
        LeagueEntityMatchResult,
        Match,
        NameOverrides,
        PlayerIndex,
    )


@dataclass(frozen=True)
class _InputPaths:
    picks: Path
    players: Path
    teams: Path
    skater_games: Path


@dataclass(frozen=True)
class _MatchContext:
    index: PlayerIndex
    manager_aliases: Mapping[str, str]
    overrides: NameOverrides
    archive_points: Mapping[tuple[int, int, int], int]
    team_names: Mapping[int, str]


@dataclass(frozen=True)
class _ResolvedPick:
    position: str
    raw_name: str
    match: Match
    player_id: int | None
    team_id: int | None


def build_league_draft_picks(
    normalized_dir: Path,
    overrides_dir: Path,
    out_dir: Path,
) -> LeagueEntityMatchResult:
    """Match ``league_picks`` to NHL ids and write ``league_draft_picks.parquet``."""
    from draft_oracle.ingest.entity_match import (
        LeagueEntityMatchResult,
        _archive_round_points,
        _mark_duplicate_ownership,
        _picks_frame,
        _point_columns_contradict,
        _validate_override_match_counts,
        build_player_index,
        load_manager_aliases,
        load_name_overrides,
    )

    inputs = _read_inputs(_required_paths(normalized_dir))
    index = build_player_index(inputs["players"])
    manager_aliases = load_manager_aliases(overrides_dir / "manager_aliases.yaml")
    overrides = load_name_overrides(overrides_dir / "name_overrides.yaml")
    _validate_override_match_counts(inputs["league_picks"], overrides)
    archive_points = _archive_round_points(inputs["skater_games"])
    context = _MatchContext(
        index=index,
        manager_aliases=manager_aliases,
        overrides=overrides,
        archive_points=archive_points,
        team_names=_team_names(inputs["teams"]),
    )

    records = _build_records(inputs["league_picks"], context)
    frame = _picks_frame(records)
    point_mismatches = sum(_point_columns_contradict(record, archive_points) for record in records)
    duplicate_ownerships, duplicate_ownership_rows = _mark_duplicate_ownership(frame)
    matched_series, matched_values = _matched_status(frame)
    seasons = _season_reports(records, frame, matched_values)

    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_dir / "league_draft_picks.parquet", index=False)
    review_path = _write_review_report(frame, matched_series, out_dir)
    return LeagueEntityMatchResult(
        out_dir=out_dir,
        picks=frame,
        seasons=seasons,
        review_path=review_path,
        duplicate_ownerships=duplicate_ownerships,
        duplicate_ownership_rows=duplicate_ownership_rows,
        point_mismatches=point_mismatches,
    )


def _required_paths(normalized_dir: Path) -> _InputPaths:
    paths = _InputPaths(
        picks=normalized_dir / "league_picks.parquet",
        players=normalized_dir / "players.parquet",
        teams=normalized_dir / "teams.parquet",
        skater_games=normalized_dir / "skater_games.parquet",
    )
    for required in (paths.picks, paths.players, paths.teams, paths.skater_games):
        if not required.exists():
            raise FileNotFoundError(
                f"required normalized table missing: {required} "
                "(run `oracle league-drafts` and `oracle normalize` first)"
            )
    return paths


def _read_inputs(paths: _InputPaths) -> dict[str, pd.DataFrame]:
    return {
        "league_picks": pd.read_parquet(paths.picks),
        "players": pd.read_parquet(paths.players),
        "teams": pd.read_parquet(paths.teams),
        "skater_games": pd.read_parquet(paths.skater_games),
    }


def _team_names(teams: pd.DataFrame) -> dict[int, str]:
    from draft_oracle.ingest.entity_match import _as_int

    names: dict[int, str] = {
        _as_int(r.team_id): str(r.team_full_name) for r in teams.itertuples(index=False)
    }
    for team in NHL_TEAMS:
        names[team.team_id] = team.full_name
    return names


def _build_records(league_picks: pd.DataFrame, context: _MatchContext) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in league_picks.itertuples(index=False):
        records.append(_match_pick_record(row, context))
    return records


def _match_pick_record(row: Any, context: _MatchContext) -> dict[str, Any]:
    from draft_oracle.ingest.entity_match import (
        _effective_skater_name,
        _point_columns_contradict,
        match_skater,
        match_team,
        resolve_team,
    )

    position = str(row.position)
    raw_name = str(row.player_or_team_name)
    skater_name = _effective_skater_name(row)
    team_name = _row_team_name(row)
    player_id: int | None = None
    team_id: int | None = None
    if position == "G":
        match = match_team(team_name, raw_name, dict(context.team_names), context.overrides)
        team_id = match.entity_id
    else:
        match = match_skater(skater_name, position, context.index, context.overrides)
        player_id = match.entity_id
        team_id = resolve_team(team_name, None, context.overrides)

    resolved = _ResolvedPick(position, raw_name, match, player_id, team_id)
    record = _base_record(row, resolved, context)
    if _point_columns_contradict(record, dict(context.archive_points)):
        record["needs_review"] = True
    return record


def _row_team_name(row: Any) -> str | None:
    raw_team_name = getattr(row, "team_name", None)
    if raw_team_name is None or pd.isna(raw_team_name):
        return None
    return str(raw_team_name)


def _base_record(
    row: Any,
    resolved: _ResolvedPick,
    context: _MatchContext,
) -> dict[str, Any]:
    from draft_oracle.ingest.entity_match import _as_int, _to_int, resolve_manager

    return {
        "season": _as_int(row.season),
        "source": row.source,
        "league_name": row.league_name,
        "draft_event": row.draft_event,
        "manager": resolve_manager(str(row.manager), dict(context.manager_aliases)),
        "snake_slot": _to_int(row.snake_slot),
        "pick_number": _to_int(row.pick_number),
        "position": resolved.position,
        "slot_label": row.slot_label,
        "player_or_team_name": resolved.raw_name,
        "matched_name": resolved.match.matched_name,
        "player_id": resolved.player_id,
        "team_id": resolved.team_id,
        "points_for_round": _to_int(row.points_for_round),
        "points_when_drafted": _to_int(row.points_when_drafted),
        "current_total_points": _to_int(row.current_total_points),
        "status": row.status,
        "points_excluded": bool(row.points_excluded),
        "ir_activated": bool(row.ir_activated),
        "swap_partner": row.swap_partner,
        "note": row.note,
        "is_scored": bool(row.is_scored),
        "match_method": resolved.match.method,
        "match_confidence": float(resolved.match.confidence),
        "needs_review": bool(resolved.match.needs_review),
    }


def _matched_status(frame: pd.DataFrame) -> tuple[pd.Series, list[bool]]:
    from draft_oracle.ingest.entity_match import _is_matched

    frame_records = frame.to_dict("records")
    matched_values = [
        _is_matched(str(r["position"]), r["player_id"], r["team_id"]) for r in frame_records
    ]
    return pd.Series(matched_values, index=frame.index), matched_values


def _season_reports(
    records: list[dict[str, Any]], frame: pd.DataFrame, matched_values: list[bool]
) -> list[Any]:
    from draft_oracle.ingest.entity_match import SeasonMatchReport

    seasons: list[Any] = []
    for season in sorted({int(r["season"]) for r in records}):
        idx = [i for i, r in enumerate(records) if int(r["season"]) == season]
        total = len(idx)
        matched = sum(1 for i in idx if matched_values[i])
        review = sum(1 for i in idx if bool(frame.iloc[i]["needs_review"]))
        seasons.append(SeasonMatchReport(season, total, matched, review))
    return seasons


def _write_review_report(
    frame: pd.DataFrame, matched_series: pd.Series, out_dir: Path
) -> Path | None:
    review_frame = frame[frame["needs_review"] | ~matched_series]
    if review_frame.empty:
        return None
    review_path = out_dir / "league_draft_picks_review.csv"
    review_frame.to_csv(review_path, index=False)
    return review_path
