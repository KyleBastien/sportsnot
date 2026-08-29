# Opponent model (US-020)

## Fitted opponent model

- total historical picks: 480
- league coefficients: rank +0.160, affinity +2.850
- per-manager models: 7 (min picks 20)

| manager | picks | rank beta | affinity beta |
| --- | ---: | ---: | ---: |
| ben | 87 | -0.083 | +2.424 |
| connor.fehr | 33 | +0.088 | +1.770 |
| judah | 87 | -0.150 | +1.538 |
| kyle | 120 | +0.232 | +1.448 |
| levi | 87 | +0.185 | +1.168 |
| paul.markhauser | 33 | +0.088 | +1.807 |
| tobi | 33 | +0.088 | +1.773 |

## Held-out validation

Roster-membership accuracy (leave-one-season-out): the fraction of each manager's actual roster the model reproduces given the true snake order and drafted pool. Compared against the greedy best-available fallback.

| season | events | picks | fitted | greedy | fitted wins |
| --- | ---: | ---: | ---: | ---: | :---: |
| 2024 | 3 | 108 | 0.222 | 0.194 | yes |
| 2025 | 2 | 88 | 0.273 | 0.216 | yes |
| 2026 | 6 | 240 | 0.308 | 0.292 | yes |

Seasons where fitted beats the fallback: 3/3.

### Per-pick accuracy (true-order app export)

- picks scored: 240
- top-1: fitted 0.113 vs greedy 0.104
- top-3: fitted 0.208 vs greedy 0.204
