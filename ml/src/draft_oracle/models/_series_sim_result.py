"""Result and reporting types for series simulator evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

SERIES_SIM_VERSION = "series-sim-v1"


@dataclass(frozen=True)
class SeriesCalibrationBin:
    """One predicted-P(higher-seed-wins) bucket: predicted vs. observed frequency."""

    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float


@dataclass(frozen=True)
class LengthBin:
    """Predicted vs. observed frequency for one series length (4/5/6/7)."""

    length: int
    predicted_rate: float
    observed_rate: float


@dataclass(frozen=True)
class SeriesSimConfig:
    """Evaluation knobs; every stochastic step is seeded (SPEC section 3)."""

    seed: int = 20260827
    n_test_seasons: int = 2
    calibration_bins: int = 5


@dataclass
class SeriesSimResult:
    """Outcome of the series-simulator calibration on held-out seasons."""

    config: SeriesSimConfig
    test_years: tuple[int, ...]
    n_series_scored: int
    n_series_skipped: int
    brier_series: float
    brier_higher_seed: float
    brier_coin_flip: float
    calibration_bins: list[SeriesCalibrationBin]
    length_bins: list[LengthBin]
    predicted_shutouts_by_round: dict[int, float]
    observed_shutouts_by_round: dict[int, int]

    @property
    def beats_higher_seed_baseline(self) -> bool:
        return self.brier_series < self.brier_higher_seed

    @property
    def beats_coin_flip(self) -> bool:
        return self.brier_series < self.brier_coin_flip

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable run summary (seed, split, metrics)."""
        return {
            "model_version": SERIES_SIM_VERSION,
            "seed": self.config.seed,
            "test_years": list(self.test_years),
            "counts": {
                "series_scored": self.n_series_scored,
                "series_skipped": self.n_series_skipped,
            },
            "brier": {
                "series_model": self.brier_series,
                "higher_seed_baseline": self.brier_higher_seed,
                "coin_flip_baseline": self.brier_coin_flip,
            },
            "beats_higher_seed_baseline": self.beats_higher_seed_baseline,
            "beats_coin_flip": self.beats_coin_flip,
            "series_winner_reliability": [
                {
                    "lower": bucket.lower,
                    "upper": bucket.upper,
                    "count": bucket.count,
                    "mean_predicted": bucket.mean_predicted,
                    "observed_rate": bucket.observed_rate,
                }
                for bucket in self.calibration_bins
            ],
            "series_length_distribution": [
                {
                    "length": bucket.length,
                    "predicted_rate": bucket.predicted_rate,
                    "observed_rate": bucket.observed_rate,
                }
                for bucket in self.length_bins
            ],
            "shutouts_by_round": {
                str(playoff_round): {
                    "predicted": self.predicted_shutouts_by_round.get(playoff_round, 0.0),
                    "observed": self.observed_shutouts_by_round.get(playoff_round, 0),
                }
                for playoff_round in sorted(
                    set(self.predicted_shutouts_by_round)
                    | set(self.observed_shutouts_by_round)
                )
            },
        }

    def report_lines(self) -> list[str]:
        """Human-readable calibration report (Markdown; ASCII only)."""
        lines = _report_intro(self)
        lines.extend(_reliability_lines(self.calibration_bins))
        lines.extend(_length_lines(self.length_bins))
        lines.extend(
            _shutout_lines(
                self.predicted_shutouts_by_round,
                self.observed_shutouts_by_round,
            )
        )
        lines.extend(_honesty_note(self.n_series_scored))
        return lines


def _report_intro(result: SeriesSimResult) -> list[str]:
    cfg = result.config
    return [
        f"# Best-of-7 series simulator ({SERIES_SIM_VERSION})",
        "",
        "Composes the per-game win model (US-011) and shutout model (US-012) into a",
        "full best-of-7 outcome distribution with the 2-2-1-1-1 home-ice pattern. The",
        "distribution is enumerated exactly over all series paths (no Monte Carlo). Per",
        "series it yields P(win series), the 4/5/6/7-game length distribution, E[wins],",
        "E[games], and E[goalie-slot points] scored through the rules engine (a shutout",
        "win replaces a normal win: 4 pts vs 2).",
        "",
        "## Reproducibility",
        f"- Seed: {cfg.seed}",
        f"- Held-out test seasons (end year): {list(result.test_years)}",
        "- The per-game win and shutout models are trained ONLY on seasons before the",
        "  held-out set; test-season series never touch training (SPEC section 6).",
        f"- Series scored: {result.n_series_scored} (skipped for missing pre-series "
        f"state: {result.n_series_skipped}).",
        "",
        "## Series-winner calibration (held out)",
        "Brier score for P(higher seed wins the series), lower is better:",
        f"- series simulator:        {result.brier_series:.4f}",
        f"- baseline higher seed=1:  {result.brier_higher_seed:.4f}",
        f"- baseline coin flip=0.5:  {result.brier_coin_flip:.4f}",
        f"- Beats higher-seed baseline: {'yes' if result.beats_higher_seed_baseline else 'NO'}",
        f"- Beats coin flip: {'yes' if result.beats_coin_flip else 'NO'}",
        "",
    ]


def _reliability_lines(bins: list[SeriesCalibrationBin]) -> list[str]:
    lines = [
        "### Reliability bins (predicted P(higher seed wins) -> observed)",
        "| predicted range | n | mean predicted | observed |",
        "| --- | --- | --- | --- |",
    ]
    for bucket in bins:
        lines.append(
            f"| {bucket.lower:.2f}-{bucket.upper:.2f} | {bucket.count} | "
            f"{bucket.mean_predicted:.3f} | {bucket.observed_rate:.3f} |"
        )
    return lines


def _length_lines(bins: list[LengthBin]) -> list[str]:
    lines = [
        "",
        "## Series-length distribution: predicted vs. observed",
        "| games | predicted | observed |",
        "| --- | --- | --- |",
    ]
    for length_bin in bins:
        lines.append(
            f"| {length_bin.length} | {length_bin.predicted_rate:.3f} | "
            f"{length_bin.observed_rate:.3f} |"
        )
    return lines


def _shutout_lines(
    predicted_by_round: dict[int, float],
    observed_by_round: dict[int, int],
) -> list[str]:
    lines = [
        "",
        "## Shutouts per playoff round: predicted E[shutouts] vs. observed",
        "| round | predicted | observed |",
        "| --- | --- | --- |",
    ]
    for playoff_round in sorted(set(predicted_by_round) | set(observed_by_round)):
        predicted = predicted_by_round.get(playoff_round, 0.0)
        observed = observed_by_round.get(playoff_round, 0)
        lines.append(f"| {playoff_round} | {predicted:.2f} | {observed} |")
    return lines


def _honesty_note(n_series_scored: int) -> list[str]:
    return [
        "",
        "## Honesty note (SPEC section 7)",
        f"Metrics are reported exactly as measured. With {n_series_scored} playoff "
        "series held out the",
        "sample is small, so the series-winner Brier is noisy and may not beat the",
        "higher-seed baseline every split; the number is printed as-is. Series prices",
        "are unavailable, so per-game probabilities come from the stat-only win model.",
        "",
    ]


def _held_out_years(series: pd.DataFrame, n_test: int) -> tuple[int, ...]:
    years = sorted({int(year) for year in series["year"].dropna().unique()})
    return tuple(years[-n_test:]) if n_test > 0 else ()
