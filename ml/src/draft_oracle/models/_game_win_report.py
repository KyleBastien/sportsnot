"""Markdown report rendering for the per-game win model."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from draft_oracle.models.game_win import GameWinResult


def game_win_report_lines(result: GameWinResult, version: str) -> list[str]:
    lines = _game_win_report_intro(result, version)
    lines.extend(_game_win_model_selection_lines(result))
    lines.extend(_game_win_test_lines(result))
    lines.extend(_game_win_market_coverage_lines(result))
    lines.extend(_game_win_honest_note_lines(result))
    return lines


def _game_win_report_intro(result: GameWinResult, version: str) -> list[str]:
    cfg = result.config
    return [
        f"# Per-game win model ({version})",
        "",
        "Single-game `P(home beats away)` model, home/away aware, trained on",
        "historical regular-season and playoff games. Features are home-minus-away",
        "differences of a cross-season Elo rating and in-season regular-season rates,",
        "plus an optional de-vigged betting-market home probability.",
        "",
        "## Reproducibility",
        f"- Seed: {cfg.seed}",
        f"- Min pre-game regular-season games per team: {cfg.min_pregame_games}",
        f"- Train seasons (end year): {list(result.split.train_years)} "
        f"({result.n_train} games)",
        f"- Validation seasons: {list(result.split.val_years)} ({result.n_val} games)",
        f"- Test seasons (held out): {list(result.split.test_years)} "
        f"({result.n_test} games)",
        "- Splits are strictly temporal: no test-season game touches training or",
        "  model selection (SPEC section 6).",
        "",
        "## Model selection (validation Brier, lower is better)",
    ]


def _game_win_model_selection_lines(result: GameWinResult) -> list[str]:
    lines: list[str] = []
    for model_type, brier in sorted(result.val_brier_by_model.items()):
        marker = "  <- chosen" if model_type == result.chosen_model_type else ""
        lines.append(f"- {model_type}: {brier:.4f}{marker}")
    lines += [
        "",
        f"Chosen model: **{result.chosen_model_type}** (lowest validation Brier).",
        "It is refit on train + validation seasons before the held-out test.",
    ]
    return lines


def _game_win_test_lines(result: GameWinResult) -> list[str]:
    return [
        "",
        "## Held-out test Brier vs. fixed baselines",
        f"- market + stats model: {result.test_brier_market:.4f}",
        f"- stats-only model:     {result.test_brier_stats_only:.4f}",
        f"- baseline (a) coin flip:              {result.test_brier_coin_flip:.4f}",
        f"- baseline (b) higher reg-season pts:  {result.test_brier_higher_points:.4f}",
        "",
        f"- Beats coin flip: {'yes' if result.beats_coin_flip else 'NO'}",
        f"- Beats higher-points baseline: {'yes' if result.beats_higher_points else 'NO'}",
        f"- Beats both baselines: {'yes' if result.beats_both_baselines else 'NO'}",
        "",
        "## Ablation: does the market help? (test seasons with odds coverage)",
        f"- Test-set market coverage: {result.test_market_coverage:.1%} of games priced.",
        f"- market + stats Brier: {result.test_brier_market:.4f}",
        f"- stats-only Brier:     {result.test_brier_stats_only:.4f}",
        f"- Market improves Brier: {'yes' if result.market_helps else 'no'}"
        f" (delta {result.test_brier_stats_only - result.test_brier_market:+.4f}).",
        "",
        "## Market coverage by season",
        "Coverage uses the modeled rows after the pre-game-history filter.",
    ]


def _game_win_market_coverage_lines(result: GameWinResult) -> list[str]:
    lines: list[str] = []
    for year, coverage in sorted(result.market_coverage_by_season.items()):
        uncovered = " - uncovered" if coverage.uncovered else ""
        lines.append(
            f"- {year} ({coverage.split}): {coverage.priced_games}/"
            f"{coverage.total_games} games priced ({coverage.fraction:.1%})"
            f"{uncovered}"
        )
    lines.append("")
    return lines


def _game_win_honest_note_lines(result: GameWinResult) -> list[str]:
    if result.beats_both_baselines:
        return []
    return [
        "## Honest note on a missed target",
        "The headline model did not beat both baselines on this split. Reported",
        "as-is (SPEC section 7): baselines, splits, and seeds are unchanged. One",
        "plausible improvement: add rest/schedule-density and explicit goalie-",
        "availability features, plus probability calibration",
        "(isotonic / Platt) on the validation fold before scoring the test set.",
        "",
    ]
