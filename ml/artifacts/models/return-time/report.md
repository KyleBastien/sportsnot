# Injury return-time model (return-time-v1)

Prices `P(available for game k)`, k=1..7, for injured skaters. ESPN cannot
supply historical injuries (leakage), so the model is calibrated on ABSENCE
SPELLS derived from the NHL archive: bookended runs of consecutive team games
an established skater missed between two appearances.

## Healthy-scratch guards (documented filters)
- Minimum spell length: 2 games (single-game gaps are usually healthy scratches; this biases the retained
  distribution toward genuine absences -- intentional and reported here).
- Minimum appearances: 20 (established regulars only).
- Minimum median TOI: 600 seconds (top-9/6 skaters, not scratch fodder).

## Absence-spell distribution (games missed per spell)
- Spells retained: 10470
- Mean: 6.19 | median: 4.0 | p90: 14.0

## Status -> mean-absence assumption (SPEC section 7)
The archive has no status label, so status maps to a documented mean absence;
the archive supplies the timing SHAPE, the status map supplies the LOCATION:
- day_to_day: 1 games
- ir: 8 games
- out: 3 games

## Temporal calibration (survival on held-out seasons)
- Train seasons (end year): [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024] (8611 spells)
- Test seasons (held out):  [2025, 2026] (1859 spells)
- Predicted vs observed `P(L > m)` on the test seasons (lower gap is better):
  - missed > 1: predicted 1.000 / observed 1.000
  - missed > 2: predicted 0.696 / observed 0.722
  - missed > 3: predicted 0.520 / observed 0.551
  - missed > 4: predicted 0.405 / observed 0.437
  - missed > 5: predicted 0.336 / observed 0.360
  - missed > 6: predicted 0.277 / observed 0.306
  - missed > 7: predicted 0.237 / observed 0.255

- Mean absolute calibration error: 0.0230

## Labeled validation slice (future work)
The Dec 2025 - June 2026 as-of-game `injuries` blocks under
`odds-archive/espn-2025-26-completion/raw/summary/` are the designated labeled
validation slice; this report calibrates on a temporal hold-out of the archive
spells themselves, reported honestly (SPEC section 7).

