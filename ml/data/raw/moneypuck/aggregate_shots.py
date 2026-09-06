#!/usr/bin/env python3
"""Derive deterministic per-game MoneyPuck aggregates from committed shot archives."""
from __future__ import annotations

import gzip
import pathlib
import re
import sys
import zipfile

import pandas as pd

SHOT_ZIP_RE = re.compile(r'^shots_(\d{4})\.zip$')
SHOT_PART_RE = re.compile(r'^shots_(\d{4})\.part(\d+)\.csv\.gz$')
REQUIRED_COLUMNS = [
    'season',
    'game_id',
    'homeTeamCode',
    'awayTeamCode',
    'teamCode',
    'isHomeTeam',
    'shooterPlayerId',
    'shooterName',
    'goalieIdForShot',
    'goalieNameForShot',
    'goal',
    'xGoal',
    'shotWasOnGoal',
    'shotRebound',
    'shotRush',
    'shotOnEmptyNet',
    'homeEmptyNet',
    'awayEmptyNet',
    'homeSkatersOnIce',
    'awaySkatersOnIce',
    'time',
    'id',
    'isPlayoffGame',
]
FLOAT_COLUMNS = {'xGoal'}
INT_COLUMNS = {
    'goal',
    'shotWasOnGoal',
    'shotRebound',
    'shotRush',
    'shotOnEmptyNet',
    'homeEmptyNet',
    'awayEmptyNet',
    'homeSkatersOnIce',
    'awaySkatersOnIce',
    'time',
    'id',
    'wentToOT',
    'wentToShootout',
    'isPlayoffGame',
    'isHomeTeam',
}
BASE_METRICS = {
    'shots': 'shotWasOnGoal',
    'unblockedShots': 'unblockedShotAttempt',
    'xGoals': 'xGoal',
    'goals': 'goal',
    'highDangerShots': 'highDangerShot',
    'highDangerXGoals': 'highDangerXGoal',
    'reboundShots': 'shotRebound',
    'rushShots': 'shotRush',
}
TEAM_KEY_COLUMNS = [
    'season',
    'seasonId',
    'gameTypeId',
    'gameId',
    'teamCode',
    'opponentCode',
    'isHome',
]
SKATER_KEY_COLUMNS = TEAM_KEY_COLUMNS + ['playerId', 'playerName']
GOALIE_KEY_COLUMNS = TEAM_KEY_COLUMNS + ['goalieId', 'goalieName']
TEAM_COLUMN_ORDER = TEAM_KEY_COLUMNS + [
    'allShotsFor',
    'allShotsAgainst',
    'allUnblockedShotsFor',
    'allUnblockedShotsAgainst',
    'allXGoalsFor',
    'allXGoalsAgainst',
    'allGoalsFor',
    'allGoalsAgainst',
    'allHighDangerShotsFor',
    'allHighDangerShotsAgainst',
    'allHighDangerXGoalsFor',
    'allHighDangerXGoalsAgainst',
    'allReboundShotsFor',
    'allReboundShotsAgainst',
    'allRushShotsFor',
    'allRushShotsAgainst',
    'fiveOnFiveShotsFor',
    'fiveOnFiveShotsAgainst',
    'fiveOnFiveUnblockedShotsFor',
    'fiveOnFiveUnblockedShotsAgainst',
    'fiveOnFiveXGoalsFor',
    'fiveOnFiveXGoalsAgainst',
    'fiveOnFiveGoalsFor',
    'fiveOnFiveGoalsAgainst',
    'fiveOnFiveHighDangerShotsFor',
    'fiveOnFiveHighDangerShotsAgainst',
    'fiveOnFiveHighDangerXGoalsFor',
    'fiveOnFiveHighDangerXGoalsAgainst',
    'fiveOnFiveReboundShotsFor',
    'fiveOnFiveReboundShotsAgainst',
    'fiveOnFiveRushShotsFor',
    'fiveOnFiveRushShotsAgainst',
]
SKATER_COLUMN_ORDER = SKATER_KEY_COLUMNS + [
    'allShots',
    'allUnblockedShots',
    'allIXGoals',
    'allGoals',
    'allHighDangerShots',
    'allHighDangerXGoals',
    'allReboundShots',
    'allRushShots',
    'fiveOnFiveShots',
    'fiveOnFiveUnblockedShots',
    'fiveOnFiveIXGoals',
    'fiveOnFiveGoals',
    'fiveOnFiveHighDangerShots',
    'fiveOnFiveHighDangerXGoals',
    'fiveOnFiveReboundShots',
    'fiveOnFiveRushShots',
]
GOALIE_COLUMN_ORDER = GOALIE_KEY_COLUMNS + [
    'shotsFaced',
    'unblockedShotsFaced',
    'xGoalsFaced',
    'goalsAgainst',
    'gsax',
    'starter',
    'shotsFacedShare',
    'unblockedShotsFacedShare',
]


def season_label(start_year: int) -> str:
    return f'{start_year}-{str(start_year + 1)[2:]}'


def season_id(start_year: int) -> str:
    return f'{start_year}{start_year + 1}'


def shot_years(shots_dir: pathlib.Path) -> list[int]:
    years = set()
    for path in shots_dir.iterdir():
        match = SHOT_ZIP_RE.match(path.name) or SHOT_PART_RE.match(path.name)
        if match is not None:
            years.add(int(match.group(1)))
    return sorted(years)


def shot_sources(shots_dir: pathlib.Path, start_year: int) -> list[pathlib.Path]:
    zip_path = shots_dir / f'shots_{start_year}.zip'
    if zip_path.exists():
        return [zip_path]
    parts = sorted(shots_dir.glob(f'shots_{start_year}.part*.csv.gz'))
    if parts:
        return parts
    raise FileNotFoundError(f'no committed shot archive found for {start_year}')


def csv_header(path: pathlib.Path) -> list[str]:
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as zf:
            with zf.open(zf.namelist()[0]) as fh:
                return fh.readline().decode('utf-8').strip().split(',')
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        return fh.readline().strip().split(',')


def select_columns(path: pathlib.Path) -> list[str]:
    header = set(csv_header(path))
    columns = [name for name in REQUIRED_COLUMNS if name in header]
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        raise ValueError(f'{path.name} missing required columns: {missing}')
    return columns


def read_source(path: pathlib.Path) -> pd.DataFrame:
    kwargs = {
        'usecols': select_columns(path),
        'dtype': 'string',
        'keep_default_na': False,
        'na_filter': False,
    }
    if path.suffix == '.zip':
        return pd.read_csv(path, compression='zip', **kwargs)
    return pd.read_csv(path, compression='gzip', **kwargs)


def read_shots(shots_dir: pathlib.Path, start_year: int) -> pd.DataFrame:
    frames = [read_source(path) for path in shot_sources(shots_dir, start_year)]
    return pd.concat(frames, ignore_index=True)


def as_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors='coerce').fillna(0).astype('int64')


def as_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors='coerce').fillna(0.0).astype('float64')


def normalize_id(series: pd.Series) -> pd.Series:
    return (
        series.astype('string')
        .str.strip()
        .str.removesuffix('.0')
        .fillna('')
    )


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    for column in df.columns:
        if column in FLOAT_COLUMNS:
            df[column] = as_float(df[column])
        elif column in INT_COLUMNS:
            df[column] = as_int(df[column])
        else:
            df[column] = df[column].astype('string').fillna('')
    return df


def dedupe_shot_events(df: pd.DataFrame) -> pd.DataFrame:
    """Drop source rows duplicated under MoneyPuck's game event identifier."""
    key_columns = ['season', 'game_id', 'id']
    duplicate_rows = df[df.duplicated(key_columns, keep=False)]
    if duplicate_rows.empty:
        return df

    value_columns = [column for column in df.columns if column not in key_columns]
    conflicts = (
        duplicate_rows.groupby(key_columns, sort=True)[value_columns]
        .nunique(dropna=False)
        .gt(1)
        .any(axis=1)
    )
    if conflicts.any():
        examples = conflicts[conflicts].index.tolist()[:5]
        raise ValueError(f'conflicting duplicate MoneyPuck shot events: {examples}')
    return df.drop_duplicates(key_columns, keep='first').copy()


def canonical_game_id(df: pd.DataFrame) -> pd.Series:
    game_suffix = df['game_id'].astype('string').str.zfill(5)
    return (df['seasonStartYear'].astype('string') + '0' + game_suffix).astype('string')


def derive_opponent_code(df: pd.DataFrame) -> pd.Series:
    return df['awayTeamCode'].where(df['teamCode'] == df['homeTeamCode'], df['homeTeamCode'])


def prepare_shots(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_types(df.copy())
    df = dedupe_shot_events(df)
    df['gameTypeId'] = df['game_id'].astype('string').str[0]
    df = df[df['gameTypeId'].isin(['2', '3'])].copy()
    playoff_flag_mismatch = df['isPlayoffGame'].ne(df['gameTypeId'].eq('3').astype('int64'))
    if playoff_flag_mismatch.any():
        raise ValueError('game_id type disagrees with isPlayoffGame')
    df['shooterPlayerId'] = normalize_id(df['shooterPlayerId'])
    df['goalieIdForShot'] = normalize_id(df['goalieIdForShot'])
    df['seasonStartYear'] = df['season'].astype('string')
    df['season'] = df['seasonStartYear'].map(lambda value: season_label(int(value)))
    df['seasonId'] = df['season'].map(
        lambda label: f"{label[:4]}20{label[-2:]}"
    )
    df['gameId'] = canonical_game_id(df)
    df['gameTypeId'] = df['gameTypeId'].astype('int64')
    df['isHome'] = df['isHomeTeam'].astype('int64')
    df['teamCode'] = df['teamCode'].astype('string')
    df['opponentCode'] = derive_opponent_code(df).astype('string')
    df['playerId'] = df['shooterPlayerId'].astype('string')
    df['playerName'] = df['shooterName'].astype('string')
    df['goalieId'] = df['goalieIdForShot'].astype('string')
    df['goalieName'] = df['goalieNameForShot'].astype('string')
    df['unblockedShotAttempt'] = 1
    df['highDangerShot'] = (df['xGoal'] > 0.2).astype('int64')
    df['highDangerXGoal'] = df['xGoal'].where(df['xGoal'] > 0.2, 0.0)
    df['isFiveOnFive'] = (
        (df['homeSkatersOnIce'] == 5)
        & (df['awaySkatersOnIce'] == 5)
        & (df['homeEmptyNet'] == 0)
        & (df['awayEmptyNet'] == 0)
    ).astype('int64')
    return df


def metric_columns(prefix: str) -> list[str]:
    return [f'{prefix}{name[0].upper()}{name[1:]}' for name in BASE_METRICS]


def rename_metrics(df: pd.DataFrame, suffix: str) -> pd.DataFrame:
    renamed = {}
    for prefix in ['all', 'fiveOnFive']:
        for metric in BASE_METRICS:
            source = f'{prefix}{metric[0].upper()}{metric[1:]}'
            renamed[source] = f'{source}{suffix}'
    return df.rename(columns=renamed)


def add_prefixed_metrics(df: pd.DataFrame) -> pd.DataFrame:
    for metric, source in BASE_METRICS.items():
        series = df[source]
        all_column = f'all{metric[0].upper()}{metric[1:]}'
        five_column = f'fiveOnFive{metric[0].upper()}{metric[1:]}'
        df[all_column] = series
        df[five_column] = series * df['isFiveOnFive']
    return df


def sum_columns(columns: list[str]) -> dict[str, str]:
    return {column: 'sum' for column in columns}


def team_for_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = add_prefixed_metrics(df.copy())
    aggregate = sum_columns(metric_columns('all') + metric_columns('fiveOnFive'))
    grouped = (
        df.groupby(TEAM_KEY_COLUMNS, sort=True, as_index=False)
        .agg(aggregate)
        .sort_values(TEAM_KEY_COLUMNS, kind='stable')
    )
    return grouped


def team_against_frame(team_metrics: pd.DataFrame) -> pd.DataFrame:
    against = team_metrics.copy()
    against['teamCode'], against['opponentCode'] = (
        team_metrics['opponentCode'],
        team_metrics['teamCode'],
    )
    against['isHome'] = 1 - team_metrics['isHome']
    return against


def merge_team_frames(team_for: pd.DataFrame, team_against: pd.DataFrame) -> pd.DataFrame:
    for_merge = team_for.copy()
    against_merge = team_against.copy()
    merged = for_merge.merge(
        against_merge,
        on=['season', 'seasonId', 'gameTypeId', 'gameId', 'teamCode', 'opponentCode', 'isHome'],
        how='left',
        validate='one_to_one',
    )
    return merged[TEAM_COLUMN_ORDER].sort_values(
        ['gameId', 'teamCode'], kind='stable'
    )


def build_team_game(df: pd.DataFrame) -> pd.DataFrame:
    team_metrics = team_for_frame(df)
    team_for = rename_metrics(team_metrics.copy(), 'For')
    team_against = rename_metrics(team_against_frame(team_metrics), 'Against')
    return merge_team_frames(team_for, team_against)


def build_skater_game(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df['playerId'] != ''].copy()
    df = add_prefixed_metrics(df)
    aggregate = sum_columns(metric_columns('all') + metric_columns('fiveOnFive'))
    grouped = (
        df.groupby(SKATER_KEY_COLUMNS, sort=True, as_index=False)
        .agg(aggregate)
        .sort_values(SKATER_KEY_COLUMNS, kind='stable')
    )
    return grouped.rename(
        columns={
            'allXGoals': 'allIXGoals',
            'fiveOnFiveXGoals': 'fiveOnFiveIXGoals',
        }
    )[SKATER_COLUMN_ORDER].sort_values(
        ['gameId', 'teamCode', 'playerId'], kind='stable'
    )


def goalie_events(df: pd.DataFrame) -> pd.DataFrame:
    goalie_df = df[(df['goalieId'] != '') & (df['shotOnEmptyNet'] == 0)].copy()
    goalie_df['teamCode'] = goalie_df['opponentCode']
    goalie_df['opponentCode'] = df.loc[goalie_df.index, 'teamCode']
    goalie_df['isHome'] = 1 - df.loc[goalie_df.index, 'isHome']
    goalie_df['shotsFaced'] = goalie_df['shotWasOnGoal']
    goalie_df['unblockedShotsFaced'] = goalie_df['unblockedShotAttempt']
    goalie_df['xGoalsFaced'] = goalie_df['xGoal']
    goalie_df['goalsAgainst'] = goalie_df['goal']
    return goalie_df


def goalie_starters(df: pd.DataFrame) -> pd.DataFrame:
    ordered = df.sort_values(
        ['season', 'gameId', 'teamCode', 'time', 'id', 'goalieId'],
        kind='stable',
    )
    starters = ordered.groupby(['season', 'gameId', 'teamCode'], as_index=False).first()
    starters['starter'] = 1
    return starters[['season', 'gameId', 'teamCode', 'goalieId', 'starter']]


def build_goalie_game(df: pd.DataFrame) -> pd.DataFrame:
    events = goalie_events(df)
    grouped = (
        events.groupby(GOALIE_KEY_COLUMNS, sort=True, as_index=False)
        .agg(
            {
                'shotsFaced': 'sum',
                'unblockedShotsFaced': 'sum',
                'xGoalsFaced': 'sum',
                'goalsAgainst': 'sum',
            }
        )
        .sort_values(GOALIE_KEY_COLUMNS, kind='stable')
    )
    starters = goalie_starters(events)
    grouped = grouped.merge(
        starters,
        on=['season', 'gameId', 'teamCode', 'goalieId'],
        how='left',
        validate='one_to_one',
    )
    grouped['starter'] = grouped['starter'].fillna(0).astype('int64')
    grouped['gsax'] = grouped['xGoalsFaced'] - grouped['goalsAgainst']
    shot_totals = grouped.groupby(['season', 'gameId', 'teamCode'])['shotsFaced'].transform('sum')
    unblocked_totals = grouped.groupby(['season', 'gameId', 'teamCode'])[
        'unblockedShotsFaced'
    ].transform('sum')
    grouped['shotsFacedShare'] = (
        grouped['shotsFaced'] / shot_totals.where(shot_totals != 0, 1)
    )
    grouped['unblockedShotsFacedShare'] = (
        grouped['unblockedShotsFaced'] / unblocked_totals.where(unblocked_totals != 0, 1)
    )
    return grouped[GOALIE_COLUMN_ORDER].sort_values(
        ['gameId', 'teamCode', 'goalieId'], kind='stable'
    )


def write_csv_gz(df: pd.DataFrame, path: pathlib.Path) -> None:
    payload = df.to_csv(index=False, lineterminator='\n', float_format='%.15g')
    with path.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=9, mtime=0) as gz:
            gz.write(payload.encode('utf-8'))


def aggregate_season(shots_dir: pathlib.Path, out_dir: pathlib.Path, start_year: int) -> None:
    label = season_label(start_year)
    df = prepare_shots(read_shots(shots_dir, start_year))
    write_csv_gz(build_team_game(df), out_dir / f'team-game-xg-{label}.csv.gz')
    write_csv_gz(build_skater_game(df), out_dir / f'skater-game-xg-{label}.csv.gz')
    write_csv_gz(build_goalie_game(df), out_dir / f'goalie-game-{label}.csv.gz')


def main(
    shots_dir_arg: str,
    out_dir_arg: str,
    start_year_arg: str | None = None,
) -> None:
    shots_dir = pathlib.Path(shots_dir_arg)
    out_dir = pathlib.Path(out_dir_arg)
    out_dir.mkdir(parents=True, exist_ok=True)
    years = [int(start_year_arg)] if start_year_arg is not None else shot_years(shots_dir)
    for start_year in years:
        aggregate_season(shots_dir, out_dir, start_year)


if __name__ == '__main__':
    if len(sys.argv) not in {3, 4}:
        raise SystemExit(
            'usage: aggregate_shots.py <shots_dir> <out_dir> [season_start_year]'
        )
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
