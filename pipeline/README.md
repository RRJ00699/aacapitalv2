# AACapitalPvtLtd — IPO data pipeline

One command fills every column for every active IPO, from authenticated sources, with
IPOMatrix as fallback. Safe to run repeatedly: data arrives progressively (RHP ~2 weeks
out, issue details ~1 week, subscription at close, candles at listing), so each run
fills whatever has newly appeared.

## Run

    python cron.py --dry-run                    # plan only, spends nothing
    python cron.py --run --limit 10             # full chain
    python cron.py --run --limit 10 --skip-download   # skip the two downloaders

## The chain

| # | Step | Script |
|---|------|--------|
| 1 | Kite token (TOTP) | `_scripts/refresh_kite_token.py` |
| 2a | Download RHPs | `_scripts/download_sebi_rhps_playwright.py` |
| 2b | Download SBI notes | `_scripts/download_sbi_notes.py` |
| 2c | Parse SBI notes | `_scripts/parse_sbi_notes.py` |
| 3 | NSE issue + subscription | `nse_fetch.py` |
| 4 | RHP extraction (PAID) | `drive.py --rhp` |
| 5 | Vendor fallback | `ipomatrix_fallback.py` |
| 6 | Candles + listing outcomes | `kite_fetch.py` |
| 7 | Score, verdict, completeness, ntfy | `drive.py` |
| 9-11 | Cleanup + document home | `cron.py` |

## Spend control

The daily cap lives in `platform_config.daily_spend_cap_usd` — change it from a phone
with any DB client, no redeploy:

    INSERT INTO platform_config (key, value, updated_at)
    VALUES ('daily_spend_cap_usd', '2.00', NOW())
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

Today's spend is summed from `rhp_findings.cost_usd`, which the extractor already
writes, so there is no second ledger to drift. Only step 4 costs money (~$0.13/RHP).

## Document lifecycles differ, deliberately

- **RHPs** (8-20MB) — extracted, then purged. Never committed: git keeps every blob
  forever. Re-fetchable via `documents.url`.
- **SBI notes** (~3 pages) — kept, because the UI displays them. On GitHub Actions they
  are committed back (the runner is ephemeral); locally they just stay put. `cron.py`
  detects `GITHUB_ACTIONS` and does the right thing either way.

## Scope

The cron works the ACTIVE window only — unlisted IPOs with a live issue date or a
recently fetched document, plus anything listed within 90 days (the anchor lock-in).
Older IPOs are finished business. `--backfill` overrides this for one-off history work.

## No duplicates

Every write goes through `fill_ipo` / `fill_v2`, which resolve on the ISIN spine
(ISIN -> name_norm, never fuzzy) and are COALESCE-empty-only or keyed `ON CONFLICT`.
Re-running fills gaps and duplicates nothing.

## Environment

    DATABASE_URL, ANTHROPIC_API_KEY,
    KITE_API_KEY, KITE_API_SECRET, KITE_USER_ID, KITE_PASSWORD, KITE_TOTP_SECRET,
    NTFY_TOPIC

Locally in `.env`; on Actions as repository secrets.

## Diagnostics (read-only)

    python completeness.py --limit 5      # what is missing, pending, vendor-fallback
    python inspect_schema.py              # V2 tables, columns, unique keys
    python check_pool.py                  # listing_outcomes CHECK + active-window evidence
    python fix_zero_subs.py --check       # zero-filled final subscription snapshots

## Status

Tested against the live DB on 2026-08-01: steps 1, 3, 4, 5, 6, 7 and the cleanup all ran
end to end. Steps 2a/2b/2c (the downloaders) are carried over from the previous repo and
have NOT been executed from this one yet — run once with `--skip-download` omitted,
supervised, before scheduling.

## Snapshot architecture additions

Status: Accepted

The pipeline is the only production owner of IPO snapshot construction. User-facing routes consume Cloudflare KV snapshots and must not build snapshots or wake Neon.

### Fetch

Fetch jobs collect upstream IPO, document, market, subscription, GMP, and broker inputs into the database or local/R2-backed working files. Fetchers should keep source-specific behavior isolated and must not be imported by user-facing routes.

### Build

Snapshot build jobs live under `pipeline/build/`. The canonical snapshot builder is `pipeline/build/build_snapshots.ts`; it runs with `npx tsx`, reuses the TypeScript domain builders, selects the Journey universe with `selectJourneyUniverse()`, validates bounds from `lib/config/pipeline.ts`, and emits/publishes JSON snapshots.

Run the read-only schema smoke from the repository root with:

```bash
npx tsx pipeline/build/build_snapshots.ts --limit=1 --concurrency=1 --schema-smoke
```

When the working directory is `pipeline` (as it is for pipeline workflow steps), use:

```bash
npx tsx build/build_snapshots.ts --limit=1 --concurrency=1 --schema-smoke
```

### Publish

`pipeline/warm_kv.py` invokes the TypeScript builder. The builder posts validated snapshot payloads to `POST /api/admin/snapshots`, which is a publication-only endpoint that writes versioned KV and does not read Neon or construct domain payloads.

### Capture

`pipeline/capture_preopen.py` performs bounded listing-day pre-open capture into the existing `listing_observations` table only. It supports dry-run and limit modes, selects identity by ISIN first, prints operator verification details, uses the weekday 03:25–04:35 UTC / 08:55–10:05 IST schedule to cover the 09:00–09:40 IST decision window, with 75 maximum scheduled checks/week and a fast exit when no eligible IPO lists that day.

### Engines

Engines compute derived IPO analysis such as scoring, valuation, extraction, and decision artifacts. Engine outputs must be validated before they feed published snapshots. Research outputs must graduate through validation before entering pipeline or production paths.

### Diagnostics

Diagnostics and audit checks should verify producer ownership, no user-route DB imports, snapshot publication/fallback behavior, pre-open bounds, and credential safety. Diagnostics must avoid deployments, broad backfills, paid APIs, or schema changes unless explicitly approved.
