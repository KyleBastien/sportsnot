# Provenance — sealed The Odds API NHL history

Acquired **2026-09-05** for US-502. The plaintext working tree remained under the
Windows temporary directory, outside this repository. Only the seven encrypted season
archives, scripts, and this provenance are committed.

## 1. Source, plan, and terms boundary

Source: The Odds API v4 historical odds endpoint:

```text
GET https://api.the-odds-api.com/v4/historical/sports/icehockey_nhl/odds
```

Parameters were `regions=us,eu`, `dateFormat=iso`, `oddsFormat=decimal`, a requested
historical `date`, and either:

- playoff: `markets=h2h,spreads,totals`;
- regular season: `markets=h2h`.

The API key came only from `ODDS_API_KEY` in the process environment or ignored
`ml/.env`. It was never printed or written to a request log. Logged request parameters
exclude `apiKey`; a post-run scan found zero `apiKey` strings in all 1,665 bulk log
records.

The subscription was the 100,000-credit monthly plan. The v4 documentation checked on
2026-09-05 states that historical featured-market requests cost:

```text
10 × requested markets × requested regions
```

It also states that the endpoint returns the closest snapshot at or before `date`,
featured history begins June 6, 2020, and snapshots are normally ten minutes apart
before September 2022 and five minutes apart afterward.

The Odds API terms prohibit redistributing its data as downloadable files. Therefore
no raw response, index, flat line file, or per-game probability is committed in clear
text. The owner still needs to retain written confirmation from The Odds API for this
encrypted-at-rest arrangement.

Documentation:

- <https://the-odds-api.com/liveapi/guides/v4/>
- <https://the-odds-api.com/historical-odds-data/>
- <https://the-odds-api.com/sports-odds-data/bookmaker-apis.html>

## 2. Probe results

`GET /v4/sports?all=true` was free and returned three keys containing
`icehockey_nhl`:

| Key | Active | `has_outrights` |
|---|---:|---:|
| `icehockey_nhl` | yes | no |
| `icehockey_nhl_championship_winner` | yes | yes |
| `icehockey_nhl_preseason` | no | no |

The featured-market probe used game 2023030141, CAR–NYI on 2024-04-20. The committed
NHL archive start was `2024-04-20T21:00:00Z`; the requested time was one hour earlier,
`2024-04-20T20:00:00Z`.

| Field | Observed value |
|---|---|
| returned `timestamp` | `2024-04-20T19:55:38Z` |
| `previous_timestamp` | `2024-04-20T19:50:38Z` |
| `next_timestamp` | `2024-04-20T20:00:39Z` |
| events in snapshot | 8 |
| bookmaker entries across snapshot | 196 |
| API event commence time | `2024-04-20T21:10:00Z` |
| books on exact event | 25 |
| market presence by book | `h2h` 25, `spreads` 16, `totals` 15 |

Matchbook also returned `h2h_lay`, although only the three featured markets were
requested. The parser preserves every returned market in the validation-only flat
table while the index flags only `h2h`, `spreads`, and `totals`.

Observed US-region book keys were `draftkings`, `bovada`, `betmgm`, `pointsbetus`,
`mybookieag`, `fanduel`, `betrivers`, `unibet_us`, `lowvig`, `betonlineag`,
`williamhill_us`, `superbook`, `betus`, and `wynnbet`.

Observed EU-region book keys were `onexbet`, `marathonbet`, `betclic`, `mybookieag`,
`nordicbet`, `betsson`, `livescorebet_eu`, `betonlineag`, `williamhill`, `pinnacle`,
`suprabets`, `coolbet`, and `matchbook`. `betonlineag` and `mybookieag` were
cross-listed. Pinnacle was present under EU as intended.

Outright probes returned exactly:

- `icehockey_nhl` plus `markets=outrights`: HTTP 422,
  `INVALID_MARKET_COMBO`, zero credits;
- `icehockey_nhl_championship_winner` plus `markets=outrights`: one NHL Championship
  Winner event, 11 books, and 16 team outcomes per book; Betfair also returned
  `outrights_lay`.

This is a Stanley Cup future, not a per-series market. No series-winner market was
observed.

Probe quota headers:

| Call | `x-requests-last` | `x-requests-used` | `x-requests-remaining` |
|---|---:|---:|---:|
| sports catalog | 0 | 0 | 100,000 |
| featured markets | 60 | 60 | 99,940 |
| invalid base-NHL outright | 0 | 60 | 99,940 |
| championship outright | 20 | 80 | 99,920 |

Probe cost: **80 credits**, below the 300-credit probe cap.

## 3. Request construction and cost

Input tables were the committed `game-times-<season>.csv.gz` and
`team-games-<season>.csv.gz` files under `ml/data/raw/nhl-archive/`.

- Playoffs (`gameTypeId=3`): one request at scheduled start minus 60 minutes for every
  distinct start minute, seasons 2019-20 through 2025-26. Games sharing a start minute
  share one response.
- Regular season (`gameTypeId=2`): one request per NHL archive `gameDate`, at that
  day's earliest scheduled UTC start minus 60 minutes, seasons 2020-21 through
  2025-26. The 2019-20 archive has no regular-season day after June 6, 2020.

| Season | PO games | PO requests | PO credits | RS games | RS days | RS credits |
|---|---:|---:|---:|---:|---:|---:|
| 2019-20 | 130 | 130 | 7,800 | 0 | 0 | 0 |
| 2020-21 | 84 | 83 | 4,980 | 868 | 126 | 2,520 |
| 2021-22 | 89 | 87 | 5,220 | 1,312 | 189 | 3,780 |
| 2022-23 | 88 | 88 | 5,280 | 1,312 | 178 | 3,560 |
| 2023-24 | 88 | 88 | 5,280 | 1,312 | 183 | 3,660 |
| 2024-25 | 86 | 86 | 5,160 | 1,312 | 178 | 3,560 |
| 2025-26 | 82 | 82 | 4,920 | 1,312 | 167 | 3,340 |
| **Total** | **647** | **644** | **38,640** | **7,428** | **1,021** | **20,420** |

The script printed the full estimate before the first bulk request:

```text
bulk 59,060 + probes 80 = 59,140 credits
```

This was 30,860 below the 90,000-credit job cap. All **1,665 / 1,665** bulk requests
returned HTTP 200. Every response's three quota headers were appended immediately to
an external sanitized JSONL log. The final headers were:

| Header | Value |
|---|---:|
| `x-requests-last` | 20 |
| `x-requests-used` | 59,140 |
| `x-requests-remaining` | 40,860 |

Observed bulk cost was exactly **59,060**: 644 calls at 60 credits and 1,021 calls at
20 credits. Whole-job cost including probes was exactly **59,140**. The 5,000-credit
remaining guard never approached its stop threshold.

## 4. Plaintext layout and matching

Plaintext existed only outside the repository. Each season directory contained:

```text
raw/<gameTypeId>/<requested-iso-timestamp>.json.gz
index.csv.gz
lines.csv.gz
```

Colons in requested timestamps are replaced with hyphens in filenames. Raw files are
gzip wrappers around otherwise unmodified response bodies. `index.csv.gz` contains one
row per covered NHL archive game. `lines.csv.gz` contains one row per matched game ×
bookmaker × market × outcome and exists for validation and later in-memory parsing.

Team names came from the paired NHL `team-games` rows (`homeRoad=H/R`). Matching
requires exact API home and away names plus an unambiguous commence time within two
hours of the NHL archive start. No spelling alias, fuzzy match, or inferred event id
was used. Exact duplicate response objects are collapsed before matching; one snapshot
on 2022-12-21 repeated seven event objects byte-for-byte with identical ids and times.

| Season | Games indexed | Games matched | Unmatched | Flat line rows | Unique books |
|---|---:|---:|---:|---:|---:|
| 2019-20 | 130 | 119 | 11 | 9,426 | 20 |
| 2020-21 | 952 | 892 | 60 | 57,008 | 28 |
| 2021-22 | 1,401 | 1,307 | 94 | 80,311 | 26 |
| 2022-23 | 1,400 | 1,318 | 82 | 89,704 | 32 |
| 2023-24 | 1,400 | 1,318 | 82 | 80,005 | 31 |
| 2024-25 | 1,398 | 1,309 | 89 | 78,839 | 35 |
| 2025-26 | 1,394 | 1,312 | 82 | 110,358 | 35 |
| **Total** | **8,075** | **7,575** | **500** | **505,651** | — |

All 7,575 matched rows have `h2h`. Every matched playoff row also has `spreads` and
`totals`.

### Explicit gaps

- **498 rows** involve the NHL archive name `St. Louis Blues`, whose API spelling did
  not compare byte-for-byte because of punctuation. Per the no-guess rule, these rows
  remain unmatched: 32 playoff games and 466 regular-season games.
- **2 rows** were absent at the requested snapshots despite exact archive names:
  2020 qualifying-round PIT–MTL games 1 and 2 (`2019030021`, `2019030022`).

Thus playoff exact-match coverage is **613 / 647 games**. No substitute line or nearby
event was inserted for any of the 34 gaps.

API commence times differ from NHL scheduled starts because of feed corrections and
delays. Four matched games differ by more than 30 minutes; the maximum accepted exact-
team difference is two hours and is recorded per row. All 1,665 returned snapshot
timestamps are at or before the request. Three snapshots are more than ten minutes
older than requested; the largest snapshot gap is 4 hours 15 minutes. These values are
preserved and not adjusted.

Regular-season rows share the snapshot taken 60 minutes before the day's earliest
scheduled game. Lines for later games can therefore be several hours older than their
own start and are not true closing lines.

## 5. Encryption and archive verification

`sealed_archive.py` creates a deterministic POSIX tar stream with sorted entries,
`mtime=0`, `uid=gid=0`, empty user/group names, fixed file modes, and deterministic
gzip metadata. It encrypts those gzip bytes with AES-256-GCM using a fresh random
12-byte nonce and writes:

```text
nonce || AESGCM ciphertext-and-tag
```

`ODDS_ARCHIVE_KEY` is urlsafe-base64 decoded and must be exactly 32 bytes. It was
generated once into ignored `ml/.env`. The value was never printed or committed.

| File | Files | Cipher bytes | Cipher SHA-256 | Plain gzip SHA-256 | Tar SHA-256 |
|---|---:|---:|---|---|---|
| `2019-20.tar.enc` | 132 | 501,001 | `8c673b227ca070bbcf08998a22d6508d9863b4f35c7bc494a9083daa31b97c90` | `90756b3064f80ba1b9c820487f7a6c9d4f6b1b8e5a1e1e398acee89064ce30d0` | `ca71873fbc2a889e6b014ea9a111eea5367ef73e0c16e83b33adc965ce75d26f` |
| `2020-21.tar.enc` | 211 | 1,297,833 | `9d042d93fe509c13a338d51dc6389a45c9954ead2063787ddce4bfd541e990d1` | `ae5c906f14ee5b50da8a8fe79ec54ca1df0e8308d9fbb98b9018f37ab6927c1c` | `f921839650565683a605f88422b6577da9c3dc68d4ae268bfa190b73ee85b69e` |
| `2021-22.tar.enc` | 278 | 1,724,153 | `85ef059022b5465e16dd6bcdab3c6e19a48a1df919edeaa8c850c7532a0edfd3` | `ca05ce605d478b0ce9561df9c21138a1540330399fc36ac3083295f6ac604b31` | `94b02818670241395426d0adda792ba480d69ea49c6c16a04ba5c3ac8a15f71e` |
| `2022-23.tar.enc` | 268 | 1,842,606 | `811b5c86d17e0910549fd5a5b3476f6d5c62fca7252afb2c71349765d1955ecd` | `35e91471a8c0ee61d7218c0e26950382890b37442ddce8cc7e107d4b7745c4ca` | `64366733b6faf66e9e54ce2f5eb117c7b07eb5bc0bc30d3ec4c0447f728ce50d` |
| `2023-24.tar.enc` | 273 | 1,686,493 | `50d69cb1956207a01ed50633fc32ce326a3ab07af56b0d436d35538b1167d103` | `cf7776c63eb6062e6e6b9f924edb6ac986b6424a505c7e5e50af51439068d5b1` | `ec7bfd0915ace3e4426712fa4020d0257bb1f6a45a6ba43a05431c377de692ab` |
| `2024-25.tar.enc` | 266 | 1,674,600 | `af9cef1d74b3b3c8b265ba179efc22601945409b4abb8aa303a537f6db09ceaa` | `5d830ef0a57fe3bd07c105dd7c23d689208b9c54c4cd92f1255b3f9c92a9705b` | `22347cd2cf05a66f7ed89fe8aa572d5b1e9692e23073eecba574fdf1bf9365eb` |
| `2025-26.tar.enc` | 251 | 2,104,219 | `9a48e5f7ebf4535038fe23050511caa72b9ce704039255a2dbc3e0d4a2e81c61` | `e2c6e415a71a94ecee46daa2b755e7149223459a03b967a417eafc5d420969b4` | `d05c3c84483779280d195b7db158cfe1ed438e1820975ff8afe78e3053821893` |

Every archive was decrypted with the committed `open` command into a new external
directory. All **1,679 / 1,679** extracted files matched the original external files by
relative path and SHA-256. Wrong keys produce one concise error and no traceback.
