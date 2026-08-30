"""Injury return-time model and availability adjustment (US-015, PRD US-011 part 2).

Prices *availability* for injured skaters: ``P(available for game k)``, ``k = 1..7``
of the upcoming best-of-7 round, per injured player. Downstream, a skater's round
projection multiplies expected games played by the resulting availability haircut
and the IR-stash valuation prices how long a stash sits out.

Why absence spells (SPEC section 5). ESPN cannot supply *historical* injuries -- old
game summaries resolve their ``injuries`` block against **today's** rosters, so any
training-season pull leaks the future (odds-archive/PROVENANCE.md section 10). The
return-time model is therefore calibrated on **absence spells** derived from the
committed NHL archive (the normalized ``skater_games`` / ``team_games`` tables, 11
seasons 2015-16..2025-26): for each established skater, a maximal run of consecutive
team games they missed *between two appearances* is one real missed-game spell with a
known return timing -- no external feed, no leakage.

Honest caveats (SPEC section 7). Spells conflate injuries with healthy scratches; the
derivation mitigates that with documented filters -- a minimum spell length
(``min_spell``, single-game gaps are usually scratches), a minimum appearance count
(``min_appearances``, established regulars only), and a minimum median ice time
(``min_median_toi``, top-9/top-6 skaters, not fourth-line scratch fodder). Because the
archive carries no injury *status* label, the map from a live status
(``day_to_day`` / ``out`` / ``ir``) to an expected absence is a **documented
status-based assumption** (:data:`STATUS_MEAN_GAMES`, NHL-informed): the archive
distribution supplies the return-timing *shape* (dispersion, tail) and the status map
supplies its *location* (mean). The Dec 2025 - June 2026 as-of-game ``injuries`` blocks
in ``odds-archive/espn-2025-26-completion/raw/summary/`` are the designated labeled
validation slice; here the model is calibrated and its survival curve checked on a
strictly temporal hold-out of the archive spells themselves.

Overrides are the final authority. An ``injuries.yaml`` entry may pin an explicit
``return_game`` -- the round game a player is expected back -- which takes precedence
over the model (:func:`project_availability`): the player is unavailable for games
before it and available from it on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from draft_oracle.ingest.entity_match import normalize_name
from draft_oracle.ingest.injuries import (
    STATUS_DAY_TO_DAY,
    STATUS_HEALTHY,
    STATUS_IR,
    STATUS_OUT,
    InjuryOverride,
)
from draft_oracle.provenance import add_git_provenance

__all__ = [
    "DEFAULT_HORIZON",
    "RETURN_TIME_MODEL_VERSION",
    "STATUS_MEAN_GAMES",
    "AbsenceSpellConfig",
    "AvailabilityRow",
    "ReturnTimeConfig",
    "ReturnTimeModel",
    "ReturnTimeResult",
    "availability_from_return_game",
    "derive_absence_spells",
    "fit_return_time_model",
    "project_availability",
    "spells_from_sequence",
    "train_return_time_from_normalized",
    "train_return_time_model",
]

RETURN_TIME_MODEL_VERSION = "return-time-v1"

REGULAR_SEASON_GAME_TYPE = 2
DEFAULT_HORIZON = 7  # best-of-7 round (SPEC section 1)

# Documented status -> mean absence (games) assumption (SPEC section 7). The archive
# spell distribution supplies the SHAPE; these NHL-informed means supply the LOCATION.
# day-to-day ~ back within a game; "out" ~ a few games; IR/LTIR ~ a week-plus of games.
STATUS_MEAN_GAMES: dict[str, float] = {
    STATUS_DAY_TO_DAY: 1.0,
    STATUS_OUT: 3.0,
    STATUS_IR: 8.0,
}

_SPELL_COLUMNS: tuple[str, ...] = (
    "season_id",
    "team_abbrev",
    "player_id",
    "spell_length",
    "median_toi_seconds",
    "n_appearances",
)


# ── Absence-spell derivation (the calibration data) ──────────────────────


@dataclass(frozen=True)
class AbsenceSpellConfig:
    """Filters that turn appearance gaps into credible injury spells.

    Every threshold is a documented healthy-scratch guard (SPEC section 7):

    * ``min_spell`` -- ignore gaps shorter than this many games (a single missed
      game is usually a healthy scratch, not an injury). This biases the retained
      distribution toward genuine absences; the bias is intentional and reported.
    * ``min_appearances`` -- the player must appear in at least this many of the
      team's games that season to count as an established regular.
    * ``min_median_toi`` -- the player's median ice time across appearances must
      clear this floor (seconds), excluding fringe skaters whose gaps are scratches.
    * ``min_team_games`` -- skip teams with too few games to bookend a spell.
    """

    min_spell: int = 2
    min_appearances: int = 20
    min_median_toi: float = 600.0
    min_team_games: int = 40


def spells_from_sequence(present: list[bool], min_spell: int) -> list[int]:
    """Bookended missed-game run lengths from a team's appear/miss sequence.

    ``present[i]`` is whether the player played the team's i-th game. Only runs of
    missed games that fall *between two appearances* are returned (a run is closed by
    a later appearance, so the player provably came back). Leading gaps (before the
    first appearance -- pre-debut/trade) and trailing gaps (after the last -- season
    ends / season-ending injury with no observed return) are excluded. Runs shorter
    than ``min_spell`` are dropped as likely healthy scratches.
    """
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
    """Derive injury absence spells from normalized archive tables.

    For each ``(season, team)`` the team's regular-season games are ordered
    chronologically; each established skater's appearances mark which games they
    played; a maximal bookended run of missed games is one spell (see
    :func:`spells_from_sequence`). Returns one row per spell with its length in games
    and the sample-size / ice-time context that admitted it.
    """
    config = config or AbsenceSpellConfig()
    sg = skater_games.loc[skater_games["game_type_id"] == REGULAR_SEASON_GAME_TYPE]
    tg = team_games.loc[team_games["game_type_id"] == REGULAR_SEASON_GAME_TYPE]

    rows: list[dict[str, Any]] = []
    for (season, team), team_grp in tg.groupby(["season_id", "team_abbrev"], sort=False):
        game_seq = _team_game_sequence(team_grp)
        if len(game_seq) < config.min_team_games:
            continue
        season_id = int(season)  # type: ignore[call-overload]
        team_abbrev = str(team)
        players = sg.loc[(sg["season_id"] == season) & (sg["team_abbrev"] == team)]
        for player_id, player_games in players.groupby("player_id", sort=False):
            result = _spells_for_team_player(game_seq, player_games, config)
            if result is None:
                continue
            n_app, median_toi, spells = result
            for length in spells:
                rows.append(
                    {
                        "season_id": season_id,
                        "team_abbrev": team_abbrev,
                        "player_id": player_id,
                        "spell_length": int(length),
                        "median_toi_seconds": median_toi,
                        "n_appearances": int(n_app),
                    }
                )
    return pd.DataFrame(rows, columns=list(_SPELL_COLUMNS))


# ── Fitted return-time model ─────────────────────────────────────────────


@dataclass
class ReturnTimeModel:
    """Return-timing distribution fit on archive absence spells.

    The retained spell lengths are the empirical distribution of a genuine injury's
    total games missed. :meth:`availability_curve` conditions that distribution on a
    live status (rescaled to :data:`STATUS_MEAN_GAMES`) and, optionally, on games
    already missed, yielding a non-decreasing ``P(available for game k)`` over the
    round horizon.
    """

    spell_lengths: tuple[int, ...]
    horizon: int
    status_mean_games: dict[str, float]

    @property
    def n_spells(self) -> int:
        return len(self.spell_lengths)

    def base_mean(self) -> float:
        """Mean archive spell length (games); ``1.0`` if no spells were retained."""
        if not self.spell_lengths:
            return 1.0
        return float(np.mean(np.asarray(self.spell_lengths, dtype=float)))

    def survival(self, missed: int) -> float:
        """``P(L > missed)`` on the raw archive spell distribution (calibration check)."""
        if not self.spell_lengths:
            return 0.0
        arr = np.asarray(self.spell_lengths, dtype=float)
        return float(np.mean(arr > float(missed)))

    def _total_absence_samples(self, status: str) -> np.ndarray:
        """Status-scaled total-absence samples (games), rounded and floored at 1."""
        mean_games = self.status_mean_games.get(status, STATUS_MEAN_GAMES[STATUS_OUT])
        if not self.spell_lengths:
            return np.asarray([max(1, round(mean_games))], dtype=int)
        scale = mean_games / self.base_mean()
        scaled = np.rint(np.asarray(self.spell_lengths, dtype=float) * scale)
        return np.clip(scaled, 1.0, None).astype(int)

    def _remaining_samples(self, status: str, games_missed: int) -> np.ndarray:
        """Remaining-absence samples given ``games_missed`` already sat out."""
        total = self._total_absence_samples(status)
        if games_missed <= 0:
            return total
        remaining = total[total >= games_missed] - games_missed
        if remaining.size == 0:
            # Out longer than any comparable spell -> assume an imminent return.
            return np.asarray([0], dtype=int)
        return remaining

    def availability_curve(self, status: str = STATUS_OUT, games_missed: int = 0) -> list[float]:
        """``P(available for game k)`` for ``k = 1..horizon`` (non-decreasing).

        A player is available for round game ``k`` once their remaining absence is at
        most ``k - 1`` games, so the curve is the empirical CDF of the remaining-games
        distribution and is monotonically non-decreasing in ``k``.
        """
        if status == STATUS_HEALTHY:
            return [1.0] * self.horizon
        remaining = self._remaining_samples(status, games_missed)
        return [float(np.mean(remaining <= (k - 1))) for k in range(1, self.horizon + 1)]

    def expected_games_available(self, status: str = STATUS_OUT, games_missed: int = 0) -> float:
        """Expected games available over the horizon ``= sum_k P(available game k)``."""
        return float(sum(self.availability_curve(status, games_missed)))

    def availability_multiplier(self, status: str = STATUS_OUT, games_missed: int = 0) -> float:
        """Availability haircut in ``[0, 1]`` = expected available / horizon."""
        return self.expected_games_available(status, games_missed) / float(self.horizon)


def availability_from_return_game(return_game: int, horizon: int) -> list[float]:
    """Deterministic curve for an override-pinned return game.

    The player is unavailable (``0``) for games before ``return_game`` and available
    (``1``) from it on; ``return_game <= 1`` means available all round.
    """
    return [1.0 if k >= return_game else 0.0 for k in range(1, horizon + 1)]


# ── Availability projection (model + override precedence) ─────────────────


@dataclass(frozen=True)
class AvailabilityRow:
    """Per-player availability projection over the round horizon."""

    player_id: Any
    player_name: str | None
    status: str
    curve: tuple[float, ...]
    expected_games_available: float
    availability_multiplier: float
    source: str  # "override" | "model" | "healthy"


def _match_override(
    overrides: list[InjuryOverride], player_id: Any, player_name: Any
) -> InjuryOverride | None:
    """Best override for a player: exact ``espn_id`` first, else normalized name."""
    name_key = normalize_name(str(player_name)) if player_name is not None else None
    by_name: InjuryOverride | None = None
    for override in overrides:
        if (
            override.espn_id is not None
            and player_id is not None
            and int(override.espn_id) == int(player_id)
        ):
            return override
        if (
            by_name is None
            and override.player
            and name_key is not None
            and normalize_name(override.player) == name_key
        ):
            by_name = override
    return by_name


def _availability_for_row(
    row: dict[Any, Any],
    model: ReturnTimeModel,
    overrides: list[InjuryOverride],
    horizon: int,
) -> AvailabilityRow:
    status = str(row.get("status") or STATUS_OUT)
    player_id = row.get("player_id")
    player_name = row.get("player_name")

    override = _match_override(overrides, player_id, player_name)
    if override is not None and override.return_game is not None:
        curve = availability_from_return_game(int(override.return_game), horizon)
        source = "override"
    elif status == STATUS_HEALTHY:
        curve = [1.0] * horizon
        source = "healthy"
    else:
        curve = model.availability_curve(status)
        source = "model"

    expected = float(sum(curve))
    return AvailabilityRow(
        player_id=player_id,
        player_name=None if player_name is None else str(player_name),
        status=status,
        curve=tuple(curve),
        expected_games_available=expected,
        availability_multiplier=expected / float(horizon),
        source=source,
    )


def project_availability(
    injuries: pd.DataFrame,
    model: ReturnTimeModel,
    *,
    overrides: list[InjuryOverride] | None = None,
    horizon: int | None = None,
) -> pd.DataFrame:
    """Project per-player availability over the round; overrides win.

    For each injury row, an ``injuries.yaml`` override that pins ``return_game`` takes
    precedence (deterministic curve); otherwise the status-conditioned model curve is
    used. Returns one row per player with the per-game probabilities
    (``p_available_g1..gH``), ``expected_games_available``, ``availability_multiplier``
    (the haircut applied to expected games in projection composition), and the
    decision ``source``.
    """
    overrides = overrides if overrides is not None else []
    horizon = horizon if horizon is not None else model.horizon

    records: list[dict[str, Any]] = []
    for row in injuries.to_dict("records"):
        av = _availability_for_row(row, model, overrides, horizon)
        record: dict[str, Any] = {
            "player_id": av.player_id,
            "player_name": av.player_name,
            "status": av.status,
            "expected_games_available": av.expected_games_available,
            "availability_multiplier": av.availability_multiplier,
            "source": av.source,
        }
        for k in range(1, horizon + 1):
            record[f"p_available_g{k}"] = av.curve[k - 1]
        records.append(record)

    columns = [
        "player_id",
        "player_name",
        "status",
        *[f"p_available_g{k}" for k in range(1, horizon + 1)],
        "expected_games_available",
        "availability_multiplier",
        "source",
    ]
    return pd.DataFrame(records, columns=columns)


# ── Training / calibration (report + manifest) ───────────────────────────


@dataclass(frozen=True)
class ReturnTimeConfig:
    """Training knobs; deterministic given the archive (no stochastic step)."""

    seed: int = 20260827
    n_test_seasons: int = 2
    horizon: int = DEFAULT_HORIZON
    spell_config: AbsenceSpellConfig = field(default_factory=AbsenceSpellConfig)
    status_mean_games: dict[str, float] = field(default_factory=lambda: dict(STATUS_MEAN_GAMES))


@dataclass
class ReturnTimeResult:
    """Outcome of fitting the return-time model on archive spells."""

    model: ReturnTimeModel
    config: ReturnTimeConfig
    train_years: tuple[int, ...]
    test_years: tuple[int, ...]
    n_spells_total: int
    n_spells_train: int
    n_spells_test: int
    mean_spell: float
    median_spell: float
    p90_spell: float
    per_season_counts: list[tuple[int, int]]
    calibration_mae: float
    calibration_bins: list[tuple[int, float, float]]

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable run summary (config, splits, calibration)."""
        return {
            "model_version": RETURN_TIME_MODEL_VERSION,
            "seed": self.config.seed,
            "horizon": self.config.horizon,
            "status_mean_games": self.config.status_mean_games,
            "spell_filters": {
                "min_spell": self.config.spell_config.min_spell,
                "min_appearances": self.config.spell_config.min_appearances,
                "min_median_toi": self.config.spell_config.min_median_toi,
                "min_team_games": self.config.spell_config.min_team_games,
            },
            "split": {
                "train_years": list(self.train_years),
                "test_years": list(self.test_years),
            },
            "counts": {
                "spells_total": self.n_spells_total,
                "spells_train": self.n_spells_train,
                "spells_test": self.n_spells_test,
            },
            "spell_distribution": {
                "mean": self.mean_spell,
                "median": self.median_spell,
                "p90": self.p90_spell,
            },
            "calibration_mae": self.calibration_mae,
            "calibration_bins": [
                {"missed": m, "predicted_survival": pred, "observed_survival": obs}
                for m, pred, obs in self.calibration_bins
            ],
        }

    def report_lines(self) -> list[str]:
        """Human-readable calibration report (Markdown; ASCII only)."""
        cfg = self.config
        lines = [
            f"# Injury return-time model ({RETURN_TIME_MODEL_VERSION})",
            "",
            "Prices `P(available for game k)`, k=1..7, for injured skaters. ESPN cannot",
            "supply historical injuries (leakage), so the model is calibrated on ABSENCE",
            "SPELLS derived from the NHL archive: bookended runs of consecutive team games",
            "an established skater missed between two appearances.",
            "",
            "## Healthy-scratch guards (documented filters)",
            f"- Minimum spell length: {cfg.spell_config.min_spell} games "
            "(single-game gaps are usually healthy scratches; this biases the retained",
            "  distribution toward genuine absences -- intentional and reported here).",
            f"- Minimum appearances: {cfg.spell_config.min_appearances} "
            "(established regulars only).",
            f"- Minimum median TOI: {cfg.spell_config.min_median_toi:g} seconds "
            "(top-9/6 skaters, not scratch fodder).",
            "",
            "## Absence-spell distribution (games missed per spell)",
            f"- Spells retained: {self.n_spells_total}",
            f"- Mean: {self.mean_spell:.2f} | median: {self.median_spell:.1f} "
            f"| p90: {self.p90_spell:.1f}",
            "",
            "## Status -> mean-absence assumption (SPEC section 7)",
            "The archive has no status label, so status maps to a documented mean absence;",
            "the archive supplies the timing SHAPE, the status map supplies the LOCATION:",
        ]
        for status, mean in sorted(cfg.status_mean_games.items()):
            lines.append(f"- {status}: {mean:g} games")
        lines += [
            "",
            "## Temporal calibration (survival on held-out seasons)",
            f"- Train seasons (end year): {list(self.train_years)} ({self.n_spells_train} spells)",
            f"- Test seasons (held out):  {list(self.test_years)} ({self.n_spells_test} spells)",
            "- Predicted vs observed `P(L > m)` on the test seasons (lower gap is better):",
        ]
        for missed, pred, obs in self.calibration_bins:
            lines.append(f"  - missed > {missed}: predicted {pred:.3f} / observed {obs:.3f}")
        lines += [
            "",
            f"- Mean absolute calibration error: {self.calibration_mae:.4f}",
            "",
            "## Labeled validation slice (future work)",
            "The Dec 2025 - June 2026 as-of-game `injuries` blocks under",
            "`odds-archive/espn-2025-26-completion/raw/summary/` are the designated labeled",
            "validation slice; this report calibrates on a temporal hold-out of the archive",
            "spells themselves, reported honestly (SPEC section 7).",
            "",
        ]
        return lines


def _spell_percentiles(spells: np.ndarray) -> tuple[float, float, float]:
    if spells.size == 0:
        return 0.0, 0.0, 0.0
    return (
        float(np.mean(spells)),
        float(np.median(spells)),
        float(np.percentile(spells, 90)),
    )


def _calibration(
    train_spells: np.ndarray, test_spells: np.ndarray, horizon: int
) -> tuple[float, list[tuple[int, float, float]]]:
    """Predicted (train) vs observed (test) survival ``P(L > m)`` for m=1..horizon."""
    bins: list[tuple[int, float, float]] = []
    diffs: list[float] = []
    for missed in range(1, horizon + 1):
        pred = float(np.mean(train_spells > missed)) if train_spells.size else 0.0
        obs = float(np.mean(test_spells > missed)) if test_spells.size else 0.0
        bins.append((missed, pred, obs))
        diffs.append(abs(pred - obs))
    mae = float(np.mean(diffs)) if diffs else float("nan")
    return mae, bins


def fit_return_time_model(
    spells: pd.DataFrame, *, horizon: int = DEFAULT_HORIZON
) -> ReturnTimeModel:
    """Fit a :class:`ReturnTimeModel` from a derived absence-spell frame."""
    lengths = tuple(int(x) for x in spells["spell_length"]) if not spells.empty else ()
    return ReturnTimeModel(
        spell_lengths=lengths,
        horizon=horizon,
        status_mean_games=dict(STATUS_MEAN_GAMES),
    )


def train_return_time_model(
    skater_games: pd.DataFrame,
    team_games: pd.DataFrame,
    *,
    config: ReturnTimeConfig | None = None,
) -> ReturnTimeResult:
    """Derive absence spells, fit the model, and evaluate temporal calibration.

    The shipped model is fit on all seasons; calibration holds out the newest
    ``n_test_seasons`` and compares predicted vs observed spell-length survival there,
    reported honestly (SPEC section 7).
    """
    config = config or ReturnTimeConfig()
    spells = derive_absence_spells(skater_games, team_games, config=config.spell_config)
    if spells.empty:
        raise ValueError("no absence spells derived; loosen AbsenceSpellConfig filters")

    spells = spells.copy()
    spells["season_end_year"] = (spells["season_id"] % 10000).astype(int)
    years = sorted(int(y) for y in spells["season_end_year"].unique())
    n_test = min(config.n_test_seasons, max(1, len(years) - 1))
    test_years = tuple(years[-n_test:])
    train_years = tuple(years[:-n_test])

    all_lengths = spells["spell_length"].to_numpy(dtype=float)
    train_lengths = spells.loc[
        spells["season_end_year"].isin(train_years), "spell_length"
    ].to_numpy(dtype=float)
    test_lengths = spells.loc[spells["season_end_year"].isin(test_years), "spell_length"].to_numpy(
        dtype=float
    )

    mean_spell, median_spell, p90_spell = _spell_percentiles(all_lengths)
    calibration_mae, calibration_bins = _calibration(train_lengths, test_lengths, config.horizon)
    per_season = [(int(y), int((spells["season_end_year"] == y).sum())) for y in years]

    model = ReturnTimeModel(
        spell_lengths=tuple(int(x) for x in all_lengths),
        horizon=config.horizon,
        status_mean_games=dict(config.status_mean_games),
    )

    return ReturnTimeResult(
        model=model,
        config=config,
        train_years=train_years,
        test_years=test_years,
        n_spells_total=len(all_lengths),
        n_spells_train=len(train_lengths),
        n_spells_test=len(test_lengths),
        mean_spell=mean_spell,
        median_spell=median_spell,
        p90_spell=p90_spell,
        per_season_counts=per_season,
        calibration_mae=calibration_mae,
        calibration_bins=calibration_bins,
    )


DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_MODEL_ARTIFACT_DIR = Path("artifacts/models/return-time")


def train_return_time_from_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Path = DEFAULT_MODEL_ARTIFACT_DIR,
    config: ReturnTimeConfig | None = None,
) -> ReturnTimeResult:
    """Load normalized Parquet tables, fit, and write the report + manifest."""
    skater_games = pd.read_parquet(normalized_dir / "skater_games.parquet")
    team_games = pd.read_parquet(normalized_dir / "team_games.parquet")

    result = train_return_time_model(skater_games, team_games, config=config)
    manifest = add_git_provenance(result.manifest())

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text(
        "\n".join(result.report_lines()) + "\n", encoding="utf-8"
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result
