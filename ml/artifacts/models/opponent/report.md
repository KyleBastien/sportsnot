# Opponent model (US-020)

## Fitted opponent model

- total historical picks: 552
- league coefficients: rank +0.143, affinity +2.423
- per-manager models: 7 (min picks 20)

| manager | picks | rank beta | affinity beta |
| --- | ---: | ---: | ---: |
| ben | 105 | -0.106 | +2.399 |
| connor.fehr | 33 | +0.078 | +1.616 |
| judah | 105 | -0.178 | +1.720 |
| kyle | 138 | +0.215 | +2.361 |
| levi | 105 | +0.178 | +1.374 |
| paul.markhauser | 33 | +0.078 | +1.425 |
| tobi | 33 | +0.078 | +1.104 |

## Held-out validation

Roster-membership accuracy (leave-one-season-out): the fraction of each manager's actual roster the model reproduces given the true snake order and drafted pool. Compared against the greedy best-available fallback.

| season | events | picks | fitted | greedy | fitted wins |
| --- | ---: | ---: | ---: | ---: | :---: |
| 2024 | 3 | 108 | 0.269 | 0.194 | yes |
| 2025 | 2 | 88 | 0.261 | 0.216 | yes |
| 2026 | 3 | 233 | 0.180 | 0.159 | yes |

Seasons where fitted beats the fallback: 3/3.

### Per-pick accuracy (true-order app export)

- picks scored: 143
- top-1: fitted 0.126 vs greedy 0.112
- top-3: fitted 0.217 vs greedy 0.203
