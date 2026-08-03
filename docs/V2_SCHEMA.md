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
- **Reader:** the top/bottom (Wyckoff) detector is the *intended* consumer. **As of this
  writing NOTHING reads it yet** — the detector is not wired to it. This is recorded on
  purpose: an unread table is what made `intraday_30d` look droppable; it must not be
  treated as debris on that basis.
- **NOT V1 debris.** It **supersedes** the dropped `intraday_30d` (which had a misleading
  "30d" name, held 10 years of bars, and carried **no primary key** so nothing could
  upsert into it safely). `intraday_30d` and its data are gone permanently — Neon's restore
  window closed before a back-dated branch could be taken. `market_candles_15m` is refilled
  forward by cron and back-filled by `kite_fetch --ids … --write`.
- **Retention wall — coverage starts 2025-11-18 (measured 2026-08-03).** Kite serves only
  the most recent **~258 days** of 15-minute history — a HARD retention wall (not a
  per-request cap; pagination does not extend it). The 2016→2026 backfill confirmed this
  empirically: bars exist only from ~2025-11-18 forward. **The cross-era validation in
  `AACapital_TopBottom_Approach.md` (2016–2026, stable across eras) rests on 15-min data
  no longer held and is not reproducible** from what we have; current coverage is 2025-11
  onward. The wall rolls forward daily.
- **Coverage is honest-partial, in two distinct states** (`completeness.py`, evidence-based
  off `min(ts)`): (1) **listed before the wall** → its listing-period 15-min is permanently
  gone, but the IPO still trades so RECENT bars ARE fetchable (`kite_fetch` clamps the
  fetch start to `today − LOOKBACK_15M_DAYS`); (2) **token unresolved** → no series yet but
  fixable. The fetch stores exactly the bars Kite returns, so a short series reads as
  *present* (has rows) — bar-count / ts-range is the real coverage signal.

## Where the V2 set is enumerated in code (keep these in sync)
- `pipeline/inspect_schema.py` — `V2_TARGETS` (extractor-gated) + `V2_DATA_FILL` (the rest).
  `V1_DEBRIS` must contain **neither** `market_candles_15m` **nor** `intraday_30d`.
- `pipeline/completeness.py` — `HAS_ROWS_LISTED` + the `_pending` permanent-gap rule.
- `pipeline/fill_v2.py` — the selftest cleanup lists.
- There is **no** `which_db.py`; DB identity is `inspect_schema.py` job 1.
- `pipeline/inspect_checks.py` `TABLES` is the *extractor CHECK-constraint* set only —
  candle tables are not extractor targets, so `market_candles_15m` is correctly absent there.
