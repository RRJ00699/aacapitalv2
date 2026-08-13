# V2 Canonical Schema — the table registry

Status: reference — the authoritative list of V2 canonical tables (the `misty-meadow`
family the pipeline writes and the app reads). Created 2026-08 because no single doc
previously declared the V2 set — and an **undeclared table looks like debris**, which is
exactly how `intraday_30d` got swept when the V1 tables were dropped. Every V2 table
belongs here; if you add one, add it here and to `inspect_schema.py`'s `V2_DATA_FILL`.

Source of truth for the list: the writers themselves — `fill_v2.py`, `fill_ipo.py`,
`kite_fetch.py`. Do not hand-maintain a count; enumerate.

> **A table with no declared writer and no declared reader will be mistaken for debris.
> Register it here before it exists.**

## Canonical tables

**Spine & data-fill** (written by `fill_v2` / `fill_ipo` / `kite_fetch`):
| table | key | what |
|---|---|---|
| `ipo` | `id` (ISIN spine) | one row per company |
| `ipo_issue` | `ipo_id` | issue economics (band, size, dates, price) |
| `subscription_snapshots` | `(ipo_id, captured_at)` | demand / anchor snapshots |
| `financial_statements` | `(ipo_id, period, basis)` | restated financials |
| `documents` | `sha256` | RHP file registry (R2-backed) |
| `source_facts` | append-on-change | provenance log |
| `market_regimes` | `d` | daily regime / VIX / breadth |
| `market_candles` | `(ipo_id, d)` | **daily** OHLCV + delivery |
| **`market_candles_15m`** | **`(ipo_id, ts)`** | **15-minute intraday OHLCV** |
| `listing_observations` | `(ipo_id, obs_type, observed_at)` | listing-day tape / pre-open |
| `listing_outcomes` | `ipo_id` | derived listing result (gap, pool) |

**Engine-output** (computed; bodies filled by their engines):
`valuation` · `decisions` · `rhp_findings` · `insights`

## `market_candles_15m` — the detail

- **Purpose:** 15-minute intraday bars — the forward-validation / Wyckoff input.
- **PK:** `(ipo_id, ts timestamptz)`. Columns `o, h, l, c, v`.
- **Writer:** `kite_fetch.py` (`fetch_candles_15m` → `upsert_candles_15m`), run as **cron
  step 6** (`cron.py`, `kite_fetch.py --ids <ids> --write`). Table is created idempotently
  by `ensure_15m_table` on the first `--write` run — no manual DDL step.
- **Reader:** the stored 15-min bars ARE read. `research/backtests/forensic.py` gates its
  universe on `EXISTS (SELECT 1 FROM market_candles_15m …)` and reads `ts,o,h,l,c,v` from
  the table, and `pipeline/completeness.py` reads `min(ts)` from it to compute coverage.
  (The top/bottom (Wyckoff) `topout_online.py` detector reads 15-min bars live from Kite,
  not from this table.) It must not be treated as debris — an unread table is what made
  `intraday_30d` look droppable, and this one is not unread.
- **NOT V1 debris.** It **supersedes** the dropped `intraday_30d` (which had a misleading
  "30d" name, held 10 years of bars, and carried **no primary key** so nothing could
  upsert into it safely). `intraday_30d` and its data are gone permanently — Neon's restore
  window closed before a back-dated branch could be taken. `market_candles_15m` is refilled
  forward by cron and back-filled by `kite_fetch --ids … --write`.
- **Coverage currently starts ~2025-11-18** (earliest bar held, as of 2026-08-03). The
  2016→2026 backfill returned 15-min data only from ~2025-11-18 forward. **Kite's true
  15-min availability horizon is UNMEASURED** — `min(ts)` is self-confirming (old IPOs
  returned 0 because the fetch asked from an out-of-range `listing_date`, not because Kite
  refuses recent data). It must be measured with a backward-walking probe (request
  today-300/-400/-600/-1000 for a token that listed well before the wall; find where Kite
  returns empty), then a fetch-start clamp set from the measured value. Until then no
  permanence is claimed. **The cross-era validation in `AACapital_TopBottom_Approach.md`
  (2016–2026) rests on 15-min data no longer held and is not reproducible** from what we
  have; current coverage is 2025-11 onward.
- **Coverage is honest-partial, in two distinct states** (`completeness.py`, off `min(ts)` =
  earliest bar held): (1) **listed before our earliest held bar** → listing-period 15-min
  not held; refetchability pending the horizon probe; (2) **token unresolved** → no series
  yet but fixable. The fetch stores exactly the bars Kite returns, so a short series reads
  as *present* (has rows) — bar-count / ts-range is the real coverage signal.

## Where the V2 set is enumerated in code (keep these in sync)
- `pipeline/inspect_schema.py` — `V2_TARGETS` (extractor-gated) + `V2_DATA_FILL` (the rest).
  `V1_DEBRIS` must contain **neither** `market_candles_15m` **nor** `intraday_30d`.
- `pipeline/completeness.py` — `HAS_ROWS_LISTED` + the `_pending` permanent-gap rule.
- `pipeline/fill_v2.py` — the selftest cleanup lists.
- There is **no** `which_db.py`; DB identity is `inspect_schema.py` job 1.
- `pipeline/inspect_checks.py` `TABLES` is the *extractor CHECK-constraint* set only —
  candle tables are not extractor targets, so `market_candles_15m` is correctly absent there.
