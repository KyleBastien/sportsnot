# Per-game win model (game-win-v1)

Single-game `P(home beats away)` model, home/away aware, trained on
historical regular-season and playoff games. Features are home-minus-away
differences of a cross-season Elo rating and in-season regular-season rates,
plus an optional de-vigged betting-market home probability.

## Reproducibility
- Seed: 20260827
- Min pre-game regular-season games per team: 5
- Train seasons (end year): [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023] (8892 games)
- Validation seasons: [2024] (1232 games)
- Test seasons (held out): [2025, 2026] (2421 games)
- Splits are strictly temporal: no test-season game touches training or
  model selection (SPEC section 6).

## Model selection (validation Brier, lower is better)
- lightgbm: 0.2402
- logistic_regression: 0.2383  <- chosen

Chosen model: **logistic_regression** (lowest validation Brier).
It is refit on train + validation seasons before the held-out test.

## Held-out test Brier vs. fixed baselines
- market + stats model: 0.2410
- stats-only model:     0.2413
- baseline (a) coin flip:              0.2500
- baseline (b) higher reg-season pts:  0.4450

- Beats coin flip: yes
- Beats higher-points baseline: yes
- Beats both baselines: yes

## Ablation: does the market help? (test seasons with odds coverage)
- Test-set market coverage: 34.3% of games priced.
- market + stats Brier: 0.2410
- stats-only Brier:     0.2413
- Market improves Brier: yes (delta +0.0003).

