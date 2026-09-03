"""Shared synthetic backtest fixtures."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from draft_oracle.backtest.replay import BacktestConfig
from draft_oracle.models.skater_production import SkaterProductionConfig
from draft_oracle.projection_artifact import ProjectArtifactConfig

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
class _SkaterRowInput:
    player_id: int
    pos: str
    game_id: int
    game_date: str
    season_id: int
    game_type_id: int
    team: str
    opp: str
    goals: int
    assists: int


def _players() -> tuple[pd.DataFrame, dict[int, tuple[str, str, float]]]:
    players: dict[int, tuple[str, str, float]] = {}
    rows: list[dict[str, object]] = []
    pid = 100
    for team in TEAMS:
        for i in range(FORWARDS_PER_TEAM + DEFENSE_PER_TEAM):
            pos = "F" if i < FORWARDS_PER_TEAM else "D"
            rate = 0.6 + 0.05 * (STRENGTH[team]) - 0.03 * i
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


def _skater_row(spec: _SkaterRowInput) -> dict[str, object]:
    return {
        "season_id": spec.season_id,
        "game_type_id": spec.game_type_id,
        "game_id": spec.game_id,
        "game_date": spec.game_date,
        "player_id": spec.player_id,
        "player_name": f"{spec.team}-{spec.player_id}",
        "position_code": "C" if spec.pos == "F" else "D",
        "position": spec.pos,
        "shoots_catches": "L",
        "team_abbrev": spec.team,
        "opponent_team_abbrev": spec.opp,
        "home_road": "H",
        "goals": spec.goals,
        "assists": spec.assists,
        "points": spec.goals + spec.assists,
        "shots": spec.goals * 3 + 2,
        "toi_seconds": 1000,
        "pp_goals": 0,
        "pp_points": 0,
        "sh_goals": 0,
        "sh_points": 0,
        "ev_goals": spec.goals,
        "ev_points": spec.goals + spec.assists,
        "plus_minus": 0,
        "penalty_minutes": 0,
        "game_winning_goals": 0,
        "ot_goals": 0,
        "shooting_pct": 0.1,
        "faceoff_win_pct": 0.5,
    }


def _team_rows(
    game_id: int,
    game_date: str,
    season_id: int,
    game_type_id: int,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    team_ids: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    def _team_id(team: str) -> int:
        return team_ids[team] if team_ids is not None else TEAMS.index(team) + 1

    rows: list[dict[str, object]] = []
    for team, opp, gf, ga, is_home in (
        (home, away, home_goals, away_goals, True),
        (away, home, away_goals, home_goals, False),
    ):
        won = gf > ga
        rows.append(
            {
                "season_id": season_id,
                "game_type_id": game_type_id,
                "game_id": game_id,
                "game_date": game_date,
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


def _draw_ga(rng: np.random.Generator, rate: float) -> tuple[int, int]:
    return int(rng.poisson(max(rate * 0.5, 0.01))), int(rng.poisson(max(rate * 0.5, 0.01)))


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
        day, month = 1, 10
        for _ in range(reg_cycles):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    date = f"{end_year - 1}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day = 1
                        month = 11 if month == 10 else (12 if month == 11 else 10)
                    diff = STRENGTH[home] - STRENGTH[away]
                    home_win = rng.random() < 1.0 / (1.0 + np.exp(-0.5 * diff))
                    if home_win:
                        hg = int(rng.integers(2, 5))
                        ag = int(rng.integers(0, hg))
                    else:
                        ag = int(rng.integers(2, 5))
                        hg = int(rng.integers(0, ag))
                    tg_rows.extend(_team_rows(gid, date, season_id, 2, home, away, hg, ag))
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

        for letter_idx, (top, bottom) in enumerate(SERIES_PAIRS):
            for offset, (winner_side, wg, lg) in enumerate(SERIES_RESULT):
                gid += 1
                host = top if HOME_PATTERN[offset] == "top" else bottom
                visitor = bottom if host == top else top
                winner = top if winner_side == "top" else bottom
                hg, ag = (wg, lg) if winner == host else (lg, wg)
                date = f"{end_year}-04-{15 + offset:02d}"
                tg_rows.extend(_team_rows(gid, date, season_id, 3, host, visitor, hg, ag))
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

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )


def _archive_tables(
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _synthetic_archive([2017, 2018, 2019, 2020, 2021, 2022], seed=seed)


def _tables(seed: int = 1) -> dict[str, pd.DataFrame]:
    sk, tg, players, series = _archive_tables(seed)
    return {"skater_games": sk, "players": players, "team_games": tg, "series": series}


# ── Four-round fixture (M-8): a full 16-team bracket through the Cup Final ────
#
# Eight teams only reach a conference final (round 3); a genuine round-4 event and
# the combined R3_4 draft need a sixteen-team first round. The lower-indexed seed
# wins every series (SERIES_RESULT: 4-2 in six), so the survivors are deterministic:
# R1 -> T01..T08, R2 -> T01..T04, R3 (conference finals) -> T01,T02, R4 -> T01.
TEAMS16 = [f"T{i:02d}" for i in range(1, 17)]
TEAM16_ID = {t: i + 1 for i, t in enumerate(TEAMS16)}
STRENGTH16 = {t: 8.0 - 0.4 * i for i, t in enumerate(TEAMS16)}
FORWARDS16 = 6
DEFENSE16 = 4
FOUR_ROUND_YEARS = [2019, 2020, 2021, 2022]
FOUR_ROUND_TARGET = 2022

# Bracket pairings per round; first-named (lower seed index) wins each series.
ROUND_PAIRS: dict[int, list[tuple[str, str]]] = {
    1: [(TEAMS16[i], TEAMS16[15 - i]) for i in range(8)],
    2: [(TEAMS16[i], TEAMS16[7 - i]) for i in range(4)],
    3: [(TEAMS16[0], TEAMS16[3]), (TEAMS16[1], TEAMS16[2])],
    4: [(TEAMS16[0], TEAMS16[1])],
}
# Six strictly increasing game dates per round (round N is played after round N-1).
ROUND_DATES: dict[int, list[str]] = {
    1: [f"-04-{15 + o:02d}" for o in range(6)],
    2: [f"-04-{24 + o:02d}" for o in range(6)],
    3: [f"-05-{5 + o:02d}" for o in range(6)],
    4: [f"-05-{15 + o:02d}" for o in range(6)],
}


def _players16() -> tuple[pd.DataFrame, dict[int, tuple[str, str, float]]]:
    players: dict[int, tuple[str, str, float]] = {}
    rows: list[dict[str, object]] = []
    pid = 1000
    for team in TEAMS16:
        for i in range(FORWARDS16 + DEFENSE16):
            pos = "F" if i < FORWARDS16 else "D"
            rate = 0.6 + 0.05 * STRENGTH16[team] - 0.03 * i
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
                        _team_rows(gid, date, season_id, 2, home, away, hg, ag, team_ids=TEAM16_ID)
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
                            gid, date, season_id, 3, host, visitor, hg, ag, team_ids=TEAM16_ID
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


def _four_round_tables() -> dict[str, pd.DataFrame]:
    sk, tg, players, series = _four_round_archive()
    return {"skater_games": sk, "players": players, "team_games": tg, "series": series}


def _four_round_config() -> BacktestConfig:
    # Smaller sims/rollouts than _config: this fixture replays three events across a
    # sixteen-team archive, and the assertions are structural, not statistical.
    project = ProjectArtifactConfig(
        seed=20260827,
        n_sims=60,
        slot_strategies=False,
        production_config=SkaterProductionConfig(
            seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
        ),
    )
    return BacktestConfig(
        seed=20260827,
        managers=4,
        n_drafts=1,
        rollouts=4,
        max_candidates=5,
        strategies=("oracle",),
        project_config=project,
    )
