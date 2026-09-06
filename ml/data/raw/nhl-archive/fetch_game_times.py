#!/usr/bin/env python3
"""Fetch per-game start times from club schedules for every archived NHL season."""
import collections
import csv
import glob
import gzip
import json
import os
import subprocess
import sys
import time

WEB = 'https://api-web.nhle.com/v1'
DELAY = 1.0
ATTEMPTS = 3
COLUMNS = [
    'gameId',
    'seasonId',
    'gameTypeId',
    'gameDate',
    'startTimeUTC',
    'venue',
    'venueCity',
    'homeAbbrev',
    'awayAbbrev',
    'neutralSite',
]
SCHEDULE_ALIASES = {'PHX': 'ARI'}


def log(msg):
    print(msg, flush=True)


def get(url, counters, attempts=ATTEMPTS):
    for i in range(attempts):
        time.sleep(DELAY)
        counters['requests'] += 1
        p = subprocess.run(
            ['curl', '-sS', '--max-time', '180', url],
            capture_output=True,
        )
        if p.returncode == 0 and p.stdout:
            try:
                return json.loads(p.stdout.decode('utf-8'))
            except json.JSONDecodeError:
                pass
        if i + 1 == attempts:
            counters['failures'] += 1
            break
        counters['retries'] += 1
        backoff = DELAY * (2**i)
        log(f'    retry {i + 1}/{attempts} in {backoff:.0f}s :: {url}')
        time.sleep(backoff)
    return None


def read_team_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def season_files(outdir):
    return sorted(glob.glob(os.path.join(outdir, 'team-games-*.csv.gz')))


def season_label(path):
    name = os.path.basename(path)
    return name[len('team-games-') : -len('.csv.gz')]


def group_rows_by_game(rows):
    by_game = collections.defaultdict(list)
    for row in rows:
        by_game[row['gameId']].append(row)
    return by_game


def note_game_row_count(notes, game_id, game_rows):
    notes.append(
        {
            'gameId': game_id,
            'issue': f'expected 2 team rows, found {len(game_rows)}',
        }
    )


def store_team_abbrev(team_id_to_abbrev, notes, team_id, abbrev):
    seen = team_id_to_abbrev.get(team_id)
    if seen is not None and seen != abbrev:
        notes.append(
            {
                'teamId': team_id,
                'issue': f'abbrev mismatch {seen} vs {abbrev}',
            }
        )
        return
    team_id_to_abbrev[team_id] = abbrev


def add_game_team_abbrevs(team_id_to_abbrev, notes, game_id, game_rows):
    if len(game_rows) != 2:
        note_game_row_count(notes, game_id, game_rows)
        return
    left, right = game_rows
    store_team_abbrev(
        team_id_to_abbrev, notes, left['teamId'], right['opponentTeamAbbrev']
    )
    store_team_abbrev(
        team_id_to_abbrev, notes, right['teamId'], left['opponentTeamAbbrev']
    )


def derive_team_abbrevs(rows):
    team_id_to_abbrev = {}
    notes = []
    for game_id, game_rows in group_rows_by_game(rows).items():
        add_game_team_abbrevs(team_id_to_abbrev, notes, game_id, game_rows)
    return sorted(set(team_id_to_abbrev.values())), notes


def regular_or_playoff(games):
    return [g for g in games if str(g.get('gameType')) in {'2', '3'}]


def fetch_schedule(team_abbrev, season_id, counters):
    counters['schedule_requests'] += 1
    url = f'{WEB}/club-schedule-season/{team_abbrev}/{season_id}'
    data = get(url, counters)
    if data is None:
        return None, team_abbrev, None
    games = regular_or_playoff(data.get('games', []))
    alias = SCHEDULE_ALIASES.get(team_abbrev)
    if games or alias is None:
        return games, team_abbrev, None
    alias_url = f'{WEB}/club-schedule-season/{alias}/{season_id}'
    log(f'    {team_abbrev} returned no regular/playoff games; retrying as {alias}')
    counters['schedule_requests'] += 1
    data = get(alias_url, counters)
    if data is None:
        return None, alias, team_abbrev
    return regular_or_playoff(data.get('games', [])), alias, team_abbrev


def venue_name(game):
    venue = game.get('venue') or {}
    return venue.get('default', '') if isinstance(venue, dict) else ''


def venue_city(game):
    location = game.get('venueLocation') or {}
    if isinstance(location, dict) and location.get('default'):
        return location['default']
    if game.get('neutralSite'):
        return ''
    home = game.get('homeTeam') or {}
    place = home.get('placeName') or {}
    return place.get('default', '')


def game_row(game):
    home = game.get('homeTeam') or {}
    away = game.get('awayTeam') or {}
    return {
        'gameId': str(game.get('id', '')),
        'seasonId': str(game.get('season', '')),
        'gameTypeId': str(game.get('gameType', '')),
        'gameDate': game.get('gameDate', '') or '',
        'startTimeUTC': game.get('startTimeUTC', '') or '',
        'venue': venue_name(game),
        'venueCity': venue_city(game),
        'homeAbbrev': home.get('abbrev', '') or '',
        'awayAbbrev': away.get('abbrev', '') or '',
        'neutralSite': 'true' if game.get('neutralSite') else 'false',
    }


def fetch_landing(game_id, counters):
    counters['landing_requests'] += 1
    return get(f'{WEB}/gamecenter/{game_id}/landing', counters)


def enrich_neutral_sites(rows_by_game, counters):
    updated = 0
    missing = []
    for game_id, row in rows_by_game.items():
        if row['neutralSite'] != 'true':
            continue
        landing = fetch_landing(game_id, counters)
        if landing is None:
            missing.append(game_id)
            continue
        location = landing.get('venueLocation') or {}
        city = location.get('default', '') if isinstance(location, dict) else ''
        if not city:
            missing.append(game_id)
            continue
        row['venueCity'] = city
        updated += 1
    return updated, missing


def write_csv_gz(path, rows):
    with gzip.open(path, 'wt', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def validate(rows_by_game, expected_game_ids):
    actual_game_ids = set(rows_by_game)
    missing_game_ids = sorted(expected_game_ids - actual_game_ids)
    extra_game_ids = sorted(actual_game_ids - expected_game_ids)
    blank_start_times = sorted(
        game_id
        for game_id, row in rows_by_game.items()
        if not row['startTimeUTC']
    )
    return missing_game_ids, extra_game_ids, blank_start_times


def season_context(team_path):
    label = season_label(team_path)
    rows = read_team_rows(team_path)
    return label, rows, rows[0]['seasonId'], {row['gameId'] for row in rows}


def add_schedule_row(rows_by_game, mismatches, row):
    existing = rows_by_game.get(row['gameId'])
    if existing is None:
        rows_by_game[row['gameId']] = row
        return
    if existing != row:
        mismatches.append(
            {
                'gameId': row['gameId'],
                'issue': 'duplicate schedule rows disagree',
                'left': existing,
                'right': row,
            }
        )


def add_schedule_games(rows_by_game, mismatches, games):
    for game in games:
        add_schedule_row(rows_by_game, mismatches, game_row(game))


def collect_schedule_rows(teams, season_id, counters):
    rows_by_game = {}
    mismatches = []
    aliases_used = {}
    for team in teams:
        games, used_team, alias_from = fetch_schedule(team, season_id, counters)
        if games is None:
            mismatches.append({'team': team, 'issue': 'schedule request failed after retries'})
            continue
        if alias_from is not None:
            aliases_used[team] = used_team
        log(f'  {team}->{used_team}: {len(games)} reg+po games')
        add_schedule_games(rows_by_game, mismatches, games)
    return rows_by_game, mismatches, aliases_used


def sorted_rows(rows_by_game):
    return [rows_by_game[game_id] for game_id in sorted(rows_by_game, key=int)]


def neutral_playoff_count(rows):
    return sum(
        1
        for row in rows
        if row['gameTypeId'] == '3' and row['neutralSite'] == 'true'
    )


def all_playoff_games_neutral(label, rows):
    return label == '2019-20' and neutral_playoff_count(rows) == sum(
        1 for row in rows if row['gameTypeId'] == '3'
    )


def season_summary(season, out_rows, validation):
    neutral_playoff_rows = neutral_playoff_count(out_rows)
    return {
        'season': season['label'],
        'seasonId': season['season_id'],
        'teams': season['team_count'],
        'games': season['game_count'],
        'rows': len(out_rows),
        'neutral_playoff_rows': neutral_playoff_rows,
        'aliases_used': season['aliases_used'],
        'team_notes': season['team_notes'],
        'duplicate_mismatches': season['mismatches'],
        'missing_game_ids': validation['missing_game_ids'],
        'extra_game_ids': validation['extra_game_ids'],
        'blank_start_times': validation['blank_start_times'],
        'neutral_city_misses': validation['neutral_city_misses'],
        'all_2020_playoff_games_neutral': all_playoff_games_neutral(
            season['label'], out_rows
        ),
    }


def process_season(team_path, outdir, counters):
    label, rows, season_id, expected_game_ids = season_context(team_path)
    teams, team_notes = derive_team_abbrevs(rows)
    log(f'=== season {label} ({season_id}) teams={len(teams)} games={len(expected_game_ids)}')
    rows_by_game, mismatches, aliases_used = collect_schedule_rows(
        teams, season_id, counters
    )
    neutral_updates, neutral_city_misses = enrich_neutral_sites(rows_by_game, counters)
    missing_game_ids, extra_game_ids, blank_start_times = validate(
        rows_by_game, expected_game_ids
    )
    out_rows = sorted_rows(rows_by_game)
    write_csv_gz(os.path.join(outdir, f'game-times-{label}.csv.gz'), out_rows)
    neutral_playoff_rows = neutral_playoff_count(out_rows)
    log(
        f'  wrote {label}: rows {len(out_rows)} neutral-playoff {neutral_playoff_rows} '
        f'neutral-city-updates {neutral_updates}'
    )
    season = {
        'label': label,
        'season_id': season_id,
        'team_count': len(teams),
        'game_count': len(expected_game_ids),
        'aliases_used': aliases_used,
        'team_notes': team_notes,
        'mismatches': mismatches,
    }
    validation = {
        'missing_game_ids': missing_game_ids,
        'extra_game_ids': extra_game_ids,
        'blank_start_times': blank_start_times,
        'neutral_city_misses': neutral_city_misses,
    }
    return season_summary(season, out_rows, validation)


def main(outdir):
    files = season_files(outdir)
    if not files:
        raise SystemExit(f'no team-games files found in {outdir}')
    counters = {
        'requests': 0,
        'schedule_requests': 0,
        'landing_requests': 0,
        'retries': 0,
        'failures': 0,
    }
    manifest = [process_season(path, outdir, counters) for path in files]
    summary = {'request_counts': counters, 'seasons': manifest}
    with open(os.path.join(outdir, '_game_times_manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, indent=1)
    log(
        f"DONE seasons={len(manifest)} requests={counters['requests']} "
        f"schedule={counters['schedule_requests']} landing={counters['landing_requests']} "
        f"retries={counters['retries']} failures={counters['failures']}"
    )


if __name__ == '__main__':
    main(sys.argv[1])
