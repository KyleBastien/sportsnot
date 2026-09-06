# NHL shift-chart archive

This directory contains compact, deterministic NHL shift-chart snapshots for
2007-08 through 2025-26. The snapshots cover regular-season and playoff games
listed in the adjacent `nhl-archive/game-times-<season>.csv.gz` files. Derived
tables provide skater deployment, line combinations, power-play units, and
dressed lineups without live HTTP access.

Data comes from the NHL's public Stats REST API. Seasons or individual games
whose REST response lacks ordinary shifts use the NHL's public HTML
home/visitor time-on-ice reports.
See `PROVENANCE.md` for endpoints, probe results, coverage, validation, and
checksums. NHL data attribution: National Hockey League.

## Re-fetch

Run from `ml/` with the project Python environment:

```powershell
.venv/Scripts/python.exe data/raw/nhl-shifts/fetch_shifts.py --probe
.venv/Scripts/python.exe data/raw/nhl-shifts/fetch_shifts.py --probe-html
.venv/Scripts/python.exe data/raw/nhl-shifts/fetch_shifts.py
.venv/Scripts/python.exe data/raw/nhl-shifts/derive_deployment.py
```

`fetch_shifts.py` uses curl, one request per second, four attempts, and
exponential backoff. Raw responses live in ignored `cache/` files. Existing
cache files are never downloaded again. Keep that local cache to resume an
interrupted run and re-verify committed `cache-manifest-<season>.csv.gz`
hashes.

All committed gzip files use a zero modification time and stable row order.
Re-running fetch and derivation from an unchanged cache emits byte-identical
files.
