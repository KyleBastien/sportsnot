# Natural Stat Trick raw snapshot

Collection attempted from public pages at
`https://www.naturalstattrick.com/` for offline Draft Oracle feature work. The first
request received HTTP 403 from a Cloudflare challenge, so policy required an immediate
stop. This directory currently contains only the failure report, exact fetch/stop
records, and cached challenge response. It contains no statistics tables or fetcher.

See `PROVENANCE.md` before any future run. Do not retry until the owner chooses a
site-approved access path. Do not spoof a browser, solve or bypass the challenge, change
IP to evade it, or use subscriber-only data.

Future fetch tooling must be reviewed after access is explicitly approved. Tier 2 must
run only after a complete Tier 1 snapshot is committed and only when Tier 1 has shown no
HTTP 403 or 429. Natural Stat Trick must be credited when its data is used.

**Decision (2026-09-06):** NaturalStatTrick is dropped as a source. See
`tasks/prd-ml-model-improvements.md` Decisions §7; deployment data comes from the
NHL API's shift charts and TOI reports instead (US-504, `ml/data/raw/nhl-shifts/`).
