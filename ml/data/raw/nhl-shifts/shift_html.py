#!/usr/bin/env python3
"""Parse NHL HTML time-on-ice reports and resolve archived player IDs."""

import csv
import difflib
import gzip
import html.parser
import re
import unicodedata

PLAYER_PATTERN = re.compile(r"^\s*\d+\s+(?:-\s*)?([^,]+),\s*(.+?)\s*$")


class FetchError(RuntimeError):
    pass


class TextTableParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attributes):
        del attributes
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None


def log(message):
    print(message, flush=True)


def seconds(value):
    if value in (None, ""):
        return 0
    text = str(value).strip()
    if ":" not in text:
        return int(float(text))
    parts = [int(part) for part in text.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"invalid clock value: {value!r}")


def normalize_name(value):
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return "".join(character for character in ascii_text.casefold() if character.isalnum())


def archive_player(row, name_column):
    name = row[name_column]
    return (
        row["playerId"],
        name.split(" ", 1)[0],
        row.get("lastName") or name.rsplit(" ", 1)[-1],
    )


def add_game_skaters(mapping, path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["gameId"], row["teamAbbrev"], normalize_name(row["skaterFullName"]))
            mapping[key] = archive_player(row, "skaterFullName")


def add_game_goalies(mapping, path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = row["goalieFullName"]
            key = (row["gameId"], row["teamAbbrev"], normalize_name(name))
            mapping[key] = archive_player(row, "goalieFullName")


def unique_bio_players(path):
    bios = {}
    duplicate_bios = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = row["skaterFullName"]
            normalized = normalize_name(name)
            player = archive_player(row, "skaterFullName")
            if normalized in bios and bios[normalized][0] != player[0]:
                duplicate_bios.add(normalized)
            bios[normalized] = player
    return {
        normalized: player
        for normalized, player in bios.items()
        if normalized not in duplicate_bios
    }


def read_game_players(archive, label):
    mapping = {}
    add_game_skaters(mapping, archive / f"skater-games-{label}.csv.gz")
    add_game_goalies(mapping, archive / f"goalie-games-{label}.csv.gz")
    for normalized, player in unique_bio_players(archive / f"skater-bios-{label}.csv.gz").items():
        mapping[("BIO", "", normalized)] = player
    return mapping


def game_roster(player_map, game_id, team):
    return {
        player[0]: player
        for key, player in player_map.items()
        if key[0] == game_id and key[1] == team
    }


def unique_match(players):
    unique = {player[0]: player for player in players}
    return next(iter(unique.values())) if len(unique) == 1 else None


def fuzzy_surname_match(roster, first_initial, normalized_last):
    scored = sorted(
        (
            difflib.SequenceMatcher(None, normalized_last, normalize_name(player[2])).ratio(),
            player_id,
            player,
        )
        for player_id, player in roster.items()
        if normalize_name(player[1])[:1] == first_initial
    )
    if not scored or scored[-1][0] < 0.75:
        return None
    if len(scored) > 1 and scored[-1][0] - scored[-2][0] < 0.15:
        return None
    return scored[-1][2]


def resolve_html_player(player_map, source, player_name):
    game_id, team = source
    first_name, last_name = player_name
    exact_name = normalize_name(f"{first_name} {last_name}")
    exact = player_map.get((game_id, team, exact_name))
    if exact is not None:
        return exact
    roster = game_roster(player_map, game_id, team)
    normalized_last = normalize_name(last_name)
    surname = unique_match(
        player for player in roster.values() if normalize_name(player[2]) == normalized_last
    )
    if surname is not None:
        return surname
    return fuzzy_surname_match(roster, normalize_name(first_name)[:1], normalized_last)


def player_name(cells):
    matches = (PLAYER_PATTERN.match(cell) for cell in cells if ":" not in cell)
    match = next((candidate for candidate in matches if candidate), None)
    return (match.group(2), match.group(1)) if match else None


def is_shift_row(cells):
    if len(cells) != 6:
        return False
    identity_is_valid = cells[0].isdigit() and cells[1] in {"1", "2", "3", "4", "5"}
    clocks_are_valid = all(":" in value for value in cells[2:4])
    return identity_is_valid and clocks_are_valid


def cross_team_player(player_map, source, current_player_name):
    game_id, team = source
    normalized = normalize_name(" ".join(current_player_name))
    matches = {
        player[0]: player
        for key, player in player_map.items()
        if key[0] == game_id and key[1] != team and key[2] == normalized
    }
    return next(iter(matches.values())) if len(matches) == 1 else None


def resolve_html_heading(player_map, source, current_player_name):
    player = resolve_html_player(player_map, source, current_player_name)
    if player is not None:
        return player
    game_id, team = source
    display_name = " ".join(current_player_name)
    if cross_team_player(player_map, source, current_player_name) is not None:
        log(f"    skip cross-team HTML player: {game_id} {team} {display_name}")
        return False
    normalized = normalize_name(display_name)
    season_bio = player_map.get(("BIO", "", normalized))
    if season_bio is not None:
        log(f"    map HTML player from season bio: {game_id} {team} {display_name}")
        return season_bio
    raise FetchError(f"HTML player could not map uniquely: {game_id} {team} {display_name}")


def period_length(game_id, period):
    if period <= 3 or game_id[4:6] == "03":
        return 1200
    return 300


def interval_parts(game_id, period, start, end):
    length = period_length(game_id, period)
    end_limit = length if end >= start else period_length(game_id, period + 1)
    if start > length or end > end_limit:
        raise FetchError(
            f"shift clock outside period: {game_id} period={period} start={start} end={end}"
        )
    if end >= start:
        return [(period, start, end)]
    return [
        segment
        for segment in ((period, start, length), (period + 1, 0, end))
        if segment[2] > segment[1]
    ]


def shift_interval_parts(game_id, interval):
    period, start, end, duration = interval
    length = period_length(game_id, period)
    if start == end == 0 and duration == length:
        return [(period, 0, length)]
    if length == 300 and end == 1200:
        end = length
    return interval_parts(game_id, period, start, end)


def html_shift_rows(cells, source, player):
    game_id, team = source
    player_id, first_name, last_name = player
    start = seconds(cells[2].split("/", 1)[0].strip())
    end = seconds(cells[3].split("/", 1)[0].strip())
    period = int(cells[1])
    return [
        {
            "gameId": game_id,
            "teamAbbrev": team,
            "playerId": player_id,
            "firstName": first_name,
            "lastName": last_name,
            "period": str(part_period),
            "startSeconds": str(part_start),
            "endSeconds": str(part_end),
            "durationSeconds": str(part_end - part_start),
            "shiftNumber": cells[0],
            "typeCode": "517",
            "eventDescription": cells[5],
        }
        for part_period, part_start, part_end in interval_parts(game_id, period, start, end)
    ]


def parse_html_report(raw, game_id, team, player_map):
    parser = TextTableParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    current_player = None
    output = []
    for cells in parser.rows:
        heading = player_name(cells)
        if heading is not None:
            current_player = resolve_html_heading(player_map, (game_id, team), heading)
        if current_player and is_shift_row(cells):
            output.extend(html_shift_rows(cells, (game_id, team), current_player))
    return output
