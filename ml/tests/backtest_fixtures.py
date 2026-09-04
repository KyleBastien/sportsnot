"""Shared synthetic backtest fixtures."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from draft_oracle.backtest.replay import BacktestConfig
from draft_oracle.models.skater_production import SkaterProductionConfig
from draft_oracle.projection_artifact import ProjectArtifactConfig
from tests._fixture_rows import (
    SkaterRowInput as _SkaterRowInput,
)
from tests._fixture_rows import (
    draw_ga as _draw_ga,
)
from tests._fixture_rows import (
    skater_row as _skater_row,
)

TEAMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
# Round-1 bracket: four series pairing all eight teams; the first-named wins each.
SERIES_PAIRS = [("AAA", "HHH"), ("BBB", "GGG"), ("CCC", "FFF"), ("DDD", "EEE")]
STRENGTH = {t: 3.5 - i for i, t in enumerate(TEAMS)}
FORWARDS_PER_TEAM = 5
DEFENSE_PER_TEAM = 4
# Fixed best-of-7 result: winner takes it in six (games 1,2,5,6), one of them a shutout.
SERIES_RESULT = [
    ("top", 3, 0),
    ("top", 4, 2),
    ("bottom", 3, 1),
    ("bottom", 2, 1),
    ("top", 3, 2),
    ("top", 2, 1),
]
HOME_PATTERN = ["top", "top", "bottom", "bottom", "top", "top"]


@dataclass(frozen=True)
class _PlayerPoolInput:
    teams: list[str]
    strengths: dict[str, float]
    forwards: int
    defense: int
    pid_start: int


@dataclass(frozen=True)
class _TeamRowsInput:
    game_id: int
    game_date: str
    season_id: int
    game_type_id: int
    home: str
    away: str
    home_goals: int
    away_goals: int
    teams: list[str]
    team_ids: dict[str, int] | None = None


@dataclass(frozen=True)
class _ArchiveBuildRequest:
    sk_rows: list[dict[str, object]]
    tg_rows: list[dict[str, object]]
    series_rows: list[dict[str, object]]
    players: dict[int, tuple[str, str, float]]
    rng: np.random.Generator
    end_year: int
    season_id: int
    reg_cycles: int
    gid_start: int


@dataclass(frozen=True)
class _BacktestSkaterRowsRequest:
    rows: list[dict[str, object]]
    players: dict[int, tuple[str, str, float]]
    rng: np.random.Generator
    game_id: int
    game_date: str
    season_id: int
    game_type_id: int
    team: str
    opp: str


def _player_tables(
    spec: _PlayerPoolInput,
) -> tuple[pd.DataFrame, dict[int, tuple[str, str, float]]]:
    players: dict[int, tuple[str, str, float]] = {}
    rows: list[dict[str, object]] = []
    pid = spec.pid_start
    for team in spec.teams:
        for i in range(spec.forwards + spec.defense):
            pos = "F" if i < spec.forwards else "D"
            rate = 0.6 + 0.05 * spec.strengths[team] - 0.03 * i
            players[pid] = (team, pos, max(rate, 0.15))
            rows.append(
                {
                    "player_id": pid,
                    "player_name": f"{team}-{pid}",
                    "last_name": f"L{pid}",
                    "birth_date": "1996-01-01",
                    "position_code": "C" if pos == "F" else "D",
                    "position": pos,
                    "shoots_catches": "L",
                    "current_team_abbrev": team,
                }
            )
            pid += 1
    return pd.DataFrame(rows), players


def _players() -> tuple[pd.DataFrame, dict[int, tuple[str, str, float]]]:
    return _player_tables(
        _PlayerPoolInput(TEAMS, STRENGTH, FORWARDS_PER_TEAM, DEFENSE_PER_TEAM, 100)
    )


def _players16() -> tuple[pd.DataFrame, dict[int, tuple[str, str, float]]]:
    return _player_tables(_PlayerPoolInput(TEAMS16, STRENGTH16, FORWARDS16, DEFENSE16, 1000))


def _team_rows(spec: _TeamRowsInput) -> list[dict[str, object]]:
    def _team_id(team: str) -> int:
        return spec.team_ids[team] if spec.team_ids is not None else spec.teams.index(team) + 1

    rows: list[dict[str, object]] = []
    for team, opp, gf, ga, is_home in (
        (spec.home, spec.away, spec.home_goals, spec.away_goals, True),
        (spec.away, spec.home, spec.away_goals, spec.home_goals, False),
    ):
        won = gf > ga
        rows.append(
            {
                "season_id": spec.season_id,
                "game_type_id": spec.game_type_id,
                "game_id": spec.game_id,
                "game_date": spec.game_date,
                "team_id": _team_id(team),
                "team_abbrev": team,
                "team_full_name": team,
                "opponent_team_abbrev": opp,
                "home_road": "H" if is_home else "R",
                "goals_for": gf,
                "goals_against": ga,
                "wins": 1 if won else 0,
                "losses": 0 if won else 1,
                "ot_losses": 0,
                "regulation_and_ot_wins": 1 if won else 0,
                "wins_in_regulation": 1 if won else 0,
                "wins_in_shootout": 0,
                "points": 2 if won else 0,
                "shots_for": 30,
                "shots_against": 30,
                "faceoff_win_pct": 0.5,
                "power_play_pct": 0.2,
                "power_play_net_pct": 0.2,
                "penalty_kill_pct": 0.8,
                "penalty_kill_net_pct": 0.8,
                "team_shutouts": 1 if (won and ga == 0) else 0,
                "win": won,
                "shutout_win": won and ga == 0,
            }
        )
    return rows


def _append_backtest_skater_rows(
    request: _BacktestSkaterRowsRequest,
) -> None:
    for player_id, (player_team, pos, rate) in request.players.items():
        if player_team != request.team:
            continue
        goals, assists = _draw_ga(request.rng, rate)
        request.rows.append(
            _skater_row(
                _SkaterRowInput(
                    player_id,
                    pos,
                    request.game_id,
                    request.game_date,
                    request.season_id,
                    request.game_type_id,
                    request.team,
                    request.opp,
                    goals,
                    assists,
                )
            )
        )


def _emit_regular_season_games(request: _ArchiveBuildRequest) -> int:
    gid = request.gid_start
    day, month = 1, 10
    for _ in range(request.reg_cycles):
        for i, home in enumerate(TEAMS):
            for away in TEAMS[i + 1 :]:
                gid += 1
                date = f"{request.end_year - 1}-{month:02d}-{day:02d}"
                day += 1
                if day > 27:
                    day = 1
                    month = 11 if month == 10 else (12 if month == 11 else 10)
                diff = STRENGTH[home] - STRENGTH[away]
                home_win = request.rng.random() < 1.0 / (1.0 + np.exp(-0.5 * diff))
                if home_win:
                    home_goals = int(request.rng.integers(2, 5))
                    away_goals = int(request.rng.integers(0, home_goals))
                else:
                    away_goals = int(request.rng.integers(2, 5))
                    home_goals = int(request.rng.integers(0, away_goals))
                request.tg_rows.extend(
                    _team_rows(
                        _TeamRowsInput(
                            gid,
                            date,
                            request.season_id,
                            2,
                            home,
                            away,
                            home_goals,
                            away_goals,
                            TEAMS,
                        )
                    )
                )
                for team, opp in ((home, away), (away, home)):
                    _append_backtest_skater_rows(
                        _BacktestSkaterRowsRequest(
                            rows=request.sk_rows,
                            players=request.players,
                            rng=request.rng,
                            game_id=gid,
                            game_date=date,
                            season_id=request.season_id,
                            game_type_id=2,
                            team=team,
                            opp=opp,
                        )
                    )
    return gid


def _emit_series_games(
    request: _ArchiveBuildRequest,
    *,
    letter_idx: int,
    top: str,
    bottom: str,
) -> int:
    gid = request.gid_start
    for offset, (winner_side, wg, lg) in enumerate(SERIES_RESULT):
        gid += 1
        host = top if HOME_PATTERN[offset] == "top" else bottom
        visitor = bottom if host == top else top
        winner = top if winner_side == "top" else bottom
        hg, ag = (wg, lg) if winner == host else (lg, wg)
        date = f"{request.end_year}-04-{15 + offset:02d}"
        request.tg_rows.extend(
            _team_rows(
                _TeamRowsInput(
                    gid,
                    date,
                    request.season_id,
                    3,
                    host,
                    visitor,
                    hg,
                    ag,
                    TEAMS,
                )
            )
        )
        for team, opp in ((top, bottom), (bottom, top)):
            _append_backtest_skater_rows(
                _BacktestSkaterRowsRequest(
                    rows=request.sk_rows,
                    players=request.players,
                    rng=request.rng,
                    game_id=gid,
                    game_date=date,
                    season_id=request.season_id,
                    game_type_id=3,
                    team=team,
                    opp=opp,
                )
            )
    request.series_rows.append(
        {
            "year": request.end_year,
            "season_id": request.season_id,
            "series_letter": chr(ord("A") + letter_idx),
            "series_abbrev": f"{top}{bottom}",
            "playoff_round": 1,
            "top_seed_team_id": TEAMS.index(top) + 1,
            "top_seed_abbrev": top,
            "top_seed_wins": 4,
            "bottom_seed_team_id": TEAMS.index(bottom) + 1,
            "bottom_seed_abbrev": bottom,
            "bottom_seed_wins": 2,
            "winning_team_id": TEAMS.index(top) + 1,
            "losing_team_id": TEAMS.index(bottom) + 1,
        }
    )
    return gid


def _synthetic_archive(
    end_years: list[int], *, seed: int = 0, reg_cycles: int = 2
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons + a four-series first round for each end year."""
    rng = np.random.default_rng(seed)
    players_df, players = _players()
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 6_000_000

    for end_year in end_years:
        season_id = (end_year - 1) * 10000 + end_year
        request = _ArchiveBuildRequest(
            sk_rows=sk_rows,
            tg_rows=tg_rows,
            series_rows=series_rows,
            players=players,
            rng=rng,
            end_year=end_year,
            season_id=season_id,
            reg_cycles=reg_cycles,
            gid_start=gid,
        )
        gid = _emit_regular_season_games(request)
        request = _ArchiveBuildRequest(
            sk_rows=sk_rows,
            tg_rows=tg_rows,
            series_rows=series_rows,
            players=players,
            rng=rng,
            end_year=end_year,
            season_id=season_id,
            reg_cycles=reg_cycles,
            gid_start=gid,
        )
        for letter_idx, (top, bottom) in enumerate(SERIES_PAIRS):
            gid = _emit_series_games(
                request,
                letter_idx=letter_idx,
                top=top,
                bottom=bottom,
            )

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )


def _tables(seed: int = 1) -> dict[str, pd.DataFrame]:
    sk, tg, players, series = (
        _ARCHIVE_TABLES
        if seed == 1
        else _synthetic_archive([2017, 2018, 2019, 2020, 2021, 2022], seed=seed)
    )
    return {"skater_games": sk, "players": players, "team_games": tg, "series": series}


# ── Four-round fixture (M-8): a full 16-team bracket through the Cup Final ────
#
# Eight teams only reach a conference final (round 3); a genuine round-4 event and
# the combined R3_4 draft need a sixteen-team first round. The lower-indexed seed
# wins every series (SERIES_RESULT: 4-2 in six), so the survivors are deterministic:
# R1 -> T01..T08, R2 -> T01..T04, R3 (conference finals) -> T01,T02, R4 -> T01.


def _team_labels(count: int) -> list[str]:
    return [f"T{i:02d}" for i in range(1, count + 1)]


def _team_id_lookup(teams: list[str]) -> dict[str, int]:
    return {team: index + 1 for index, team in enumerate(teams)}


def _team_strengths(teams: list[str]) -> dict[str, float]:
    return {team: 8.0 - 0.4 * index for index, team in enumerate(teams)}


def _round_pairs(teams: list[str]) -> dict[int, list[tuple[str, str]]]:
    return {
        1: [(teams[i], teams[15 - i]) for i in range(8)],
        2: [(teams[i], teams[7 - i]) for i in range(4)],
        3: [(teams[0], teams[3]), (teams[1], teams[2])],
        4: [(teams[0], teams[1])],
    }


def _round_dates() -> dict[int, list[str]]:
    return {
        1: [f"-04-{15 + offset:02d}" for offset in range(6)],
        2: [f"-04-{24 + offset:02d}" for offset in range(6)],
        3: [f"-05-{5 + offset:02d}" for offset in range(6)],
        4: [f"-05-{15 + offset:02d}" for offset in range(6)],
    }


TEAMS16 = _team_labels(16)
TEAM16_ID = _team_id_lookup(TEAMS16)
STRENGTH16 = _team_strengths(TEAMS16)
FORWARDS16 = 6
DEFENSE16 = 4
FOUR_ROUND_YEARS = [2019, 2020, 2021, 2022]
FOUR_ROUND_TARGET = 2022

# Bracket pairings per round; first-named (lower seed index) wins each series.
ROUND_PAIRS = _round_pairs(TEAMS16)
# Six strictly increasing game dates per round (round N is played after round N-1).
ROUND_DATES = _round_dates()


def _four_round_archive(
    *, seed: int = 3, reg_cycles: int = 1
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons plus a bracket that reaches the Cup Final.

    Only :data:`FOUR_ROUND_TARGET` plays all four rounds; the earlier seasons play a
    single round (enough history to train the sub-models) so the fixture stays small.
    """
    rng = np.random.default_rng(seed)
    players_df, players = _players16()
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 7_000_000

    for end_year in FOUR_ROUND_YEARS:
        season_id = (end_year - 1) * 10000 + end_year
        day, month = 1, 10
        for _ in range(reg_cycles):
            for i, home in enumerate(TEAMS16):
                for away in TEAMS16[i + 1 :]:
                    gid += 1
                    date = f"{end_year - 1}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day = 1
                        month = 11 if month == 10 else (12 if month == 11 else 10)
                    diff = STRENGTH16[home] - STRENGTH16[away]
                    home_win = rng.random() < 1.0 / (1.0 + np.exp(-0.5 * diff))
                    if home_win:
                        hg = int(rng.integers(2, 5))
                        ag = int(rng.integers(0, hg))
                    else:
                        ag = int(rng.integers(2, 5))
                        hg = int(rng.integers(0, ag))
                    tg_rows.extend(
                        _team_rows(
                            _TeamRowsInput(
                                gid,
                                date,
                                season_id,
                                2,
                                home,
                                away,
                                hg,
                                ag,
                                TEAMS16,
                                team_ids=TEAM16_ID,
                            )
                        )
                    )
                    for team, opp in ((home, away), (away, home)):
                        for p, (t, pos, rate) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(
                                    _SkaterRowInput(
                                        p,
                                        pos,
                                        gid,
                                        date,
                                        season_id,
                                        2,
                                        team,
                                        opp,
                                        g,
                                        a,
                                    )
                                )
                            )

        rounds = [1, 2, 3, 4] if end_year == FOUR_ROUND_TARGET else [1]
        for rnd in rounds:
            pairs = ROUND_PAIRS[rnd]
            dates = ROUND_DATES[rnd]
            for letter_idx, (top, bottom) in enumerate(pairs):
                for offset, (winner_side, wg, lg) in enumerate(SERIES_RESULT):
                    gid += 1
                    host = top if HOME_PATTERN[offset] == "top" else bottom
                    visitor = bottom if host == top else top
                    winner = top if winner_side == "top" else bottom
                    hg, ag = (wg, lg) if winner == host else (lg, wg)
                    date = f"{end_year}{dates[offset]}"
                    tg_rows.extend(
                        _team_rows(
                            _TeamRowsInput(
                                gid,
                                date,
                                season_id,
                                3,
                                host,
                                visitor,
                                hg,
                                ag,
                                TEAMS16,
                                team_ids=TEAM16_ID,
                            )
                        )
                    )
                    for team, opp in ((top, bottom), (bottom, top)):
                        for p, (t, pos, rate) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(
                                    _SkaterRowInput(
                                        p,
                                        pos,
                                        gid,
                                        date,
                                        season_id,
                                        3,
                                        team,
                                        opp,
                                        g,
                                        a,
                                    )
                                )
                            )
                series_rows.append(
                    {
                        "year": end_year,
                        "season_id": season_id,
                        "series_letter": chr(ord("A") + letter_idx),
                        "series_abbrev": f"{top}{bottom}",
                        "playoff_round": rnd,
                        "top_seed_team_id": TEAM16_ID[top],
                        "top_seed_abbrev": top,
                        "top_seed_wins": 4,
                        "bottom_seed_team_id": TEAM16_ID[bottom],
                        "bottom_seed_abbrev": bottom,
                        "bottom_seed_wins": 2,
                        "winning_team_id": TEAM16_ID[top],
                        "losing_team_id": TEAM16_ID[bottom],
                    }
                )

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )


_ARCHIVE_TABLES = _synthetic_archive([2017, 2018, 2019, 2020, 2021, 2022], seed=1)
_FOUR_ROUND_ARCHIVE = _four_round_archive()
_FOUR_ROUND_TABLES = {
    "skater_games": _FOUR_ROUND_ARCHIVE[0],
    "players": _FOUR_ROUND_ARCHIVE[2],
    "team_games": _FOUR_ROUND_ARCHIVE[1],
    "series": _FOUR_ROUND_ARCHIVE[3],
}
_FOUR_ROUND_PROJECT_CONFIG = ProjectArtifactConfig(
    seed=20260827,
    n_sims=60,
    slot_strategies=False,
    production_config=SkaterProductionConfig(
        seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
    ),
)
_FOUR_ROUND_CONFIG = BacktestConfig(
    seed=20260827,
    managers=4,
    n_drafts=1,
    rollouts=4,
    max_candidates=5,
    strategies=("oracle",),
    project_config=_FOUR_ROUND_PROJECT_CONFIG,
)
def _four_round_tables_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _FOUR_ROUND_ARCHIVE
