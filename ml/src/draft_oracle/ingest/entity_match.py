"""Match parsed league draft picks to NHL player/team ids (US-007 / PRD US-015).

US-006 (:mod:`draft_oracle.ingest.league_drafts`) produces a raw ``league_picks``
table whose player/team references are free-text sheet spellings. This module is
the second half of that pipeline: it resolves every pick to a stable NHL id and
emits the final ``league_draft_picks`` table.

What it does:

* **Skater slots** (``F`` / ``D`` / ``IR_F`` / ``IR_D``) resolve to an NHL
  ``player_id`` from ``players.parquet`` via normalized fuzzy name matching that
  survives accents, initials and small typos. Same-name collisions (there are two
  ``Sebastian Aho``s) are disambiguated by the pick's roster position.
* **Goalie / team slots** (``G``) resolve to an NHL ``team_id`` from
  ``teams.parquet`` — in this league a goalie pick is really a bet on a team's
  goalie situation, so the id is the team, not the netminder.
* **Managers** fold to a canonical id across seasons via a committed alias file
  (``data/overrides/manager_aliases.yaml``); ``evi`` = ``levi`` is owner-confirmed.
* **Low-confidence and unresolved names** are emitted to a reviewable report and
  are fixable via ``data/overrides/name_overrides.yaml`` — the honesty rule
  (SPEC §7) forbids closing a gap by dropping rows or weakening the bar.
* **Scored sheet picks** are cross-checked against archive playoff point splits.
  Because goals and assists are integer counts, the tolerance is exactly zero;
  a match is flagged only when ``points_when_drafted``, ``points_for_round``, and
  ``current_total_points`` all contradict the matched player's archive values.
* **Ownership validation** flags every copy of a player owned by more than one
  manager in the same league, season, and draft event. Duplicate source copies
  owned by the same manager are not conflicts.

The output ``league_draft_picks`` table keeps the season / draft_event / manager /
snake_slot / position / pick_number provenance plus the resolved ``player_id`` /
``team_id``, the points fields, the status flag, and the match diagnostics.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from draft_oracle.ingest import _entity_match_build as _entity_match_build_module
from draft_oracle.ingest.normalize import DEFAULT_NORMALIZED_DIR
from draft_oracle.ingest.odds import NHL_TEAMS, resolve_team_id

# ── Directory + threshold contract (SPEC §4/§7) ──────────────────────────

DEFAULT_OVERRIDES_DIR = Path("data/overrides")

# A fuzzy full-name match at or above this ratio is accepted without review.
HIGH_CONFIDENCE = 0.88
# A match between REVIEW_THRESHOLD and HIGH_CONFIDENCE is accepted but flagged
# for human review; below it the name is left unresolved (never force-matched).
REVIEW_THRESHOLD = 0.80
# A unique last-name fallback (e.g. bare "McDavid") is a confident structural
# match even when the full-string ratio is low; report it at this confidence.
LASTNAME_CONFIDENCE = 0.90

# Point columns and archive goals/assists are exact integer counts. A non-zero
# tolerance would hide real entity mismatches, so only equality counts as agreement.
POINT_CROSSCHECK_TOLERANCE = 0

# The four canonical Gemmell Cup managers (SCHEMA §6 / SPEC §2).
CANONICAL_MANAGERS: frozenset[str] = frozenset({"ben", "judah", "kyle", "levi"})

_SKATER_POSITIONS: frozenset[str] = frozenset({"F", "D", "IR_F", "IR_D"})

# (rounds scored by the event, rounds completed before the event's draft).
_DRAFT_EVENT_ROUNDS: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "R1": ((1,), ()),
    "R2": ((2,), (1,)),
    "R3_4": ((3, 4), (1, 2)),
}


# ── Name normalization ───────────────────────────────────────────────────


def normalize_name(raw: str | None) -> str:
    """Collapse a name to a compact match key.

    Accents are stripped (``Montréal`` → ``montreal``), case is folded, and every
    non-alphanumeric character is removed so initials and punctuation variants
    align (``J.T. Miller`` / ``JT Miller`` / ``J-T Miller`` → ``jtmiller``).
    """
    if raw is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(raw))
    ascii_name = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def name_tokens(raw: str | None) -> list[str]:
    """Split a name into lowercase ascii alphanumeric tokens (accent-stripped)."""
    if raw is None:
        return []
    decomposed = unicodedata.normalize("NFKD", str(raw))
    ascii_name = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", " ", ascii_name.lower()).split()


def last_name_key(raw: str | None) -> str:
    """Return the normalized final token of a name (its surname), or ``""``."""
    tokens = name_tokens(raw)
    return tokens[-1] if tokens else ""


# ── Manager alias resolution ─────────────────────────────────────────────


def load_manager_aliases(
    path: Path = DEFAULT_OVERRIDES_DIR / "manager_aliases.yaml",
) -> dict[str, str]:
    """Load ``manager_aliases.yaml`` into a surface-form → canonical-id map.

    The file maps each canonical id to its known aliases; this inverts it. Every
    canonical id also maps to itself. Fails loudly if the file is missing.
    """
    if not path.exists():
        raise FileNotFoundError(f"manager alias file not found: {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    aliases: dict[str, str] = {}
    for canonical, forms in raw.items():
        canon = str(canonical).strip().lower()
        aliases[canon] = canon
        for form in forms or []:
            aliases[str(form).strip().lower()] = canon
    return aliases


def resolve_manager(name: str, aliases: dict[str, str]) -> str:
    """Fold a raw manager label to its canonical id via ``aliases``.

    Unknown labels (e.g. the 2026 in-app league's other players) return their
    lowercased, stripped surface form so they are never silently merged.
    """
    key = name.strip().lower()
    return aliases.get(key, key)


# ── Name-override files ──────────────────────────────────────────────────


@dataclass(frozen=True)
class NameOverrides:
    """Manual raw-name → id overrides (normalized keys)."""

    players: dict[str, int] = field(default_factory=dict)
    teams: dict[str, int] = field(default_factory=dict)
    player_expected_matches: dict[str, int] = field(default_factory=dict)
    team_expected_matches: dict[str, int] = field(default_factory=dict)


def _load_override_section(
    raw_section: Mapping[str, Any], *, id_key: str
) -> tuple[dict[str, int], dict[str, int]]:
    ids: dict[str, int] = {}
    expected_matches: dict[str, int] = {}
    for raw_name, value in raw_section.items():
        name = normalize_name(raw_name)
        ids[name], expected = _override_id_and_expected(raw_name, value, id_key)
        if expected is not None:
            expected_matches[name] = expected
    return ids, expected_matches


def _override_id_and_expected(raw_name: str, value: Any, id_key: str) -> tuple[int, int | None]:
    if not isinstance(value, Mapping):
        return int(value), None
    if id_key not in value:
        raise ValueError(f"name override {raw_name!r} is missing {id_key!r}")
    expected = value.get("expected_matches")
    if expected is None:
        return int(value[id_key]), None
    count = int(expected)
    if count < 1:
        raise ValueError(f"name override {raw_name!r} expected_matches must be >= 1")
    return int(value[id_key]), count


def load_name_overrides(
    path: Path = DEFAULT_OVERRIDES_DIR / "name_overrides.yaml",
) -> NameOverrides:
    """Load ``name_overrides.yaml``; keys are normalized on load.

    A missing file yields empty maps (overrides are optional). Present-but-empty
    ``players`` / ``teams`` sections are allowed.
    """
    if not path.exists():
        return NameOverrides()
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    players, player_expected_matches = _load_override_section(
        raw.get("players") or {}, id_key="player_id"
    )
    teams, team_expected_matches = _load_override_section(raw.get("teams") or {}, id_key="team_id")
    return NameOverrides(
        players=players,
        teams=teams,
        player_expected_matches=player_expected_matches,
        team_expected_matches=team_expected_matches,
    )


def _effective_skater_name(row: Any) -> str:
    corrected = getattr(row, "corrected_name", None)
    if corrected is not None:
        text = str(corrected).strip()
        if pd.notna(corrected) and text:
            return str(corrected)
    return str(row.player_or_team_name)


def _team_candidates(team_name: str | None, raw_name: str | None) -> list[str]:
    return [c for c in (team_name, raw_name) if c is not None and str(c).strip()]


def _team_override_key(
    team_name: str | None, raw_name: str | None, overrides: NameOverrides
) -> str | None:
    for candidate in _team_candidates(team_name, raw_name):
        key = normalize_name(candidate)
        if key in overrides.teams:
            return key
    return None


def _validate_override_match_counts(league_picks: pd.DataFrame, overrides: NameOverrides) -> None:
    """Fail when a guarded override matches an unexpected league-pick count."""
    player_actual, team_actual = _override_match_counts(league_picks, overrides)
    _validate_expected_counts(
        player_actual,
        overrides.player_expected_matches,
        "name override",
        "league-pick match(es)",
    )
    _validate_expected_counts(
        team_actual,
        overrides.team_expected_matches,
        "team override",
        "G-slot league-pick match(es)",
    )


def _override_match_counts(
    league_picks: pd.DataFrame, overrides: NameOverrides
) -> tuple[dict[str, int], dict[str, int]]:
    player_actual = dict.fromkeys(overrides.player_expected_matches, 0)
    team_actual = dict.fromkeys(overrides.team_expected_matches, 0)
    for row in league_picks.itertuples(index=False):
        _count_override_match(row, overrides, player_actual, team_actual)
    return player_actual, team_actual


def _count_override_match(
    row: Any,
    overrides: NameOverrides,
    player_actual: dict[str, int],
    team_actual: dict[str, int],
) -> None:
    position = str(row.position)
    if position in _SKATER_POSITIONS:
        _increment_if_present(player_actual, normalize_name(_effective_skater_name(row)))
    elif position == "G":
        _increment_if_present(team_actual, _row_team_override_key(row, overrides))


def _increment_if_present(counts: dict[str, int], key: str | None) -> None:
    if key in counts:
        counts[str(key)] += 1


def _row_team_override_key(row: Any, overrides: NameOverrides) -> str | None:
    raw_name = str(row.player_or_team_name)
    raw_team_name = getattr(row, "team_name", None)
    team_name = (
        str(raw_team_name) if raw_team_name is not None and pd.notna(raw_team_name) else None
    )
    return _team_override_key(team_name, raw_name, overrides)


def _validate_expected_counts(
    actual: Mapping[str, int],
    expected_counts: Mapping[str, int],
    label: str,
    count_label: str,
) -> None:
    for key, expected in expected_counts.items():
        observed = actual[key]
        if observed != expected:
            raise ValueError(f"{label} {key!r} expected {expected} {count_label}, found {observed}")


# ── Team-id resolution (extends odds.resolve_team_id with nicknames) ──────


# Nickname-only sheet forms ("Panthers Goalie", "Jets") that odds.resolve_team_id
# does not cover (it keys on city + full name + abbrev). Built from the last word
# of each franchise's full name, with the multi-word nicknames listed explicitly.
def _build_nickname_index() -> dict[str, int]:
    index: dict[str, int] = {}
    for team in NHL_TEAMS:
        index.setdefault(normalize_name(team.full_name.split()[-1]), team.team_id)
    index.update(
        {
            "mapleleafs": 10,
            "leafs": 10,
            "redwings": 17,
            "wings": 17,
            "bluejackets": 29,
            "jackets": 29,
            "goldenknights": 54,
            "knights": 54,
            "hockeyclub": 59,
            "mammoth": 68,
        }
    )
    return index


_NICKNAME_INDEX: dict[str, int] = _build_nickname_index()


def resolve_team(
    team_name: str | None,
    raw_name: str | None = None,
    overrides: NameOverrides | None = None,
) -> int | None:
    """Resolve a goalie/team pick to an NHL ``team_id`` (``None`` if unknown).

    Resolution order: manual override, then ``odds.resolve_team_id`` (city / full
    name / abbrev), then a nickname fallback on the final word.
    """
    candidates = _team_candidates(team_name, raw_name)
    if overrides is not None:
        override_key = _team_override_key(team_name, raw_name, overrides)
        if override_key is not None:
            return overrides.teams[override_key]
    return _resolve_team_candidate(candidates) or _resolve_team_nickname(candidates)


def _resolve_team_candidate(candidates: list[str]) -> int | None:
    for candidate in candidates:
        team_id = resolve_team_id(candidate)
        if team_id is not None:
            return team_id
    return None


def _resolve_team_nickname(candidates: list[str]) -> int | None:
    for candidate in candidates:
        team_id = _resolve_nickname_tokens(candidate)
        if team_id is not None:
            return team_id
    return None


def _resolve_nickname_tokens(candidate: str) -> int | None:
    # Scan tokens (surname-first) so "Panthers Goalie" resolves on "panthers"
    # and two-word nicknames ("Maple Leafs") resolve on the distinctive word.
    for token in reversed(name_tokens(candidate)):
        nick = _NICKNAME_INDEX.get(token)
        if nick is not None:
            return nick
    return None


# ── Skater name index + fuzzy matching ───────────────────────────────────


@dataclass(frozen=True)
class PlayerCandidate:
    """A single NHL skater identity for matching."""

    player_id: int
    name: str
    norm: str
    last: str
    position: str


@dataclass
class PlayerIndex:
    """Lookup structures over the NHL skater pool."""

    candidates: list[PlayerCandidate]
    by_norm: dict[str, list[PlayerCandidate]]
    by_last: dict[str, list[PlayerCandidate]]
    id_to_name: dict[int, str]


def build_player_index(players: pd.DataFrame) -> PlayerIndex:
    """Build a :class:`PlayerIndex` from a normalized ``players`` frame."""
    candidates: list[PlayerCandidate] = []
    by_norm: dict[str, list[PlayerCandidate]] = {}
    by_last: dict[str, list[PlayerCandidate]] = {}
    id_to_name: dict[int, str] = {}
    for row in players.itertuples(index=False):
        name = str(row.player_name)
        cand = PlayerCandidate(
            player_id=_as_int(row.player_id),
            name=name,
            norm=normalize_name(name),
            last=last_name_key(name),
            position=str(row.position),
        )
        candidates.append(cand)
        by_norm.setdefault(cand.norm, []).append(cand)
        by_last.setdefault(cand.last, []).append(cand)
        id_to_name[cand.player_id] = name
    return PlayerIndex(
        candidates=candidates,
        by_norm=by_norm,
        by_last=by_last,
        id_to_name=id_to_name,
    )


@dataclass(frozen=True)
class Match:
    """The outcome of resolving one pick to an id."""

    entity_id: int | None
    matched_name: str | None
    method: str
    confidence: float
    needs_review: bool


def _position_pool(index: PlayerIndex, position: str) -> list[PlayerCandidate]:
    pool = [c for c in index.candidates if c.position == position]
    return pool or index.candidates


def match_skater(
    name: str,
    position: str,
    index: PlayerIndex,
    overrides: NameOverrides | None = None,
) -> Match:
    """Resolve a skater name to a ``player_id``.

    Order: override → exact normalized (position-disambiguated) → high-confidence
    fuzzy → unique last-name fallback → low-confidence fuzzy (review) → unresolved.
    """
    norm = normalize_name(name)
    override_match = _override_skater_match(norm, index, overrides)
    if override_match is not None:
        return override_match

    exact_match = _exact_skater_match(norm, position, index)
    if exact_match is not None:
        return exact_match

    pool = _position_pool(index, position)
    best, best_ratio = _best_fuzzy_candidate(norm, pool)
    if best is not None and best_ratio >= HIGH_CONFIDENCE:
        return Match(best.player_id, best.name, "fuzzy", round(best_ratio, 3), False)

    last_match = _last_name_match(name, pool)
    if last_match is not None:
        return last_match

    if best is not None and best_ratio >= REVIEW_THRESHOLD:
        return Match(best.player_id, best.name, "fuzzy-low", round(best_ratio, 3), True)

    return Match(None, None, "unmatched", round(best_ratio, 3), True)


def _override_skater_match(
    norm: str, index: PlayerIndex, overrides: NameOverrides | None
) -> Match | None:
    if overrides is None:
        return None
    override_id = overrides.players.get(norm)
    if override_id is None:
        return None
    return Match(override_id, index.id_to_name.get(override_id), "override", 1.0, False)


def _exact_skater_match(norm: str, position: str, index: PlayerIndex) -> Match | None:
    exact = index.by_norm.get(norm, [])
    if not exact:
        return None
    same_pos = [c for c in exact if c.position == position]
    chosen = same_pos or exact
    cand = chosen[0]
    return Match(cand.player_id, cand.name, "exact", 1.0, len(chosen) > 1)


def _best_fuzzy_candidate(
    norm: str, pool: list[PlayerCandidate]
) -> tuple[PlayerCandidate | None, float]:
    best = max(
        pool,
        key=lambda c: SequenceMatcher(None, norm, c.norm).ratio(),
        default=None,
    )
    best_ratio = SequenceMatcher(None, norm, best.norm).ratio() if best is not None else 0.0
    return best, best_ratio


def _last_name_match(name: str, pool: list[PlayerCandidate]) -> Match | None:
    last = last_name_key(name)
    last_hits = [c for c in pool if c.last == last] if last else []
    if len(last_hits) != 1:
        return None
    cand = last_hits[0]
    return Match(cand.player_id, cand.name, "lastname", LASTNAME_CONFIDENCE, False)


def match_team(
    team_name: str | None,
    raw_name: str | None,
    team_names: dict[int, str],
    overrides: NameOverrides | None = None,
) -> Match:
    """Resolve a goalie/team pick to a ``team_id``."""
    tid = resolve_team(team_name, raw_name, overrides)
    if tid is None:
        return Match(None, None, "unmatched", 0.0, True)
    return Match(tid, team_names.get(tid), "team", 1.0, False)


# ── Output table + report ────────────────────────────────────────────────

LEAGUE_DRAFT_PICK_COLUMNS: tuple[str, ...] = (
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
    "matched_name",
    "player_id",
    "team_id",
    "points_for_round",
    "points_when_drafted",
    "current_total_points",
    "status",
    "points_excluded",
    "ir_activated",
    "swap_partner",
    "note",
    "is_scored",
    "match_method",
    "match_confidence",
    "needs_review",
)

_INT_COLUMNS: tuple[str, ...] = (
    "season",
    "snake_slot",
    "pick_number",
    "player_id",
    "team_id",
    "points_for_round",
    "points_when_drafted",
    "current_total_points",
)
_BOOL_COLUMNS: tuple[str, ...] = (
    "points_excluded",
    "ir_activated",
    "is_scored",
    "needs_review",
)


@dataclass
class SeasonMatchReport:
    """Per-season matched/unmatched counts."""

    season: int
    total: int
    matched: int
    review: int

    @property
    def unmatched(self) -> int:
        return self.total - self.matched

    @property
    def match_rate(self) -> float:
        return self.matched / self.total if self.total else 1.0


@dataclass
class LeagueEntityMatchResult:
    """Outcome of :func:`build_league_draft_picks`."""

    out_dir: Path
    picks: pd.DataFrame
    seasons: list[SeasonMatchReport] = field(default_factory=list)
    review_path: Path | None = None
    duplicate_ownerships: int = 0
    duplicate_ownership_rows: int = 0
    point_mismatches: int = 0

    @property
    def total(self) -> int:
        return len(self.picks)

    @property
    def matched(self) -> int:
        return int(sum(s.matched for s in self.seasons))

    @property
    def match_rate(self) -> float:
        return self.matched / self.total if self.total else 1.0

    def report_lines(self) -> list[str]:
        lines = [
            f"League draft picks -> {self.out_dir}",
            f"  total picks: {self.total}",
            f"  matched: {self.matched} "
            f"({self.match_rate * 100:.1f}%)  unmatched: {self.total - self.matched}",
        ]
        for season in self.seasons:
            lines.append(
                f"  {season.season}: {season.matched}/{season.total} matched "
                f"({season.match_rate * 100:.1f}%), "
                f"{season.unmatched} unmatched, {season.review} to review"
            )
        lines.append(
            "  validation: "
            f"{self.duplicate_ownerships} duplicate-ownership asset(s) "
            f"across {self.duplicate_ownership_rows} row(s), "
            f"{self.point_mismatches} point-split mismatch(es)"
        )
        if self.review_path is not None:
            lines.append(f"  review report: {self.review_path}")
        else:
            lines.append("  review report: none (no low-confidence or unmatched picks)")
        return lines


def _is_matched(position: str, player_id: int | None, team_id: int | None) -> bool:
    if position == "G":
        return team_id is not None
    return player_id is not None


def _playoff_round(game_id: Any) -> int | None:
    """Return the best-of-seven round encoded in an NHL playoff ``game_id``."""
    text = str(game_id).strip()
    if len(text) != 10:
        return None
    if not text.isdigit():
        return None
    if text[7] not in "1234":
        return None
    return int(text[7])


def _archive_round_points(skater_games: pd.DataFrame) -> dict[tuple[int, int, int], int]:
    """Map ``(season_end_year, player_id, round)`` to archive goals + assists."""
    points: dict[tuple[int, int, int], int] = {}
    playoff_games = skater_games.loc[skater_games["game_type_id"].astype(int) == 3]
    for rec in playoff_games.to_dict("records"):
        playoff_round = _playoff_round(rec["game_id"])
        if playoff_round is None:
            continue
        key = (
            int(rec["season_id"]) % 10000,
            int(rec["player_id"]),
            playoff_round,
        )
        points[key] = points.get(key, 0) + int(rec["goals"]) + int(rec["assists"])
    return points


def _point_columns_contradict(
    record: dict[str, Any],
    archive_points: dict[tuple[int, int, int], int],
) -> bool:
    """Whether all three sheet point columns contradict the matched player.

    The zero-point tolerance is deliberate: every compared value is an exact integer
    goals-plus-assists count. Requiring all three comparisons to disagree avoids
    flagging legitimate sheet adjustments that perturb only one value while still
    catching a wrong entity whose before/event/total split is wholly incompatible.
    Goalie/team rows are deliberately skipped because their sheet points come from
    team wins and shutouts, while this archive cross-check uses skater goals and
    assists keyed by ``player_id``.
    """
    if not _can_crosscheck_points(record):
        return False
    columns = (
        record["points_for_round"],
        record["points_when_drafted"],
        record["current_total_points"],
    )
    if any(value is None for value in columns):
        return False
    event_rounds, prior_rounds = _DRAFT_EVENT_ROUNDS[str(record["draft_event"])]
    season = int(record["season"])
    player_id = int(record["player_id"])
    event_points = sum(
        archive_points.get((season, player_id, playoff_round), 0) for playoff_round in event_rounds
    )
    prior_points = sum(
        archive_points.get((season, player_id, playoff_round), 0) for playoff_round in prior_rounds
    )
    expected = (event_points, prior_points, event_points + prior_points)
    observed = tuple(int(value) for value in columns)
    return all(
        abs(actual - wanted) > POINT_CROSSCHECK_TOLERANCE
        for actual, wanted in zip(observed, expected, strict=True)
    )


def _can_crosscheck_points(record: dict[str, Any]) -> bool:
    if record["source"] != "sheet":
        return False
    if record["position"] == "G":
        return False
    if record["player_id"] is None:
        return False
    if not record["is_scored"]:
        return False
    return record["draft_event"] in _DRAFT_EVENT_ROUNDS


def _mark_duplicate_ownership(frame: pd.DataFrame) -> tuple[int, int]:
    """Flag assets owned by multiple managers within one league draft event."""
    conflicting_keys: list[tuple[Any, ...]] = []
    conflicting_rows: set[int] = set()
    asset_frames = (
        ("player_id", frame.loc[frame["player_id"].notna() & (frame["position"] != "G")]),
        ("team_id", frame.loc[frame["team_id"].notna() & (frame["position"] == "G")]),
    )
    for asset_column, assets in asset_frames:
        keys, rows = _conflicting_asset_ownerships(assets, asset_column)
        conflicting_keys.extend(keys)
        conflicting_rows.update(rows)
    if conflicting_rows:
        frame.loc[list(conflicting_rows), "needs_review"] = True
    return len(conflicting_keys), len(conflicting_rows)


def _conflicting_asset_ownerships(
    assets: pd.DataFrame, asset_column: str
) -> tuple[list[tuple[Any, ...]], set[int]]:
    group_columns = ["league_name", "season", "draft_event", asset_column]
    conflicting_keys: list[tuple[Any, ...]] = []
    conflicting_rows: set[int] = set()
    for key, group in assets.groupby(group_columns, dropna=False, sort=False):
        if group["manager"].nunique() > 1:
            conflicting_keys.append(key if isinstance(key, tuple) else (key,))
            conflicting_rows.update(int(index) for index in group.index)
    return conflicting_keys, conflicting_rows


def build_league_draft_picks(
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    overrides_dir: Path = DEFAULT_OVERRIDES_DIR,
    out_dir: Path = DEFAULT_NORMALIZED_DIR,
) -> LeagueEntityMatchResult:
    """Match ``league_picks`` to NHL ids and write ``league_draft_picks.parquet``."""
    return _entity_match_build_module.build_league_draft_picks(
        normalized_dir=normalized_dir,
        overrides_dir=overrides_dir,
        out_dir=out_dir,
    )


def _as_int(value: Any) -> int:
    return int(value)


def _to_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _picks_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records, columns=list(LEAGUE_DRAFT_PICK_COLUMNS))
    for column in _INT_COLUMNS:
        frame[column] = frame[column].astype("Int64")
    for column in _BOOL_COLUMNS:
        frame[column] = frame[column].astype(bool)
    frame["match_confidence"] = frame["match_confidence"].astype(float)
    return frame
