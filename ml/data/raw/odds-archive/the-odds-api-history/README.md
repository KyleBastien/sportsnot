# Sealed The Odds API history

These files are deliberately opaque. The Odds API terms prohibit redistributing its
data as downloadable files, while this repository is public. Only AES-256-GCM
ciphertext is committed. Raw JSON, `index.csv.gz`, and `lines.csv.gz` must remain in
an external scratch directory and must never be committed.

The decryption key is a urlsafe-base64 encoding of 32 random bytes. It belongs in:

- the owner's password manager;
- ignored `ml/.env` as `ODDS_ARCHIVE_KEY`;
- authorized runtime secret stores that need to regenerate evidence.

Never print or commit the key. Copy it from `ml/.env` into the password manager after
acquisition. A missing key leaves downstream consumers on the stat-only path.

From `ml/`, open one archive into an **external** empty directory:

```bash
uv run --with cryptography python data/raw/odds-archive/the-odds-api-history/sealed_archive.py open \
  data/raw/odds-archive/the-odds-api-history/2025-26.tar.enc \
  "$TEMP/odds-history-open/2025-26"
```

Seal a season directory after acquisition:

```bash
uv run --with cryptography python data/raw/odds-archive/the-odds-api-history/sealed_archive.py seal \
  "$TEMP/odds-history/2025-26" \
  data/raw/odds-archive/the-odds-api-history/2025-26.tar.enc
```

Each opened season contains:

```text
raw/<gameTypeId>/<requested-iso-timestamp>.json.gz
index.csv.gz
lines.csv.gz
```

`raw/` contains gzipped, otherwise unmodified HTTP response bodies. `index.csv.gz`
has one row per covered NHL archive game. `lines.csv.gz` is a validation-only flat
extraction. See `PROVENANCE.md` for request parameters, coverage, gaps, costs, and
checksums.
