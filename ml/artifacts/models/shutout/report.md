# Shutout probability model (shutout-v1)

`P(the win is a shutout | a team wins this game)`, framed from the winning
team. Features are the winner's team-level goaltending proxies (season and
last-15-game save %, team shutout rate), the loser's goals-for per game, and
backup-save-% / starter-unavailability terms with explicit missing-flags. The
model is monotone in goalie quality. Shutout wins are worth 4 fantasy points
vs. 2 for a normal win, so this prices the goalie slot's upside (SPEC 1).

## Reproducibility
- Seed: 20260827
- Min pre-game regular-season games (winner): 5
- Save-% recency window: last 15 games
- Train seasons (end year): [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023] (9696 games)
- Validation seasons: [2024] (1319 games)
- Test seasons (held out): [2025, 2026] (2626 games)
- Splits are strictly temporal: no test-season game touches training or
  model selection (SPEC section 6).

## Model selection (validation Brier, lower is better)
- lightgbm: 0.0957
- logistic_regression: 0.0956  <- chosen

Chosen model: **logistic_regression** (lowest validation Brier).
It is refit on train + validation seasons before the held-out test.

## Base-rate shrinkage (validation-selected, US-105)
The raw model shows little to no held-out skill over the playoff base
rate (CODE_REVIEW observation), so a shrinkage weight `w` blending
`w*model + (1-w)*base_rate` is selected on the validation fold only
(never the held-out test). `w=1.0` keeps the pure model; `w=0.0`
collapses onto the base rate.

- Selected weight: **1.00** (no shrinkage -- pure model wins on validation)
- Shrinkage base rate (train+val shutout rate): 0.1151
- Validation Brier by weight (1.00 = pure model):
  - w=1.00: 0.0956  <- chosen
  - w=0.90: 0.0956
  - w=0.80: 0.0957
  - w=0.70: 0.0957
  - w=0.60: 0.0958
  - w=0.50: 0.0958
  - w=0.40: 0.0959
  - w=0.30: 0.0959
  - w=0.20: 0.0960
  - w=0.10: 0.0961
  - w=0.00: 0.0961

## Held-out test Brier vs. base-rate baseline
- shutout model (w=1.00): 0.0923
- shutout model (unshrunk, w=1.00):  0.0923
- baseline (train shutout rate 0.115): 0.0921
- Beats base rate: NO

## Calibration: predicted vs. observed shutout frequency (held out)
- Observed shutout rate:  0.1024
- Predicted shutout rate: 0.1047
- Relative error: 2.2% (target within +/-25%)
- Within target: yes

### Reliability bins (predicted bucket -> observed rate)
| predicted range | n | mean predicted | observed |
| --- | --- | --- | --- |
| 0.036-0.072 | 16 | 0.066 | 0.188 |
| 0.072-0.108 | 1631 | 0.098 | 0.102 |
| 0.108-0.145 | 969 | 0.116 | 0.102 |
| 0.145-0.181 | 10 | 0.155 | 0.000 |

