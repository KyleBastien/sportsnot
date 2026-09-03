"""Value-over-replacement (VOR), positional scarcity, and the cheat sheet (US-018).

Projections (US-016/017) rank players *within* a position, but a draft board must
compare a forward, a defenseman, and a goalie slot (an entire NHL team's
goaltending, SPEC section 1) on one axis. VOR does that by pricing each asset
against the *replacement level* of its position -- the value of the best player at
that position you could still get for free once every manager has filled that slot.

Replacement level is a pure function of the roster shape and the league size ``N``
(SPEC section 1: ``5 F, 3 D, 1 G`` active, ``+1 IR_F, +1 IR_D`` when the league
enables IR):

* Forwards: the ``(5N + 1)``-th ranked forward (``(6N + 1)``-th with IR).
* Defensemen: the ``(3N + 1)``-th ranked defenseman (``(4N + 1)``-th with IR).
* Goalie/team slot: the ``(N + 1)``-th ranked team (IR adds no goalie slot).

When fewer assets remain than the demand (e.g. the final round with only two teams
alive, or a tiny pool), there is no free replacement to be had, so the replacement
level falls back to ``0.0`` -- every remaining asset then prices at its full
projection. ``VOR = expected_points - replacement_level`` is computed for every
skater and team; the cheat sheet is the union of both pools sorted by VOR.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

__all__ = [
    "CHEATSHEET_COLUMNS",
    "DEFAULT_DEFENSE_SLOTS",
    "DEFAULT_FORWARD_SLOTS",
    "DEFAULT_GOALIE_SLOTS",
    "IR_EXTRA_DEFENSE",
    "IR_EXTRA_FORWARD",
    "CheatSheet",
    "RosterDemand",
    "VorConfig",
    "build_cheatsheet",
    "render_cheatsheet_markdown",
    "replacement_level",
    "roster_demand",
    "write_cheatsheet",
]

# Active-roster slots per manager (SPEC section 1).
DEFAULT_FORWARD_SLOTS = 5
DEFAULT_DEFENSE_SLOTS = 3
DEFAULT_GOALIE_SLOTS = 1  # the goalie slot is an entire team's goaltending

# Extra slots each manager fills when the league enables IR (no IR goalie slot).
IR_EXTRA_FORWARD = 1
IR_EXTRA_DEFENSE = 1

# Fixed, deterministic column order for the cheat-sheet table.
CHEATSHEET_COLUMNS: tuple[str, ...] = (
    "rank",
    "position",
    "name",
    "team",
    "projection",
    "p10",
    "p50",
    "p90",
    "replacement",
    "vor",
    "injured",
)


@dataclass(frozen=True)
class RosterDemand:
    """Starter demand (slots per manager) that sets each replacement level."""

    forwards_per_manager: int
    defense_per_manager: int
    goalies_per_manager: int


def roster_demand(ir: bool) -> RosterDemand:
    """Per-manager slot demand for the standard (``5F/3D/1G``) or IR roster."""
    if ir:
        return RosterDemand(
            forwards_per_manager=DEFAULT_FORWARD_SLOTS + IR_EXTRA_FORWARD,
            defense_per_manager=DEFAULT_DEFENSE_SLOTS + IR_EXTRA_DEFENSE,
            goalies_per_manager=DEFAULT_GOALIE_SLOTS,
        )
    return RosterDemand(
        forwards_per_manager=DEFAULT_FORWARD_SLOTS,
        defense_per_manager=DEFAULT_DEFENSE_SLOTS,
        goalies_per_manager=DEFAULT_GOALIE_SLOTS,
    )


@dataclass(frozen=True)
class VorConfig:
    """League parameters that drive replacement levels and the sheet layout."""

    managers: int = 4
    ir: bool = False

    def __post_init__(self) -> None:
        if self.managers < 1:
            raise ValueError(f"managers must be >= 1, got {self.managers}")

    @property
    def demand(self) -> RosterDemand:
        """Per-manager slot demand implied by this league's IR setting."""
        return roster_demand(self.ir)


def replacement_level(values: Sequence[float], starters: int) -> float:
    """Replacement value = the ``(starters + 1)``-th best of ``values``.

    ``starters`` is the total demand across the league (slots-per-manager times the
    number of managers). Values are ranked high-to-low; the replacement is the first
    asset *past* the starter demand, i.e. the best one still freely available. When
    the demand meets or exceeds the supply there is no free replacement, so the level
    is ``0.0`` and every asset prices at its full projection.
    """
    if starters < 0:
        raise ValueError(f"starters must be >= 0, got {starters}")
    ranked = sorted((float(v) for v in values), reverse=True)
    if starters >= len(ranked):
        return 0.0
    return ranked[starters]


def _skater_records(skaters: pd.DataFrame) -> list[dict[str, Any]]:
    """Normalize the projection artifact's skater table into cheat-sheet rows."""
    if skaters is None or skaters.empty:
        return []
    rows: list[dict[str, Any]] = []
    for rec in skaters.to_dict("records"):
        rows.append(
            {
                "position": str(rec["position"]),
                "name": str(rec.get("player_name", "")),
                "team": str(rec.get("team_abbrev", "")),
                "projection": float(rec["expected_points"]),
                "p10": float(rec["p10"]) if pd.notna(rec.get("p10")) else float("nan"),
                "p50": float(rec["p50"]) if pd.notna(rec.get("p50")) else float("nan"),
                "p90": float(rec["p90"]) if pd.notna(rec.get("p90")) else float("nan"),
                "injured": bool(rec.get("injured", False)),
            }
        )
    return rows


def _team_records(teams: pd.DataFrame) -> list[dict[str, Any]]:
    """Normalize the projection artifact's team table into goalie-slot rows.

    A team pick is a bet on the whole team's goaltending, so its projection is the
    expected goalie-slot points (``e_goalie_points``). Teams carry no per-game
    quantiles in the artifact, so those are left blank on the sheet.
    """
    if teams is None or teams.empty:
        return []
    rows: list[dict[str, Any]] = []
    for rec in teams.to_dict("records"):
        rows.append(
            {
                "position": "G",
                "name": str(rec.get("team_abbrev", "")),
                "team": str(rec.get("team_abbrev", "")),
                "projection": float(rec["e_goalie_points"]),
                "p10": float("nan"),
                "p50": float("nan"),
                "p90": float("nan"),
                "injured": False,
            }
        )
    return rows


@dataclass
class CheatSheet:
    """VOR-priced draft board plus the replacement levels that produced it."""

    managers: int
    ir: bool
    demand: RosterDemand
    replacement_forward: float
    replacement_defense: float
    replacement_goalie: float
    rows: pd.DataFrame
    ir_section: list[str] = field(default_factory=list)
    note: str = ""

    def summary(self) -> dict[str, Any]:
        """JSON-serialisable scarcity summary for the run manifest."""
        return {
            "managers": self.managers,
            "ir": self.ir,
            "roster_demand": {
                "forwards_per_manager": self.demand.forwards_per_manager,
                "defense_per_manager": self.demand.defense_per_manager,
                "goalies_per_manager": self.demand.goalies_per_manager,
            },
            "replacement_level": {
                "F": self.replacement_forward,
                "D": self.replacement_defense,
                "G": self.replacement_goalie,
            },
            "assets": len(self.rows),
        }

    def report_lines(self) -> list[str]:
        """Human-readable cheat sheet (Markdown; ASCII only, SPEC honesty rules)."""
        return render_cheatsheet_markdown(self).splitlines()


def _cheatsheet_replacements(
    skater_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    demand: RosterDemand,
    managers: int,
) -> tuple[float, float, float]:
    """Per-position replacement levels for the cheat-sheet pool."""
    forward_vals = [r["projection"] for r in skater_rows if r["position"] == "F"]
    defense_vals = [r["projection"] for r in skater_rows if r["position"] == "D"]
    team_vals = [r["projection"] for r in team_rows]
    repl_f = replacement_level(forward_vals, demand.forwards_per_manager * managers)
    repl_d = replacement_level(defense_vals, demand.defense_per_manager * managers)
    repl_g = replacement_level(team_vals, demand.goalies_per_manager * managers)
    return repl_f, repl_d, repl_g


def _cheatsheet_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Sort priced rows into the ranked cheat-sheet frame (empty-safe)."""
    if not rows:
        return pd.DataFrame({col: pd.Series(dtype="object") for col in CHEATSHEET_COLUMNS})
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(
        ["vor", "projection", "name"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    frame.insert(0, "rank", range(1, len(frame) + 1))
    frame = frame[list(CHEATSHEET_COLUMNS)]
    frame["injured"] = frame["injured"].astype(bool)
    return frame


def build_cheatsheet(
    skaters: pd.DataFrame,
    teams: pd.DataFrame,
    *,
    config: VorConfig,
) -> CheatSheet:
    """Price every skater and team by VOR and return the sorted cheat sheet.

    Replacement levels come from ``config`` (league size + IR); each asset's VOR is
    its projection minus its position's replacement level. Rows are sorted by VOR
    descending, breaking ties by projection then name so the board is deterministic.
    """
    demand = config.demand
    n = config.managers

    skater_rows = _skater_records(skaters)
    team_rows = _team_records(teams)

    repl_f, repl_d, repl_g = _cheatsheet_replacements(skater_rows, team_rows, demand, n)
    repl_by_pos = {"F": repl_f, "D": repl_d, "G": repl_g}

    rows = [*skater_rows, *team_rows]
    for r in rows:
        repl = repl_by_pos[r["position"]]
        r["replacement"] = repl
        r["vor"] = r["projection"] - repl

    return CheatSheet(
        managers=n,
        ir=config.ir,
        demand=demand,
        replacement_forward=repl_f,
        replacement_defense=repl_d,
        replacement_goalie=repl_g,
        rows=_cheatsheet_frame(rows),
    )


def _fmt(value: Any) -> str:
    """Format a projection/VOR cell: two decimals, ``-`` for missing quantiles."""
    is_nan = isinstance(value, float) and value != value
    if value is None or is_nan:
        return "-"
    return f"{float(value):.2f}"


def render_cheatsheet_markdown(sheet: CheatSheet) -> str:
    """Render the cheat sheet as an ASCII Markdown document.

    The IR flag changes the layout: the header states the roster shape and, when IR
    is enabled, injured skaters are tagged ``IR?`` (an IR-stash candidate) in the
    Status column instead of the plain ``OUT`` used without IR.
    """
    demand = sheet.demand
    ir_label = "on" if sheet.ir else "off"
    lines: list[str] = [
        "# Draft Oracle cheat sheet",
        "",
        f"- League size: {sheet.managers} manager(s)",
        f"- IR slots: {ir_label}",
        (
            "- Roster demand per manager: "
            f"{demand.forwards_per_manager} F / "
            f"{demand.defense_per_manager} D / "
            f"{demand.goalies_per_manager} G (team)"
        ),
        "- Replacement level (points):"
        f" F {sheet.replacement_forward:.2f}"
        f" / D {sheet.replacement_defense:.2f}"
        f" / G {sheet.replacement_goalie:.2f}",
        "",
        "Sorted by value over replacement (VOR). The G rows are whole-team goalie",
        "slots and carry no per-game quantiles.",
        "",
    ]
    if sheet.note:
        lines.extend([f"> {sheet.note}", ""])
    lines.extend([
        "| Rank | Pos | Player | Team | Proj | p10 | p50 | p90 | Repl | VOR | Status |",
        "| ---: | :-- | :----- | :--- | ---: | --: | --: | --: | ---: | --: | :----- |",
    ])

    for rec in sheet.rows.to_dict("records"):
        injured = bool(rec["injured"])
        status = "" if not injured else "IR?" if sheet.ir else "OUT"
        lines.append(
            "| {rank} | {pos} | {name} | {team} | {proj} | {p10} | {p50} | {p90} "
            "| {repl} | {vor} | {status} |".format(
                rank=int(rec["rank"]),
                pos=str(rec["position"]),
                name=str(rec["name"]),
                team=str(rec["team"]),
                proj=_fmt(rec["projection"]),
                p10=_fmt(rec["p10"]),
                p50=_fmt(rec["p50"]),
                p90=_fmt(rec["p90"]),
                repl=_fmt(rec["replacement"]),
                vor=_fmt(rec["vor"]),
                status=status,
            )
        )

    _append_ir_section(lines, sheet)
    return "\n".join(lines) + "\n"


def _append_ir_section(lines: list[str], sheet: CheatSheet) -> None:
    """Append the pre-rendered IR-stash section (US-022) when the sheet carries one."""
    if sheet.ir_section:
        lines.extend(sheet.ir_section)


def write_cheatsheet(sheet: CheatSheet, path: Path) -> Path:
    """Write ``cheatsheet.md`` to ``path`` (parent created if needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_cheatsheet_markdown(sheet), encoding="utf-8")
    return path
