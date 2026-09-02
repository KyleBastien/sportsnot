"""Playoff round reconstruction helpers for skater production models."""

from __future__ import annotations

import pandas as pd

PLAYOFF_GAME_TYPE = 3
REGULAR_SEASON_GAME_TYPE = 2
QUALIFYING_ROUND_GAME_DIGIT = "0"
LABEL_COLUMN = "actual_points_per_game"


def _pair_key(team_a: object, team_b: object) -> tuple[str, str]:
    """Order-independent key for the two teams in a series/game."""
    a, b = str(team_a), str(team_b)
    return (a, b) if a <= b else (b, a)


def _playoff_round_digit(game_id: object) -> str | None:
    """The round digit of a 10-char NHL playoff game id, or ``None`` if unparseable.

    NHL playoff game ids are ``SSSS03RMGG`` where the 8th character (index 7) is the
    round: ``1``-``4`` for the four best-of-seven rounds. The 2019-20 bubble's
    qualifying round *and* seeding round-robin both carry digit ``0`` and must never
    be attributed to a best-of-seven series — their team pairs collide with real
    later-round matchups (e.g. a round-robin game between two teams that also meet in
    round 2), which the team-pair round map would otherwise mislabel (CODE_REVIEW
    m-6).
    """
    text = str(game_id).strip()
    if len(text) != 10 or not text.isdigit():
        return None
    return text[7]


def _series_round_map(series: pd.DataFrame) -> dict[tuple[int, tuple[str, str]], int]:
    """Map ``(season_id, {team_a, team_b}) -> playoff_round`` from the series table."""
    out: dict[tuple[int, tuple[str, str]], int] = {}
    cols = ["season_id", "top_seed_abbrev", "bottom_seed_abbrev", "playoff_round"]
    for rec in series[cols].to_dict("records"):
        key = (int(rec["season_id"]), _pair_key(rec["top_seed_abbrev"], rec["bottom_seed_abbrev"]))
        out[key] = int(rec["playoff_round"])
    return out


def _assign_rounds(
    games: pd.DataFrame, round_map: dict[tuple[int, tuple[str, str]], int]
) -> list[int | None]:
    """Look up each playoff game's round via its (season, team-pair); ``None`` if unknown.

    A 2019-20 qualifying-round / round-robin game (``game_id`` round digit ``0``) is
    always ``None`` regardless of the team-pair map, so a round-robin game whose two
    teams also meet in a real later series is never mislabeled as that series' round
    (CODE_REVIEW m-6).
    """
    has_game_id = "game_id" in games.columns
    read_cols = ["season_id", "team_abbrev", "opponent_team_abbrev"]
    if has_game_id:
        read_cols = ["game_id", *read_cols]
    result: list[int | None] = []
    for rec in games[read_cols].to_dict("records"):
        if has_game_id and _playoff_round_digit(rec["game_id"]) == QUALIFYING_ROUND_GAME_DIGIT:
            result.append(None)
            continue
        key = (int(rec["season_id"]), _pair_key(rec["team_abbrev"], rec["opponent_team_abbrev"]))
        result.append(round_map.get(key))
    return result


def playoff_round_starts(
    team_games: pd.DataFrame, series: pd.DataFrame
) -> dict[int, dict[int, str]]:
    """Earliest game date of each playoff round, per season.

    Returns ``{season_id: {playoff_round: "YYYY-MM-DD"}}``. The start date is the
    exclusive as-of cutoff for that round's features. Games whose team pair matches
    no series row (e.g. the 2019-20 bubble round-robin) are ignored.
    """
    po = team_games.loc[team_games["game_type_id"] == PLAYOFF_GAME_TYPE].copy()
    if po.empty:
        return {}
    po["game_date"] = pd.to_datetime(po["game_date"])
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.dropna(subset=["playoff_round"])
    grouped = po.groupby(["season_id", "playoff_round"])["game_date"].min().reset_index()
    starts: dict[int, dict[int, str]] = {}
    for rec in grouped.to_dict("records"):
        season = int(rec["season_id"])
        rnd = int(rec["playoff_round"])
        starts.setdefault(season, {})[rnd] = pd.Timestamp(rec["game_date"]).strftime("%Y-%m-%d")
    return starts


def playoff_round_cutoffs(
    team_games: pd.DataFrame, series: pd.DataFrame
) -> dict[int, dict[int, str]]:
    """As-of cutoffs per round, extended with a *pre-round* cutoff for the next round.

    Returns ``{season_id: {playoff_round: "YYYY-MM-DD"}}`` like
    :func:`playoff_round_starts`, but so a genuinely pre-round artifact can be built
    (CODE_REVIEW M-1): the round drafts *before* it starts, so its own first game does
    not exist yet. For every season the round *after* the latest played playoff round
    gets a cutoff of the day AFTER that round's final game -- the previous round's
    completion / bracket-announcement boundary. When no playoff games exist yet, round
    1 gets the day after the regular season's final game.

    Rounds that have already been played keep their own first-game cutoff untouched,
    so backtests over complete seasons are byte-for-byte identical: the only added
    entries are for rounds with no games in the archive.
    """
    starts = playoff_round_starts(team_games, series)
    tg = team_games.copy()
    tg["game_date"] = pd.to_datetime(tg["game_date"])

    for _, group in tg.groupby("season_id"):
        season_id = int(group["season_id"].iloc[0])
        played = starts.setdefault(season_id, {})
        _extend_round_cutoffs(played, group)
    return starts


def _extend_round_cutoffs(played: dict[int, str], games: pd.DataFrame) -> None:
    if played:
        _extend_next_round_cutoff(played, games)
    else:
        _extend_opening_round_cutoff(played, games)


def _extend_next_round_cutoff(played: dict[int, str], games: pd.DataFrame) -> None:
    po = games.loc[games["game_type_id"] == PLAYOFF_GAME_TYPE]
    if po.empty:
        return
    played.setdefault(max(played) + 1, _next_day(po["game_date"].max()))


def _extend_opening_round_cutoff(played: dict[int, str], games: pd.DataFrame) -> None:
    reg = games.loc[games["game_type_id"] == REGULAR_SEASON_GAME_TYPE]
    if reg.empty:
        return
    played.setdefault(1, _next_day(reg["game_date"].max()))


def _next_day(value: pd.Timestamp) -> str:
    return (pd.Timestamp(value) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def skater_round_production(skater_games: pd.DataFrame, series: pd.DataFrame) -> pd.DataFrame:
    """Observed goals+assists per game for each skater in each playoff round.

    One row per ``(season_id, playoff_round, player_id)`` with the round's goals,
    assists, games, and ``actual_points_per_game = (G + A) / GP``. This is the label
    the model learns; it uses only that round's playoff games.
    """
    po = skater_games.loc[skater_games["game_type_id"] == PLAYOFF_GAME_TYPE].copy()
    if po.empty:
        return pd.DataFrame(
            columns=[
                "season_id",
                "playoff_round",
                "player_id",
                "round_goals",
                "round_assists",
                "round_games",
                LABEL_COLUMN,
            ]
        )
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.dropna(subset=["playoff_round"])
    grouped = po.groupby(["season_id", "playoff_round", "player_id"], as_index=False).agg(
        round_goals=("goals", "sum"),
        round_assists=("assists", "sum"),
        round_games=("game_id", "nunique"),
    )
    grouped["playoff_round"] = grouped["playoff_round"].astype(int)
    grouped[LABEL_COLUMN] = [
        (g + a) / n if n else 0.0
        for g, a, n in zip(
            grouped["round_goals"],
            grouped["round_assists"],
            grouped["round_games"],
            strict=True,
        )
    ]
    return grouped
