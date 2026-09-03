"""Parse committed league draft-history snapshots into a raw picks table (US-006).

The committed sheet snapshots in ``data/raw/league-drafts/`` are hand-kept Google
Sheets records of the SportsNot fantasy-hockey league's playoff drafts (2024, 2025,
2026), plus a Supabase export of the in-app 2026 season. This module is pure parsing:
it reads those files exactly as documented in that directory's ``SCHEMA.md`` /
``OPEN_QUESTIONS.md`` and emits two tables — a raw ``league_picks`` table (one row per
drafted roster slot) and a ``league_champions`` table.

Contract highlights (see the source docs for the full reasoning):

* Sheet-era seasons have **three** draft events — ``R1``, ``R2`` and ``R3_4`` — because
  playoff rounds 3 and 4 were drafted together. ``sheet1__round-3-4.csv`` is a stale
  2025 duplicate and is deliberately **excluded** (SCHEMA §4.3).
* Rows are **not** in pick order (owner-confirmed), so sheet ``pick_number`` stays null;
  ``snake_slot`` is read from each tab's draft-order list (first listed = first pick).
  The app export preserves true ``pick_number``.
* Documented data corrections are applied: the ``Makar``/``Oilers`` row is Evan Bouchard;
  the Trouba→Kulikov note is parsed as recorded (never modelled as a mechanic); and the
  two formula-only IR swaps in ``sheet2__round-3-4.csv`` are flagged points-excluded /
  activated even though the CSV carries no text flag.
* ``Dropped`` / ``Not playing`` starters are points-excluded and paired with the
  same-position ``Activated`` IR row in the same manager block (the retroactive IR swap).
* Parsers fail loudly if a committed file's layout does not match ``SCHEMA.md``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from draft_oracle.ingest import _league_drafts_order as _league_drafts_order_module
from draft_oracle.ingest.normalize import DEFAULT_NORMALIZED_DIR

# ── Directory contract (SPEC §4) ─────────────────────────────────────────

DEFAULT_LEAGUE_DRAFTS_DIR = Path("data/raw/league-drafts")

# The historical league the sheets record.
SHEET_LEAGUE_NAME = "The Gemmell Cup"

# ── Managers ─────────────────────────────────────────────────────────────

# Canonical ids for the four historical league managers (SCHEMA §6).
LEAGUE_MANAGERS: frozenset[str] = frozenset({"ben", "judah", "kyle", "levi"})

# Surface-form → canonical id. Sheet spellings (``Evi`` = ``Levi``, SCHEMA §6) plus the
# app usernames (APP_EXPORT.md). Press-only managers keep their lowercased username.
_MANAGER_ALIASES: dict[str, str] = {
    "ben": "ben",
    "judah": "judah",
    "kyle": "kyle",
    "levi": "levi",
    "evi": "levi",
    # app usernames
    "nuttguy": "kyle",
    "bentunigold": "ben",
    "judah18": "judah",
    "gemmell.levi": "levi",
}

# Sheet surface forms that identify a Gemmell manager (used to find order lists).
_SHEET_MANAGER_FORMS: frozenset[str] = frozenset({"ben", "judah", "kyle", "levi", "evi"})


def canonical_manager(name: str) -> str:
    """Fold a raw manager label to its canonical id.

    Trailing whitespace is stripped and casing normalized (SCHEMA §6). Known aliases
    map to the canonical id; unknown names (e.g. Press-only managers) return their
    lowercased form unchanged.
    """
    key = name.strip().lower()
    return _MANAGER_ALIASES.get(key, key)


def _is_manager_token(cell: str) -> bool:
    return cell.strip().lower() in _SHEET_MANAGER_FORMS


# ── Roster slots ─────────────────────────────────────────────────────────

_TOTAL_LABELS: frozenset[str] = frozenset({"Total", "Total across Rounds"})
_STATUS_FLAGS: frozenset[str] = frozenset({"Dropped", "Activated", "Not playing"})
_APP_POSITIONS: frozenset[str] = frozenset({"F", "D", "G", "IR_F", "IR_D"})


def slot_position(label: str) -> str | None:
    """Map a column-B slot label to a pool position (F/D/G/IR_F/IR_D), or ``None``.

    ``None`` marks a non-roster label (the ``Total`` rows). An unrecognized label is a
    layout error and is raised by the caller.
    """
    stripped = label.strip()
    if stripped.startswith("Forward"):
        return "F"
    if stripped.startswith("Defense"):
        return "D"
    if stripped.startswith("Goalie"):
        return "G"
    if stripped == "IR - F":
        return "IR_F"
    if stripped == "IR - D":
        return "IR_D"
    return None


# ── Sheet tab registry ───────────────────────────────────────────────────

# (filename, season, draft_event). sheet1__round-3-4.csv is intentionally absent — it is
# a stale 2025 duplicate (SCHEMA §4.3) and must be deduped against sheet2, not ingested.
SHEET_TABS: tuple[tuple[str, int, str], ...] = (
    ("sheet3__round-1.csv", 2024, "R1"),
    ("sheet3__round-2.csv", 2024, "R2"),
    ("sheet3__round-3-round-4.csv", 2024, "R3_4"),
    ("sheet2__round-1.csv", 2025, "R1"),
    ("sheet2__round-2.csv", 2025, "R2"),
    ("sheet2__round-3-4.csv", 2025, "R3_4"),
    ("sheet1__round-1.csv", 2026, "R1"),
    ("sheet1__round-2.csv", 2026, "R2"),
)

WINS_TABS: tuple[str, ...] = (
    "sheet3__wins.csv",
    "sheet2__wins.csv",
    "sheet1__wins.csv",
)

# ── Documented corrections (OPEN_QUESTIONS.md) ───────────────────────────

# A3: the ``Makar``/``Oilers`` row (Levi's Defense 1, 2024 R3+4) is Evan Bouchard.
_NAME_OVERRIDES: dict[tuple[int, str, str, str], str] = {
    (2024, "R3_4", "levi", "Defense 1"): "Evan Bouchard",
}

# R5 / SCHEMA §5: two formula-only starter→IR swaps in sheet2__round-3-4.csv that carry
# NO text flag. Applied here so the roster-as-scored matches the xlsx totals. This is the
# league's IR retroactive swap, NOT a mid-round substitution mechanic (OPEN_QUESTIONS A2).
_UNFLAGGED_SWAPS: dict[tuple[int, str, str, str], str] = {
    (2025, "R3_4", "ben", "Forward 3"): "excluded",  # Sam Reinhart
    (2025, "R3_4", "ben", "IR - F"): "activated",  # Carter Verhaeghe
    (2025, "R3_4", "judah", "Forward 4"): "excluded",  # Zach Hyman
    (2025, "R3_4", "judah", "IR - F"): "activated",  # Connor Brown
}

# 2026 champion is owner-confirmed (OPEN_QUESTIONS "Kyle's answers" §3); it is scored in
# the app, not the sheets, so it never appears in a Wins tab.
_OWNER_CHAMPIONS: dict[int, str] = {2026: "ben"}

# Unified picks-table columns.
PICK_COLUMNS: tuple[str, ...] = (
    "season",
    "source",
    "league_name",
    "draft_event",
    "manager",
    "snake_slot",
    "pick_number",
    "position",
    "slot_label",
    "player_or_team_name",
    "corrected_name",
    "team_name",
    "points_for_round",
    "points_when_drafted",
    "current_total_points",
    "status",
    "points_excluded",
    "ir_activated",
    "swap_partner",
    "note",
    "is_scored",
)

_INT_COLUMNS: tuple[str, ...] = (
    "season",
    "snake_slot",
    "pick_number",
    "points_for_round",
    "points_when_drafted",
    "current_total_points",
)
_BOOL_COLUMNS: tuple[str, ...] = ("points_excluded", "ir_activated", "is_scored")


@dataclass(frozen=True)
class _BlockParseContext:
    manager: str
    season: int
    event: str
    scored: bool
    order: dict[str, int] | None


@dataclass(frozen=True)
class _SheetPickInput:
    row: list[str]
    label: str
    position: str
    player: str
    team: str
    block: _BlockParseContext


@dataclass(frozen=True)
class SheetTabRequest:
    rows: list[list[str]]
    season: int
    event: str


@dataclass(frozen=True)
class _SheetPointFields:
    status: str | None
    note: str | None
    points_when_drafted: int | None
    current_total_points: int | None


@dataclass(frozen=True)
class _ParsedBlockRow:
    is_total: bool
    pick: dict[str, object] | None = None


# ── Low-level helpers ────────────────────────────────────────────────────


def read_csv_rows(path: Path) -> list[list[str]]:
    """Read a committed CSV verbatim (CRLF, padded rectangle) into a list of rows."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [list(row) for row in csv.reader(handle)]


def _cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def _num(value: str) -> int | None:
    text = value.strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


# ── Draft-order detection ────────────────────────────────────────────────


def detect_draft_order(rows: list[list[str]]) -> dict[str, int] | None:
    """Read the four-manager draft-order list from a round tab's annotation area.

    The order list appears once per tab as four manager names — written across a row
    (sheets 1/2 R2/R3+4) or down a column (sheet 3, and sheet1 R1). Reading order = pick
    1→4 (SCHEMA §3.2). Only the annotation area (columns to the right of the roster,
    index ≥ 5) is scanned so block labels in column A are never mistaken for an order.

    Returns ``{canonical_manager: snake_slot}`` (1-based) or ``None`` when a tab records
    no order (``sheet2__round-1.csv``). Raises if two conflicting orders are found.
    """

    return _league_drafts_order_module.detect_draft_order(rows)


# ── Sheet-block splitting ────────────────────────────────────────────────


def _split_blocks(rows: list[list[str]]) -> list[tuple[str, list[list[str]]]]:
    """Split a round tab into (canonical_manager, block_rows) using column A labels.

    Column A is a merged cell per block: the manager name on the first row, blank on the
    rest, so a new block starts wherever column A holds a manager token (SCHEMA §2).
    """
    blocks: list[tuple[str, list[list[str]]]] = []
    current: list[list[str]] | None = None
    for row in rows[1:]:  # row 0 is the header
        current = _append_block_row(row, blocks, current)
    return blocks


def _append_block_row(
    row: list[str],
    blocks: list[tuple[str, list[list[str]]]],
    current: list[list[str]] | None,
) -> list[list[str]] | None:
    label = _cell(row, 0).strip()
    if label and _is_manager_token(label):
        current = []
        blocks.append((canonical_manager(label), current))
    if current is not None:
        current.append(row)
    return current


# ── Sheet tab parsing ────────────────────────────────────────────────────


def parse_sheet_tab(request: SheetTabRequest) -> list[dict[str, object]]:
    """Parse one committed round tab into raw pick rows.

    Fails loudly (``ValueError``) if the header, block count, or slot labels do not match
    the documented layout.
    """
    header = request.rows[0] if request.rows else []
    if _cell(header, 1).strip() != "Position" or _cell(header, 2).strip() != "Player":
        raise ValueError(f"{request.season} {request.event}: unexpected header row {header[:4]!r}")

    scored = request.season != 2026
    order = detect_draft_order(request.rows)
    blocks = _split_blocks(request.rows)
    managers = [manager for manager, _ in blocks]
    if set(managers) != LEAGUE_MANAGERS or len(managers) != 4:
        raise ValueError(
            f"{request.season} {request.event}: expected 4 manager blocks, got {managers}"
        )

    picks: list[dict[str, object]] = []
    for manager, block_rows in blocks:
        context = _BlockParseContext(
            manager=manager,
            season=request.season,
            event=request.event,
            scored=scored,
            order=order,
        )
        block_picks = _parse_block(block_rows, context)
        _pair_ir_swaps(block_picks)
        picks.extend(block_picks)
    return picks


def _parse_block(
    block_rows: list[list[str]],
    context: _BlockParseContext,
) -> list[dict[str, object]]:
    parsed = [_parse_block_row(row, context) for row in block_rows]
    if not any(item.is_total for item in parsed):
        raise ValueError(
            f"{context.season} {context.event} {context.manager}: block has no Total row"
        )
    return [item.pick for item in parsed if item.pick is not None]


def _parse_block_row(row: list[str], context: _BlockParseContext) -> _ParsedBlockRow:
    label = _cell(row, 1).strip()
    if label in _TOTAL_LABELS:
        return _ParsedBlockRow(is_total=True)
    position = slot_position(label)
    if position is None:
        raise ValueError(
            f"{context.season} {context.event} {context.manager}: unknown slot label {label!r}"
        )
    player = _cell(row, 2).strip()
    if player in ("", ","):
        return _ParsedBlockRow(is_total=False)
    team = _cell(row, 3).strip()
    pick_input = _SheetPickInput(row, label, position, player, team, context)
    return _ParsedBlockRow(is_total=False, pick=_build_pick(pick_input))


def _build_pick(pick_input: _SheetPickInput) -> dict[str, object]:
    row = pick_input.row
    block = pick_input.block
    points_for_round = _num(_cell(row, 4))
    fields = _sheet_point_fields(row, block.event)
    key = (block.season, block.event, block.manager, pick_input.label)
    points_excluded, ir_activated = _pick_availability_flags(fields.status, key)

    return {
        "season": block.season,
        "source": "sheet",
        "league_name": SHEET_LEAGUE_NAME,
        "draft_event": block.event,
        "manager": block.manager,
        "snake_slot": block.order.get(block.manager) if block.order else None,
        "pick_number": None,
        "position": pick_input.position,
        "slot_label": pick_input.label,
        "player_or_team_name": pick_input.player,
        "corrected_name": _NAME_OVERRIDES.get(key),
        "team_name": pick_input.team,
        "points_for_round": points_for_round,
        "points_when_drafted": fields.points_when_drafted,
        "current_total_points": fields.current_total_points,
        "status": fields.status,
        "points_excluded": points_excluded,
        "ir_activated": ir_activated,
        "swap_partner": None,
        "note": fields.note,
        "is_scored": block.scored,
    }


def _pick_availability_flags(
    status: str | None, key: tuple[int, str, str, str]
) -> tuple[bool, bool]:
    return (
        status in ("Dropped", "Not playing") or _UNFLAGGED_SWAPS.get(key) == "excluded",
        status == "Activated" or _UNFLAGGED_SWAPS.get(key) == "activated",
    )


def _sheet_point_fields(row: list[str], event: str) -> _SheetPointFields:
    if event == "R1":
        return _round_one_point_fields(row)
    return _later_round_point_fields(row)


def _round_one_point_fields(row: list[str]) -> _SheetPointFields:
    # Column F (index 5) is overloaded: a status flag, or the Hyman drafted-points
    # mini-column (numeric). Disambiguate by content (SCHEMA §5, OPEN_QUESTIONS A8).
    col_f = _cell(row, 5).strip()
    if col_f in _STATUS_FLAGS:
        return _SheetPointFields(col_f, None, None, None)
    if col_f == "":
        return _SheetPointFields(None, None, None, None)
    return _SheetPointFields(None, None, _num(col_f), _num(_cell(row, 6)))


def _later_round_point_fields(row: list[str]) -> _SheetPointFields:
    col_h = _cell(row, 7).strip()
    status = col_h if col_h in _STATUS_FLAGS else None
    note = col_h if col_h and status is None else None
    return _SheetPointFields(status, note, _num(_cell(row, 5)), _num(_cell(row, 6)))


def _pair_ir_swaps(block_picks: list[dict[str, object]]) -> None:
    """Link each points-excluded starter to its same-position Activated IR row.

    The retroactive IR swap replaces an injured starter (F/D) with the same-position IR
    player (IR_F/IR_D) in the same manager block (OPEN_QUESTIONS A5). Pairing is
    best-effort: an excluded starter with no matching IR row (e.g. 2026's IR-less tabs)
    is left unpaired.
    """
    ir_by_position = _activated_ir_by_position(block_picks)
    for pick in block_picks:
        _pair_one_ir_swap(pick, ir_by_position)


def _pair_one_ir_swap(
    pick: dict[str, object],
    ir_by_position: dict[str, list[dict[str, object]]],
) -> None:
    if not _needs_ir_partner(pick):
        return
    candidates = ir_by_position.get(str(pick["position"]), [])
    partner = next((ir for ir in candidates if ir.get("swap_partner") is None), None)
    if partner is None:
        return
    pick["swap_partner"] = partner["player_or_team_name"]
    partner["swap_partner"] = pick["player_or_team_name"]


def _activated_ir_by_position(
    block_picks: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    return {
        "F": [p for p in block_picks if _is_activated_ir(p, "IR_F")],
        "D": [p for p in block_picks if _is_activated_ir(p, "IR_D")],
    }


def _is_activated_ir(pick: dict[str, object], position: str) -> bool:
    return pick["position"] == position and bool(pick["ir_activated"])


def _needs_ir_partner(pick: dict[str, object]) -> bool:
    if not pick["points_excluded"]:
        return False
    return pick["position"] in ("F", "D")


# ── Wins-tab parsing ─────────────────────────────────────────────────────


def parse_wins_tab(rows: list[list[str]]) -> dict[int, str]:
    """Parse a Wins tab into ``{year: canonical_champion}`` for years with a champion.

    Handles both shapes: sheets 1/2 carry a header row, sheet 3 starts cold at row 10
    with no header (SCHEMA §4.1). Column A is the year, column B the league champion.
    """
    champions: dict[int, str] = {}
    for row in rows:
        parsed = _champion_from_row(row)
        if parsed is not None:
            year, champion = parsed
            champions[year] = champion
    return champions


def _champion_from_row(row: list[str]) -> tuple[int, str] | None:
    year_text = _cell(row, 0).strip()
    if not year_text.isdigit():
        return None
    champion = _cell(row, 1).strip()
    if not champion:
        return None
    return int(year_text), canonical_manager(champion)


def build_champions(league_dir: Path = DEFAULT_LEAGUE_DRAFTS_DIR) -> pd.DataFrame:
    """Merge the three Wins tabs into one champions table, plus owner-confirmed 2026."""
    merged: dict[int, str] = {}
    for year, champion in _champions_from_tabs(league_dir).items():
        merged.setdefault(year, champion)
    merged.update(_OWNER_CHAMPIONS)

    records = [{"year": year, "champion": merged[year]} for year in sorted(merged)]
    frame = pd.DataFrame(records, columns=["year", "champion"])
    frame["year"] = frame["year"].astype("Int64")
    return frame


def _champions_from_tabs(league_dir: Path) -> dict[int, str]:
    merged: dict[int, str] = {}
    for name in WINS_TABS:
        path = league_dir / name
        if path.exists():
            merged.update(parse_wins_tab(read_csv_rows(path)))
    return merged


# ── App-export parsing ───────────────────────────────────────────────────

_APP_ROUND_TO_EVENT: dict[int, str] = {1: "R1", 2: "R2", 3: "R3_4"}


def _read_dict_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_app_draft_order(rows: list[dict[str, str]]) -> dict[tuple[str, int], dict[str, int]]:
    """Derive each league-round's base snake seat (1..N) per manager from the order file.

    The stored order is a regular snake over a fixed base order, so seats 1..N are the
    first N distinct managers by ``order_position`` (APP_EXPORT.md).
    """
    base: dict[tuple[str, int], dict[str, int]] = {}
    for row in rows:
        league = row["league_name"]
        rnd = int(row["playoff_round"])
        manager = canonical_manager(row["manager"])
        seats = base.setdefault((league, rnd), {})
        if manager not in seats:
            seats[manager] = len(seats) + 1
    return base


def parse_app_picks(
    rows: list[dict[str, str]],
    order: dict[tuple[str, int], dict[str, int]],
) -> list[dict[str, object]]:
    """Parse the app draft-picks export, preserving the true ``pick_number``."""
    return [_parse_app_pick(row, order) for row in rows]


def _parse_app_pick(
    row: dict[str, str], order: dict[tuple[str, int], dict[str, int]]
) -> dict[str, object]:
    league = row["league_name"]
    rnd = int(row["playoff_round"])
    if rnd not in _APP_ROUND_TO_EVENT:
        raise ValueError(f"app export: unexpected playoff_round {rnd}")
    position = row["position"].strip()
    if position not in _APP_POSITIONS:
        raise ValueError(f"app export: unexpected position {position!r}")

    player_name = row.get("player_name", "").strip()
    nhl_team = row.get("nhl_team_name", "").strip()
    name = player_name if player_name and player_name != "null" else nhl_team
    team = "" if nhl_team == "null" else nhl_team
    manager = canonical_manager(row["manager"])

    return {
        "season": 2026,
        "source": "app",
        "league_name": league,
        "draft_event": _APP_ROUND_TO_EVENT[rnd],
        "manager": manager,
        "snake_slot": order.get((league, rnd), {}).get(manager),
        "pick_number": int(row["pick_number"]),
        "position": position,
        "slot_label": position,
        "player_or_team_name": name,
        "corrected_name": None,
        "team_name": team,
        "points_for_round": None,
        "points_when_drafted": None,
        "current_total_points": None,
        "status": None,
        "points_excluded": False,
        "ir_activated": False,
        "swap_partner": None,
        "note": None,
        "is_scored": True,
    }


# ── Result types ─────────────────────────────────────────────────────────


@dataclass
class TabReport:
    """Per-tab ingestion summary."""

    file: str
    season: int
    draft_event: str
    picks: int
    status_flags: int
    points_excluded: int
    ir_activated: int
    scored: bool


@dataclass
class LeagueDraftsResult:
    """Outcome of :func:`build_league_drafts`."""

    out_dir: Path
    picks: pd.DataFrame
    champions: pd.DataFrame
    tabs: list[TabReport] = field(default_factory=list)
    app_present: bool = False
    app_picks: int = 0

    def report_lines(self) -> list[str]:
        lines = [f"League drafts -> {self.out_dir}", f"  total picks: {len(self.picks)}"]
        for tab in self.tabs:
            scored = "scored" if tab.scored else "unscored"
            lines.append(
                f"  {tab.file}: {tab.season} {tab.draft_event} "
                f"[{scored}] {tab.picks} picks, "
                f"{tab.status_flags} flags, {tab.points_excluded} excluded, "
                f"{tab.ir_activated} activated"
            )
        if self.app_present:
            lines.append(f"  app-export-2026: {self.app_picks} picks (true pick order)")
        else:
            lines.append("  app-export-2026: ABSENT - parsing sheets only, no 2026 app data")
        lines.append(f"  champions: {len(self.champions)} seasons")
        return lines


@dataclass(frozen=True)
class _AppExportResult:
    present: bool
    records: list[dict[str, object]]


# ── Top-level ingestion ──────────────────────────────────────────────────


def _pick_frame(records: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(records, columns=list(PICK_COLUMNS))
    for column in _INT_COLUMNS:
        frame[column] = frame[column].astype("Int64")
    for column in _BOOL_COLUMNS:
        frame[column] = frame[column].astype(bool)
    return frame


def build_league_drafts(
    league_dir: Path = DEFAULT_LEAGUE_DRAFTS_DIR,
    out_dir: Path = DEFAULT_NORMALIZED_DIR,
) -> LeagueDraftsResult:
    """Parse all committed snapshots into ``league_picks`` / ``league_champions`` Parquet.

    App-export files are picked up by the ``app-export-2026__*.csv`` pattern; if absent,
    parsing proceeds on the sheets alone and the report says so.
    """
    if not league_dir.exists():
        raise FileNotFoundError(f"league-drafts directory not found: {league_dir}")

    all_records, tabs = _parse_sheet_tabs(league_dir)
    app_export = _parse_app_export(league_dir)
    all_records.extend(app_export.records)

    picks = _pick_frame(all_records)
    champions = build_champions(league_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    picks.to_parquet(out_dir / "league_picks.parquet", index=False)
    champions.to_parquet(out_dir / "league_champions.parquet", index=False)

    return LeagueDraftsResult(
        out_dir=out_dir,
        picks=picks,
        champions=champions,
        tabs=tabs,
        app_present=app_export.present,
        app_picks=len(app_export.records),
    )


def _parse_sheet_tabs(league_dir: Path) -> tuple[list[dict[str, object]], list[TabReport]]:
    all_records: list[dict[str, object]] = []
    tabs: list[TabReport] = []
    for name, season, event in SHEET_TABS:
        records = _parse_sheet_file(league_dir, name, season, event)
        tabs.append(_tab_report(name, season, event, records))
        all_records.extend(records)
    return all_records, tabs


def _parse_sheet_file(
    league_dir: Path, name: str, season: int, event: str
) -> list[dict[str, object]]:
    path = league_dir / name
    if not path.exists():
        raise FileNotFoundError(f"expected committed snapshot missing: {path}")
    return parse_sheet_tab(SheetTabRequest(read_csv_rows(path), season, event))


def _tab_report(name: str, season: int, event: str, records: list[dict[str, object]]) -> TabReport:
    return TabReport(
        file=name,
        season=season,
        draft_event=event,
        picks=len(records),
        status_flags=sum(1 for r in records if r["status"] is not None),
        points_excluded=sum(1 for r in records if r["points_excluded"]),
        ir_activated=sum(1 for r in records if r["ir_activated"]),
        scored=season != 2026,
    )


def _parse_app_export(league_dir: Path) -> _AppExportResult:
    app_picks_path = league_dir / "app-export-2026__draft-picks.csv"
    if not app_picks_path.exists():
        return _AppExportResult(False, [])
    app_order_path = league_dir / "app-export-2026__draft-order.csv"
    order = (
        parse_app_draft_order(_read_dict_rows(app_order_path)) if app_order_path.exists() else {}
    )
    records = parse_app_picks(_read_dict_rows(app_picks_path), order)
    return _AppExportResult(True, records)
