"""Absence-spell derivation for the return-time model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

REGULAR_SEASON_GAME_TYPE = 2

_SPELL_COLUMNS: tuple[str, ...] = (
    "season_id",
    "team_abbrev",
    "player_id",
    "spell_length",
    "median_toi_seconds",
    "n_appearances",
)


@dataclass(frozen=True)
class AbsenceSpellConfig:
    """Filters that turn appearance gaps into credible injury spells."""

    min_spell: int = 2
    min_appearances: int = 20
    min_median_toi: float = 600.0
    min_team_games: int = 40


@dataclass(frozen=True)
class _TeamSeasonKey:
    season: Any
    team: Any


@dataclass(frozen=True)
class _PlayerAbsenceContext:
    key: _TeamSeasonKey
    player_id: Any
    config: AbsenceSpellConfig


def spells_from_sequence(present: list[bool], min_spell: int) -> list[int]:
    """Bookended missed-game run lengths from a team's appear/miss sequence."""
    idxs = [i for i, p in enumerate(present) if p]
    if len(idxs) < 2:
        return []
    first, last = idxs[0], idxs[-1]
    spells: list[int] = []
    run = 0
    for i in range(first + 1, last + 1):
        if present[i]:
            if run >= min_spell:
                spells.append(run)
            run = 0
        else:
            run += 1
    return spells


def _team_game_sequence(team_games: pd.DataFrame) -> list[str]:
    """Chronological ``game_id`` list for one team-season's regular-season games."""
    ordered = team_games.sort_values(["game_date", "game_id"], kind="stable")
    return [str(g) for g in ordered["game_id"]]


def _spells_for_team_player(
    game_seq: list[str],
    player_games: pd.DataFrame,
    config: AbsenceSpellConfig,
) -> tuple[int, float, list[int]] | None:
    """Absence spells for one player on one team-season, or ``None`` if filtered out."""
    appearances = {str(g) for g in player_games["game_id"]}
    n_app = len(appearances)
    if n_app < config.min_appearances:
        return None
    median_toi = float(player_games["toi_seconds"].median())
    if median_toi < config.min_median_toi:
        return None
    present = [g in appearances for g in game_seq]
    return n_app, median_toi, spells_from_sequence(present, config.min_spell)


def derive_absence_spells(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    *,
    config: AbsenceSpellConfig | None = None,
) -> pd.DataFrame:
    """Derive injury absence spells from normalized archive tables."""
    config = config or AbsenceSpellConfig()
    sg, tg = _regular_season_frames(skater_games, team_games)
    rows = _absence_spell_rows(sg, tg, config)
    return pd.DataFrame(rows, columns=list(_SPELL_COLUMNS))


def _regular_season_frames(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sg = skater_games.loc[skater_games["game_type_id"] == REGULAR_SEASON_GAME_TYPE]
    tg = team_games.loc[team_games["game_type_id"] == REGULAR_SEASON_GAME_TYPE]
    return sg, tg


def _absence_spell_rows(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    config: AbsenceSpellConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (season, team), team_grp in team_games.groupby(
        ["season_id", "team_abbrev"], sort=False
    ):
        rows.extend(
            _team_absence_spell_rows(skater_games, team_grp, _TeamSeasonKey(season, team), config)
        )
    return rows


def _team_absence_spell_rows(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    key: _TeamSeasonKey,
    config: AbsenceSpellConfig,
) -> list[dict[str, Any]]:
    game_seq = _team_game_sequence(team_games)
    if len(game_seq) < config.min_team_games:
        return []
    players = skater_games.loc[
        (skater_games["season_id"] == key.season) & (skater_games["team_abbrev"] == key.team)
    ]
    rows: list[dict[str, Any]] = []
    for player_id, player_games in players.groupby("player_id", sort=False):
        context = _PlayerAbsenceContext(key=key, player_id=player_id, config=config)
        rows.extend(_player_absence_spell_rows(game_seq, player_games, context))
    return rows


def _player_absence_spell_rows(
    game_seq: list[str],
    player_games: pd.DataFrame,
    context: _PlayerAbsenceContext,
) -> list[dict[str, Any]]:
    result = _spells_for_team_player(game_seq, player_games, context.config)
    if result is None:
        return []
    n_app, median_toi, spells = result
    return [
        {
            "season_id": int(context.key.season),
            "team_abbrev": str(context.key.team),
            "player_id": context.player_id,
            "spell_length": int(length),
            "median_toi_seconds": median_toi,
            "n_appearances": int(n_app),
        }
        for length in spells
    ]
