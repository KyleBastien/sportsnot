# Natural Stat Trick snapshot fetch failure

## Summary

Natural Stat Trick snapshot collection failed on the first HTTP request. The site
returned `403 Forbidden` with a Cloudflare challenge page instead of the requested
statistics table. Collection policy required an immediate stop on HTTP 403, captcha,
or blocked page. No retry or workaround was attempted.

No Natural Stat Trick statistics were collected. Tier 1 remains incomplete and Tier 2
was not started.

## Timeline

| Time (UTC) | Event |
|---|---|
| 2026-09-06T01:34:43Z | Fetch process started with the required project User-Agent. |
| 2026-09-06T01:34:51Z | First response received and cached before inspection. |
| 2026-09-06T01:34:51Z | Response identified as HTTP 403 and run stopped. |

The UTC date is 2026-09-06; local date in America/Los_Angeles was 2026-09-05.

## Request

User-Agent:

```text
SportsNot/1.0 (+https://github.com/KyleBastien/sportsnot)
```

URL:

```text
https://www.naturalstattrick.com/playerteams.php?fromseason=20232024&thruseason=20232024&stype=2&sit=all&stdoi=std&score=all&rate=n&team=ALL&pos=S&loc=B&toi=0&gpfilt=none&fd=&td=&tgp=410&lines=single
```

Response evidence:

- HTTP status: `403`
- response size: `6,455` uncompressed bytes
- page title: `Just a moment...`
- page references `https://challenges.cloudflare.com`
- cached response:
  `raw-html/errors/raw-html__2023-24__2__skaters-all.attempt-1.status-403.html.gz`
- cached gzip SHA256:
  `786ae5e222970f0ea8cfb85a329783f8ca34fc8e60fe387013a6ada839c076cf`
- machine-readable stop record: `STOP_REASON.json`
- request audit record: `fetch-log.csv.gz`

## Why collection failed

Immediate cause: Natural Stat Trick's edge protection rejected the non-browser HTTP
client and returned a Cloudflare challenge instead of report HTML.

Evidence supports an access-layer rejection:

1. HTTP status was 403, not a report-level validation response.
2. Response title was `Just a moment...`, not a Natural Stat Trick report title.
3. Response loaded Cloudflare challenge resources.
4. No report table was present to parse.

The evidence does **not** prove that the proposed report parameters were valid or
invalid. Cloudflare stopped the request before a usable report response was obtained.
The site's own report forms could not be inspected, so parameter verification was also
blocked.

## Policy response

Collection followed the task's non-negotiable stop rules:

- one process and one thread
- required User-Agent used without browser spoofing
- initial request delayed by more than five seconds
- response cached before content inspection
- exact URL, status, byte count, timestamp, and cache path logged
- zero retries after HTTP 403
- no User-Agent change
- no IP change, proxy, VPN, captcha solver, browser automation, or cookie reuse
- no login, subscriber feature, premium feature, or paywall bypass
- no Tier 2 requests after Tier 1 showed HTTP 403

## Scope impact

| Output | Result |
|---|---:|
| Tier 1 report pages | 0 / 494 successful |
| Tier 1 parsed tables | 0 |
| Tier 2 playoff game pages | 0 / 1,700 attempted |
| Tier 2 parsed tables | 0 |
| Player mappings | 0 |
| Unmatched-player report | not produced |

US-504's Natural Stat Trick ingestion bullet remains blocked. US-507 deployment and
shot-quality features, US-510 lineup-derived availability, and US-512 in-series lineup
dynamics cannot use this source snapshot. FR-7's committed, offline-source requirement
is not satisfied for Natural Stat Trick.

MoneyPuck and NHL archive data remain unchanged. They were not silently substituted for
missing Natural Stat Trick tables.

## Safe recovery paths

Any next attempt needs a source-approved access path. Acceptable options:

1. Ask Natural Stat Trick for permission and a bulk data export or documented automated
   access method compatible with the project User-Agent and request cadence.
2. Obtain a public, redistribution-permitted archive directly from Natural Stat Trick.
3. Amend the PRD to use another public source whose license and access policy permit a
   committed offline snapshot.
4. Retry the same compliant request later only after explicit owner authorization. A
   retry may still receive the same Cloudflare block.

Browser impersonation, challenge solving, residential proxies, IP rotation, or premium
account scraping are not acceptable recovery paths.
