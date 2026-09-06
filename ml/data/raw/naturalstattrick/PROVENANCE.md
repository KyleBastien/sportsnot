# Provenance — Natural Stat Trick raw archive

## 2026-09-05 blocked fetch attempt

Snapshot collection stopped before any data page was obtained. Natural Stat Trick
returned **HTTP 403** on the first request. Per collection policy, the run made no retry,
did not change its User-Agent or IP, and made no further Natural Stat Trick requests.

Attempt time: **2026-09-06T01:34:51Z** (2026-09-05 America/Los_Angeles).

User-Agent:

```text
SportsNot/1.0 (+https://github.com/KyleBastien/sportsnot)
```

Exact requested URL:

```text
https://www.naturalstattrick.com/playerteams.php?fromseason=20232024&thruseason=20232024&stype=2&sit=all&stdoi=std&score=all&rate=n&team=ALL&pos=S&loc=B&toi=0&gpfilt=none&fd=&td=&tgp=410&lines=single
```

Response:

- status: `403`
- uncompressed response bytes: `6,455`
- cached before inspection at
  `raw-html/errors/raw-html__2023-24__2__skaters-all.attempt-1.status-403.html.gz`
- committed gzip SHA256:
  `786ae5e222970f0ea8cfb85a329783f8ca34fc8e60fe387013a6ada839c076cf`
- page title: `Just a moment...`
- response references `https://challenges.cloudflare.com`; this is a Cloudflare
  challenge page, not the requested statistics table

The request is also recorded in `fetch-log.csv.gz`; `STOP_REASON.json` is the
machine-readable stop record.

## Collection outcome

- Tier 1 successful pages: **0 / 494 requested report pages**
- Tier 1 parsed tables: **0**
- Tier 2 game pages: **0 / 1,700**
- player mappings: **not produced**
- retries: **0**
- HTTP 429 responses: **0**
- HTTP 503 responses: **0**
- HTTP 403 responses: **1**

Tier 2 is prohibited after a Tier 1 HTTP 403 and was not attempted. No substitution,
imputation, browser impersonation, captcha solving, proxying, or paywall/premium access
was attempted.

## Parameters and availability

Site report forms could not be opened because the first request was blocked. Therefore
the candidate parameter set used by the blocked request remains **unverified against the
site's own forms** and no availability claim is made for any report or season.

No Natural Stat Trick statistical data is committed in this directory. Downstream code
must treat the snapshot as unavailable and must never infer that an empty table means a
zero value.
