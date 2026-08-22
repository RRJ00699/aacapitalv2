# AACapital — Neon PostgreSQL → Cloudflare D1 Migration Plan (Phase 0)

Status: **PROPOSAL — awaiting owner approval before any code change**
Authority: This document describes the *plan*. `docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md` remains the product truth. No product rule, decision engine, or fair-value formula is changed by this migration.

> **Execution rule (from owner):** do not rewrite the whole repository. First return the audit, then implement with repository evidence. This document is that audit. Every claim below cites a real file path in `RRJ00699/aacapitalv2@main`.

---

## 0. TL;DR

- The repo is **already ~80% Cloudflare-native**: OpenNext → Workers deployment (`wrangler.jsonc`, `open-next.config.ts`), a Kite proxy Worker (`workers/kite-broker-proxy/`), R2 for documents (`pipeline/r2.py`), KV cache + versioned snapshot publisher with active/previous rollback (`lib/versioned-snapshot.ts`), and a hard zero-wake contract test on the web plane (`lib/web-plane-db-contract.test.ts`). The remaining gap is **Neon → D1** and **GitHub Actions crons → Cloudflare Cron Triggers**, plus finishing the 13-route KV allowlist.
- **We keep the Python pipeline (`pipeline/*.py`)** and let it write to D1 through a new authenticated ingestion Worker. Rewriting 60+ Python files into TypeScript Workers is not warranted; Cloudflare-native does not mean "everything is a Worker". D1 becomes the system of record; KV remains the public read plane.
- **Financial precision:** all rupee amounts move to `TEXT` (decimal-string, unit = rupees per share / rupees-crore) so no float can silently corrupt an IPO price. Share counts / basis points / integer identities move to `INTEGER`.
- **No destructive cutover.** Stages A–H below; Neon stays online, read-only for the pipeline, until reconciliation and 30 days of parallel snapshot equivalence pass.

---

## 1. Current architecture (evidence-based)

### 1.1 Layers as they exist in `main`

| Layer | Where | Evidence |
|---|---|---|
| **Edge / public site** | Next.js 15 (App Router) via OpenNext, deployed to CF Workers | `wrangler.jsonc:main = ".open-next/worker.js"`, `open-next.config.ts`, `next.config.ts` |
| **Auth** | NextAuth with allowlisted emails | `auth.ts`, `wrangler.jsonc:vars.ALLOWED_EMAILS/ADMIN_EMAILS` |
| **Public read plane (KV)** | Snapshots (versioned) + live keys | `lib/versioned-snapshot.ts`, `lib/kv-cache.ts`, `wrangler.jsonc:kv_namespaces=[JOB_FLAG, CACHE]` |
| **System of record** | Neon Postgres via `DATABASE_URL` | `lib/db.ts` (tagged-template `sql`), `README.md` |
| **Pipeline (offline)** | Python 3.12; entry `pipeline/cron.py`; ~60 step modules | `pipeline/*.py`, `pipeline/build/build_snapshots.ts` (Node), `pipeline/publish_snapshot_with_ledger.py` |
| **Broker proxy** | Cloudflare Worker for Kite | `workers/kite-broker-proxy/src/index.ts`, `wrangler.jsonc:vars.KITE_BROKER_PROXY_URL` |
| **Document store** | Cloudflare R2 (RHP + SBI PDFs, immutable) | `pipeline/r2.py`, `docs/specifications/R2_DOCUMENT_CONTRACT.md`, `.github/workflows/pipeline.yml:R2_*` |
| **Alerts** | ntfy.sh push (IST + US-Central) | `_scripts/lib/notify.py`, `vars.NTFY_TOPIC` |
| **Cron / scheduling** | **GitHub Actions** — *not* CF Cron Triggers | `.github/workflows/{daily-pipeline,preopen-capture,sbi-notes,pipeline,probe-nse}.yml` |

### 1.2 Existing KV keys (evidence in code + `docs/runbooks/KV_NAMESPACE_SPLIT.md`, `docs/architecture/ASSET_LIGHT_ARCHITECTURE.md`)

| Key pattern | Producer | Consumer | TTL |
|---|---|---|---|
| `snapshot:<name>:active` | `lib/versioned-snapshot.ts:publishVersionedSnapshot` | `readVersionedSnapshot` | 7 d |
| `snapshot:<name>:previous` | ditto (transparent rollback) | same | 7 d |
| `snapshot:<name>:data:<version>` | immutable payload | same | 7 d |
| `ipo-command:v1` / `:stale` | pipeline warm → `/api/admin/kv-put` | `/api/ipo-command/route.ts` | 12 h |
| `live:tick:<symbol>` | VM ticker `_scripts/ipo/kite_ticker_ipo.py` → `/api/admin/kv-put` | `/api/ipo/tick-feed?live=1` | 5 min |
| `live:preopen:<symbol>` | listing-day capture | `/api/ipo/live-preopen` | ~15 min |
| `journey:candles:<isin>` | pipeline | `/api/ipo/journey` | day |
| `cumvol:<isin>` | pipeline / capture | `/api/ipo/cum-volume` | day |

Namespace state: **both `JOB_FLAG` and `CACHE` are bound to the same id `71fc0e8060ce4cad919b58d35b9681e2`** (`wrangler.jsonc:16-19`, with a leading comment explaining the 2026-07-18 CACHE-placeholder incident). That is a known technical-debt item to fix by creating a real `CACHE` namespace.

### 1.3 Cron map today (evidence: `.github/workflows/*.yml`)

| Workflow file | UTC schedule | IST | Purpose | Writes |
|---|---|---|---|---|
| `daily-pipeline.yml` | `45 2 * * 1-5` | **08:15 Mon-Fri** | `pipeline/cron.py --skip-download` (main daily) | Neon, R2, KV (`snapshot:*`) |
| `preopen-capture.yml` | `0 3 * * 1-5` | 08:30 Mon-Fri | Canonical NSE universe refresh (`nse_lifecycle.py --discovery-only`) | Neon |
| " | `20 3 * * 1-5` | 08:50 Mon-Fri | Bounded ISIN backfill (`nse_identity_backfill.py`) | Neon |
| " | `30 11 * * 1-5` | 17:00 Mon-Fri | Evening universe refresh | Neon |
| " | `25-55/5 3 * * 1-5` + `0-35/5 4 * * 1-5` | **08:55–10:05 every 5 min** Mon-Fri | Pre-open capture (`capture_preopen.py`) | Neon |
| `sbi-notes.yml` | `30 3 * * *` | 09:00 daily | Scrape SBI notes to R2, dry-run | R2, Neon-write is owner-gated |
| `pipeline.yml` | manual only | — | Full paid pipeline w/ RHP Sonnet | Neon, R2, KV |
| `probe-nse.yml` | manual only | — | Reachability probe (no writes) | none |

**Timezone hygiene:** the workflows already annotate IST explicitly in comments; that discipline must carry into any CF Cron Triggers we introduce.

### 1.4 Integration map today

| Source | Ingestion module | Cost | Failure mode | Where used in DB |
|---|---|---|---|---|
| NSE | `pipeline/nse_lifecycle.py`, `nse_identity_backfill.py`, `nse_fetch.py`; `_scripts/ipo/fetch_nse_ipos.py`, `fetch_delivery_bhavcopy.py` | free | 403 from CI IPs handled via `probe-nse.yml` gate + `SourceUnavailable` no-op | `ipo` spine, `ipo_issue`, `listing_observations`, `market_candles` (delivery %) |
| SEBI | `_scripts/download_sebi_rhps_playwright.py` | free | all-failed = ntfy + exit 1 | `documents` (R2 URL) |
| SBI Securities | `_scripts/download_sbi_notes.py` → `pipeline/sbi_ongoing.py` → Anthropic Haiku | Haiku $0.50/day cap | skip + sink | `ipo_research_notes` |
| investorgain (GMP) | (referenced by product contract §5) | free | graceful skip + ntfy | context only, not DB persisted for gap decisions |
| IPOMatrix | `pipeline/ipomatrix_fallback.py` | free (cookie ~30d) | skip; cookie rotation via Settings | enrichment |
| Zerodha Kite | `_scripts/refresh_kite_token.py` (TOTP 08:00 IST), `pipeline/kite_fetch.py`, `kite_fetch_15m.py`, `_scripts/ipo/kite_ticker_ipo.py` | Kite Connect sub | token stale → URGENT ntfy | `market_candles`, `market_candles_15m`, `ipo_tick_feed`, `listing_observations` |
| Anthropic Claude | `pipeline/rhp_sonnet.py` (Sonnet, $3/day cap), SBI Haiku (in `sbi_ongoing.py`) | paid, capped | cap-deferred queue | `rhp_findings`, `insights`, `documents.full_json` |

### 1.5 Zero-wake boundary today (evidence: `lib/web-plane-db-contract.test.ts`)

The test freezes the list of `app/**` routes that still import `@/lib/db`. Anything not listed **fails the build**. Current allowlist (13 files):

- Writes that cannot be pure KV consumers (correctly Neon-bound): `access-note`, `admin/access`, `admin/jobs`, `admin/secrets`, `admin/kv-put`, `auth/zerodha/callback`, `settings/*`, `pipeline/trigger`, `access-request` etc.
- Reads that *should* migrate to KV (open work): `admin/pipeline-failures`, `admin/pipeline-steps`, `ipo/cum-volume` history path, `ipo/tick-feed` chart-history path. These are annotated in the test with the KV contract that would let them close.

**This is exactly the invariant the target architecture demands. It already exists.** Migration only needs to swap `sql` (pg) for `d1` on the write path, without weakening the guard.

---

## 2. Current Neon schema (canonical list from `docs/specifications/V2_SCHEMA.md`, verified against `pipeline/inspect_schema.py`, `pipeline/fill_v2.py`, `pipeline/fill_ipo.py`, `pipeline/kite_fetch.py`)

The pipeline calls this the **V2 canonical set** (aka `misty-meadow`). Anything not on this list is either debris (see §2.3) or app/operational infra (§2.4).

### 2.1 Spine & data-fill tables (V2_DATA_FILL)

| Table | Key | Purpose | Writer | Reader |
|---|---|---|---|---|
| `ipo` | `id` (ISIN spine) | One row per company; identity resolution root | `fill_v2.py`, `fill_ipo.py`, `nse_lifecycle.py` | almost every step + snapshot builder |
| `ipo_issue` | `ipo_id` | Issue economics (band, size, dates, price) | `fill_v2.py`, `nse_lifecycle.py` | `build_snapshots.ts`, ipo-command route |
| `subscription_snapshots` | `(ipo_id, captured_at)` | Demand + anchor snapshots (QIB / NII / retail / anchors) | `nse_lifecycle.py` | listing-day rules, snapshot |
| `financial_statements` | `(ipo_id, period, basis)` | Restated 3-year financials | `rhp_sonnet.py` via `rhp_writer.py` | fair-value, snapshot |
| `documents` | `sha256` | RHP / SBI file registry, R2-backed (immutable `object_key`) | `rhp_link.py`, `sbi_ingest.py`, `r2.py` | RHP verdict, SBI note |
| `source_facts` | append-on-change | Provenance log (see `docs/specifications/PROVENANCE_DESIGN.md`) | every writer | audit, snapshot |
| `market_regimes` | `d` (date) | Daily Nifty / VIX / breadth regime | `_scripts/market_regime.py` | market/snapshot route |
| `market_candles` | `(ipo_id, d)` | Daily OHLCV + delivery% (post-listing journey) | `kite_fetch.py` | journey route |
| `market_candles_15m` | `(ipo_id, ts)` | 15-minute intraday OHLCV | `kite_fetch_15m.py` | `topout_online.py`, backtests |
| `listing_observations` | `(ipo_id, obs_type, observed_at)` | Listing-day tape / pre-open / IEP | `capture_preopen.py`, `_scripts/ipo/kite_ticker_ipo.py` | listing-day rules, snapshot |
| `listing_outcomes` | `ipo_id` | Derived listing result (gap bucket, open pool) | `topout_online.py`, `score_engine.py` | snapshot |
| `decisions` | `ipo_id` (or `(ipo_id, decided_at)`) | Verdict engine output (Company Quality / Trade Setup / Live Action) | `verdict_engine.py` | snapshot |

### 2.2 Engine-output tables (V2_TARGETS, extractor-gated)

| Table | Purpose | Writer |
|---|---|---|
| `rhp_findings` | Sonnet forensic read of the RHP | `rhp_sonnet.py` + `rhp_writer.py` |
| `insights` | Distilled insights from filings | `intelligence.py` |
| `valuation` | Three-step fair value (`lib/fair-value.ts`) inputs + result | `pipeline/valuation` code path |
| `documents` | (also in §2.1) | as above |
| `financial_statements` | (also in §2.1) | as above |
| `source_facts` | (also in §2.1) | as above |
| `ipo_issue` | (also in §2.1) | as above |

### 2.3 Operational / auth / research tables (present in code and CI secrets)

| Table | Purpose | Where referenced |
|---|---|---|
| `platform_config` | Runtime knobs incl. `daily_spend_cap_usd` | `pipeline.yml` comment, `pipeline/cron.py`, admin routes |
| `access_requests` | Owner-approved email allowlist | `app/api/access-note/route.ts`, `app/api/admin/access/route.ts` |
| `pipeline_runs`, `pipeline_failures`, `pipeline_steps` | Pipeline observability (7-day windows) | `app/api/admin/pipeline-*`, `pipeline/cron.py` |
| `job_runs` | Admin job runner | `app/api/admin/jobs/route.ts` |
| `job_flags` (KV, not table) | via `JOB_FLAG` KV | `wrangler.jsonc`, `/api/admin/job-flag` |
| `ipo_rhp_intel` (`full_json`) | RHP Sonnet verdict blob | `docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md §4` |
| `ipo_research_notes` | SBI Haiku extract | as above |
| `ipo_tick_feed` | Historical tick series (KV is the live plane; DB is the archival trickle) | `docs/architecture/ASSET_LIGHT_ARCHITECTURE.md` Step 3 |
| `kite_session` / `broker_sessions` | Kite token persistence | `app/api/auth/zerodha/callback/route.ts` |
| `rule_validation_results` | Rule-set eval outputs | `pipeline/rule_validation.py` (`RULE_VALIDATION_OWNER_APPROVED`) |

### 2.4 Explicit non-tables (must NOT recreate in D1)

`V1_DEBRIS` from `pipeline/inspect_schema.py:31`: `ipo_intelligence`, `ipo_consolidated`, `ipo_golden`, `ipo_master`, plus `intraday_30d`, `company_master`, `amfi_*`, `management_commentary`, `technical_signals`. These are the equity-era residue and are explicitly rejected (`docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md §3`).

### 2.5 PostgreSQL constructs that need special handling for D1

| PG construct | Where it appears | D1 (SQLite) reality | Migration action |
|---|---|---|---|
| `TIMESTAMPTZ` | `subscription_snapshots.captured_at`, `market_candles_15m.ts`, `listing_observations.observed_at`, `source_facts.observed_at` | No native tz-aware type | Store as `TEXT` ISO-8601 UTC (e.g. `2026-06-17T03:30:00Z`); render in IST at the edge. Add per-table `_ts_utc` and *derived* `_d_ist` columns where needed for cheap grouping. |
| `DECIMAL / NUMERIC` (`ipo_issue.issue_price`, `financial_statements.eps` etc.) | ubiquitous | SQLite has NUMERIC affinity but stores as REAL/INTEGER; no fixed precision | **Store as `TEXT` decimal string.** Convention: `"41.5000"`. Never do arithmetic in SQL on rupee values; do it in TS/Python with `decimal.Decimal`/BigInt paise. See §6. |
| `JSONB` (`documents.full_json`, `rhp_findings.body`, `source_facts.evidence`, `insights.body`) | many | D1 has `json1` extension; column type is `TEXT` | Store as `TEXT`; keep the same shape. Use `json_extract` sparingly in D1 (indices are the win, not JSON parsing). |
| Arrays (`text[]`, `int[]`) | RHP peers list, keywords | none | Store as JSON string. |
| `GENERATED ALWAYS AS (...)` | verify via `\d+` | limited (SQLite has `GENERATED ... STORED/VIRTUAL`) | Rewrite as explicit writer-computed columns for critical fields; SQLite generated columns for read-only derivations. |
| Sequences (`SERIAL`/`BIGSERIAL`) | `id` on audit tables | no sequences | Use `INTEGER PRIMARY KEY AUTOINCREMENT` or ULID/UUID text ids. |
| Views | likely present for `ipo_command` reads | supported | Recreate; treat as build-time inputs to the snapshot builder, not query surfaces. |
| Triggers | `updated_at` auto-touch | supported (limited) | Port only those actually consumed; audit list first. |
| Stored procedures | assumed absent | no PL/pgSQL | If found, move to `pipeline/*.py` (they already largely live there). |
| Foreign keys | across V2 spine | supported | Enable with `PRAGMA foreign_keys=ON`; identical DDL. |
| Tagged-template `sql\`` (pg) | `lib/db.ts` and every allowlisted route | none | Add a new `lib/db-d1.ts` that mimics the same tagged-template surface for D1 to minimize call-site churn. |
| `ON CONFLICT ... DO UPDATE` / `COALESCE`-empty-only | writers everywhere (`fill_v2.py`, `nse_lifecycle.py`) | D1 supports `ON CONFLICT DO UPDATE` | Direct port; the "fill-empty-only" idiom translates 1:1. |
| `EXPLAIN ANALYZE` | dev tooling | no ANALYZE | Use `PRAGMA optimize`, `EXPLAIN QUERY PLAN`. |

**Data volume estimate (for D1 sizing, §7):** ~150–300 IPO rows on the spine; ~2k–8k rows across issue/subs/observations; `market_candles` ~250 rows/yr × ~150 tickers ≈ 40k/yr; `market_candles_15m` ~26 bars × ~250 trading days × ~50 tracked tickers ≈ **325k/yr**. Well inside D1's 10 GB / DB.

---

## 3. Proposed D1 architecture

### 3.1 Databases

Single database to start: **`aacapital_core`** (one D1 DB). Do **not** split D1 Core / D1 Market until measured need (§7). We only add a second DB `aacapital_market_history` if either (a) 15m grows to > 5M rows and query latency degrades, or (b) we ingest daily NIFTY components for regime models.

Bindings (proposed `wrangler.jsonc`):

```jsonc
"d1_databases": [
  { "binding": "DB_CORE", "database_name": "aacapital_core",
    "database_id": "<created by wrangler d1 create>",
    "migrations_dir": "d1/migrations" }
],
"kv_namespaces": [
  { "binding": "JOB_FLAG", "id": "71fc0e8060ce4cad919b58d35b9681e2" },
  { "binding": "CACHE",    "id": "<REPLACE — real cache ns from wrangler kv namespace create CACHE>" },
  { "binding": "SNAPSHOTS", "id": "<new — dedicated for snapshot:* keys>" }
],
"triggers": {
  "crons": [
    "45 2 * * 1-5",      // 08:15 IST daily pipeline
    "0 3 * * 1-5",       // 08:30 IST NSE universe refresh
    "20 3 * * 1-5",      // 08:50 IST identity backfill
    "*/5 3-4 * * 1-5",   // 08:30–10:05 IST pre-open capture (window enforced by handler)
    "30 11 * * 1-5",     // 17:00 IST evening refresh
    "30 3 * * *"         // 09:00 IST SBI note refresh
  ]
}
```

Rationale for a dedicated `SNAPSHOTS` KV: keeps the public read plane isolated from the `JOB_FLAG` control plane; snapshot keys don't compete for eviction with cache/hot data; matches the KV namespace-split runbook (`docs/runbooks/KV_NAMESPACE_SPLIT.md`).

### 3.2 Access rules (kept identical to today's contract)

- `DB_CORE` is bound to **ingestion Workers**, **snapshot builder Worker**, and **admin Workers** only.
- Public read routes NEVER bind `DB_CORE`. `lib/web-plane-db-contract.test.ts` is extended to also ban imports of any `lib/db-d1*` module from the public allowlist.
- KV bindings (`SNAPSHOTS`, `CACHE`) are the only reads permitted from public routes.

### 3.3 Proposed D1 schema (SQL DDL summary — full migration files land in `d1/migrations/0001_*.sql`)

Numeric convention (§6): rupees as `TEXT` decimal, share counts as `INTEGER`, timestamps as `TEXT` ISO-8601 UTC, booleans as `INTEGER 0/1`.

```sql
-- 0001_spine.sql
CREATE TABLE ipo (
  id                TEXT PRIMARY KEY,             -- ISIN (spine); if unknown, TEMP:<hash>
  company_name      TEXT NOT NULL,
  normalized_name   TEXT NOT NULL,                -- for identity resolution (exact match only)
  isin              TEXT UNIQUE,                  -- may be filled later; ISIN > normalized_name in identity rules
  nse_symbol        TEXT,                         -- never a primary identity per contract
  bse_symbol        TEXT,
  sector            TEXT,
  is_sme            INTEGER NOT NULL DEFAULT 0,   -- LOCKED avoid at read time; contract §6
  status            TEXT NOT NULL,                -- UPCOMING | OPEN | CLOSED | LISTED
  ipo_open_date     TEXT,                         -- ISO date (IST)
  ipo_close_date    TEXT,
  listing_date      TEXT,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX ipo_status_idx     ON ipo(status);
CREATE INDEX ipo_listing_idx    ON ipo(listing_date);
CREATE INDEX ipo_norm_name_idx  ON ipo(normalized_name);
CREATE INDEX ipo_isin_idx       ON ipo(isin);

CREATE TABLE ipo_issue (
  ipo_id            TEXT PRIMARY KEY REFERENCES ipo(id) ON DELETE CASCADE,
  price_band_low    TEXT,                         -- decimal string, rupees/share
  price_band_high   TEXT,
  issue_price       TEXT,                         -- final cutoff, decimal string
  face_value        TEXT,
  lot_size          INTEGER,
  fresh_issue_cr    TEXT,                         -- rupees crore, decimal string
  ofs_cr            TEXT,
  issue_size_cr     TEXT,
  market_cap_cr     TEXT,
  qib_pct           TEXT,
  nii_pct           TEXT,
  retail_pct        TEXT,
  anchor_cr         TEXT,
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE subscription_snapshots (
  ipo_id            TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  captured_at       TEXT NOT NULL,                -- ISO-8601 UTC
  qib_x             TEXT, nii_x TEXT, retail_x TEXT, total_x TEXT,
  anchors_count     INTEGER,
  source            TEXT NOT NULL,                -- 'nse'|'bse'
  PRIMARY KEY (ipo_id, captured_at)
);

CREATE TABLE financial_statements (
  ipo_id            TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  period            TEXT NOT NULL,                -- 'FY23','FY24','FY25','9M-FY25' etc
  basis             TEXT NOT NULL,                -- 'consolidated'|'standalone'|'restated'
  revenue_cr        TEXT, ebitda_cr TEXT, pat_cr TEXT, eps TEXT,
  roe TEXT, roce TEXT, debt_equity TEXT, ebitda_margin TEXT,
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  PRIMARY KEY (ipo_id, period, basis)
);

CREATE TABLE documents (
  sha256            TEXT PRIMARY KEY,
  ipo_id            TEXT REFERENCES ipo(id) ON DELETE SET NULL,
  kind              TEXT NOT NULL,                -- 'rhp'|'drhp'|'sbi_note'|'broker'
  object_key        TEXT NOT NULL,                -- R2 immutable key (contract v1)
  url_legacy        TEXT,
  extracted_at      TEXT,
  full_json         TEXT                          -- JSON extract; not queried in SQL
);
CREATE INDEX documents_ipo_idx ON documents(ipo_id);

CREATE TABLE source_facts (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id            TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  field             TEXT NOT NULL,                -- dotted path e.g. 'issue.issue_price'
  value             TEXT,                         -- prior value (or JSON blob for structured)
  source            TEXT NOT NULL,                -- 'nse'|'sebi_rhp'|'sbi'|'kite'|'ipomatrix'|'derived'
  observed_at       TEXT NOT NULL,
  evidence          TEXT                          -- JSON: {file, page, quote, ...}
);
CREATE INDEX source_facts_ipo_idx    ON source_facts(ipo_id);
CREATE INDEX source_facts_field_idx  ON source_facts(ipo_id, field);
CREATE INDEX source_facts_time_idx   ON source_facts(observed_at);
```

```sql
-- 0002_market.sql
CREATE TABLE market_regimes (
  d               TEXT PRIMARY KEY,             -- YYYY-MM-DD (IST market date)
  nifty_close     TEXT, vix TEXT, breadth_adv INTEGER, breadth_dec INTEGER,
  regime          TEXT                          -- 'risk_on'|'risk_off'|'neutral'
);

CREATE TABLE market_candles (
  ipo_id          TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  d               TEXT NOT NULL,                -- YYYY-MM-DD IST
  o TEXT, h TEXT, l TEXT, c TEXT, v INTEGER, delivery_pct TEXT,
  PRIMARY KEY (ipo_id, d)
);

CREATE TABLE market_candles_15m (
  ipo_id          TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  ts              TEXT NOT NULL,                -- ISO-8601 UTC bar-open
  o TEXT, h TEXT, l TEXT, c TEXT, v INTEGER,
  PRIMARY KEY (ipo_id, ts)
);
CREATE INDEX candles_15m_ipo_ts_idx ON market_candles_15m(ipo_id, ts DESC);

CREATE TABLE listing_observations (
  ipo_id          TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  obs_type        TEXT NOT NULL,                -- 'preopen_iep'|'preopen_qty'|'preopen_order_book'|'open'|'tick'
  observed_at     TEXT NOT NULL,
  value_json      TEXT NOT NULL,                -- {price, qty, side, buy_qty, sell_qty, ...}
  PRIMARY KEY (ipo_id, obs_type, observed_at)
);

CREATE TABLE listing_outcomes (
  ipo_id          TEXT PRIMARY KEY REFERENCES ipo(id) ON DELETE CASCADE,
  listing_open    TEXT, listing_high TEXT, listing_low TEXT, listing_close TEXT,
  gap_pct         TEXT,                         -- (open − issue)/issue × 100
  gap_bucket      TEXT NOT NULL,                -- 'LOW'|'MID'|'HIGH' per contract §4
  day1_close_pct  TEXT
);
```

```sql
-- 0003_engine.sql
CREATE TABLE valuation (
  ipo_id             TEXT PRIMARY KEY REFERENCES ipo(id) ON DELETE CASCADE,
  ipo_price          TEXT NOT NULL,
  eps                TEXT,
  peer_median_pe     TEXT,
  ipo_pe             TEXT,
  base_fair_value    TEXT,
  quality_factor     TEXT,
  structure_factor   TEXT,
  fair_value         TEXT,
  margin_of_safety_pct TEXT,
  status             TEXT NOT NULL,             -- 'OK'|'INSUFFICIENT_DATA'
  computed_at        TEXT NOT NULL
);

CREATE TABLE decisions (
  ipo_id             TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  decided_at         TEXT NOT NULL,
  company_quality    TEXT NOT NULL,             -- GOOD|NEUTRAL|WEAK
  trade_setup        TEXT NOT NULL,             -- ATTRACTIVE|FAIR|EXPENSIVE
  live_action        TEXT NOT NULL,             -- BUY NOW|WAIT|AVOID
  reasons_json       TEXT NOT NULL,
  PRIMARY KEY (ipo_id, decided_at)
);

CREATE TABLE rhp_findings (
  ipo_id             TEXT PRIMARY KEY REFERENCES ipo(id) ON DELETE CASCADE,
  verdict            TEXT,                      -- Sonnet forensic verdict
  full_json          TEXT NOT NULL,             -- $3/day cap upstream
  extracted_at       TEXT
);

CREATE TABLE insights (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id             TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  kind               TEXT NOT NULL,             -- 'red_flag'|'positive'|'commentary'
  body_json          TEXT NOT NULL,
  created_at         TEXT NOT NULL
);
CREATE INDEX insights_ipo_kind_idx ON insights(ipo_id, kind);
```

```sql
-- 0004_ops.sql (auth, access, pipeline observability — only what has an actual consumer)
CREATE TABLE platform_config (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE access_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL, name TEXT, note TEXT,
  status TEXT NOT NULL DEFAULT 'pending',       -- pending|approved|denied
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  decided_at TEXT
);
CREATE INDEX access_email_idx ON access_requests(email);

CREATE TABLE pipeline_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL, ended_at TEXT,
  status TEXT NOT NULL,                          -- ok|partial|failed
  meta_json TEXT
);

CREATE TABLE pipeline_steps (
  run_id INTEGER NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
  step TEXT NOT NULL, status TEXT NOT NULL,      -- ok|skipped|failed
  ms INTEGER, message TEXT,
  PRIMARY KEY (run_id, step)
);

CREATE TABLE pipeline_failures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  step TEXT NOT NULL, source TEXT, error TEXT NOT NULL,
  meta_json TEXT
);
CREATE INDEX pipeline_failures_time_idx ON pipeline_failures(occurred_at);

CREATE TABLE ipo_rhp_intel (
  ipo_id TEXT PRIMARY KEY REFERENCES ipo(id) ON DELETE CASCADE,
  full_json TEXT NOT NULL,
  extracted_at TEXT NOT NULL
);

CREATE TABLE ipo_research_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  source TEXT NOT NULL,                          -- 'sbi'|'broker'
  rating TEXT, peers_json TEXT, body TEXT,
  extracted_at TEXT
);
CREATE INDEX research_notes_ipo_idx ON ipo_research_notes(ipo_id);

CREATE TABLE ipo_tick_feed (
  ipo_id TEXT NOT NULL REFERENCES ipo(id) ON DELETE CASCADE,
  ts TEXT NOT NULL,
  ltp TEXT, bid TEXT, ask TEXT, qty INTEGER,
  PRIMARY KEY (ipo_id, ts)
);

-- Kite session: token persisted only until next TOTP rotation.
CREATE TABLE broker_sessions (
  broker TEXT PRIMARY KEY,                       -- 'zerodha'
  access_token TEXT, api_key TEXT, refreshed_at TEXT
);
```

Migrations land in `d1/migrations/` and are applied via `wrangler d1 migrations apply DB_CORE`.

---

## 4. Ingestion topology (how the Python pipeline talks to D1)

The pipeline stays in Python. Only its *sink* changes: instead of `psycopg2.connect(DATABASE_URL)` writing to Neon, it POSTs to an **Ingestion Worker** bound to `DB_CORE`. This preserves 60+ Python modules unchanged in behavior.

```
GH Actions cron  →  pipeline/cron.py  →  pipeline steps (Py)
                                           │
                                           ├─ read/write via HTTP:
                                           │     POST https://ingest.aacapitalprivatelimited.com/ingest/<table>
                                           │     Header: x-aac-ingest-key: <SECRET, rotated>
                                           │     Body: { rows: [...], mode: 'coalesce_empty'|'upsert' }
                                           │
                                           ▼
                                   Ingestion Worker (CF)
                                     - validates schema per table
                                     - enforces ISIN > exact-normalized-name identity rule
                                     - fill-empty-only vs upsert semantics
                                     - writes to DB_CORE (D1)
                                     - appends to source_facts
```

- **Read side of pipeline** (e.g. `build_snapshots.ts`) also switches from `NEON_READONLY_DATABASE_URL` to `wrangler d1 execute` (locally) or an internal `/read/<query_id>` on the Worker with a whitelisted, parameterized query catalog. No arbitrary SQL from Python; the query catalog is auditable.
- **Snapshot publisher** (`pipeline/publish_snapshot_with_ledger.py`) already POSTs to `SNAPSHOT_PUBLISH_URL`. Route target changes from Neon-backed to D1-backed; the KV write path (`lib/versioned-snapshot.ts`) is unchanged and already correct.
- **Kite ticker** stays exactly as-is (KV-only live path); the batched 60-second archival write moves from `ipo_tick_feed` in Neon to the same table in D1 via the ingest Worker.

Why this shape and not "rewrite the pipeline in Workers":

1. Playwright-based downloaders (`_scripts/download_sebi_rhps_playwright.py`, `_scripts/download_sbi_notes.py`) need a real Chromium; Workers can't run one. GH Actions runners can (already do).
2. Anthropic Sonnet extraction for RHP (`pipeline/rhp_sonnet.py`) uses `pymupdf`/`pdfplumber` for pre-processing — CPU-heavy, Python-native. Not a Worker fit.
3. Cost: keeping the runner strategy on GH Actions preserves ~$0/mo pipeline cost; Workers with equivalent CPU would incur real spend.
4. Cutting scope: only the *sink* changes, so blast radius is small and testable.

Where **CF Cron Triggers** *do* get added:

- KV **warm** jobs (post-pipeline KV rebuild) — trivial, no external deps.
- **Snapshot-freshness watchdog** — checks `snapshot:*:active` age, fires ntfy if stale.
- **Kite token-status watchdog** — reads `broker_sessions.refreshed_at` via ingest Worker RPC, alerts if > 24 h.

That way the CF Cron Triggers list is small, single-purpose, and auditable — not a wholesale port.

---

## 5. Public read plane (unchanged principle, minor code moves)

Post-migration, every allowlisted route in `lib/web-plane-db-contract.test.ts` falls into one of:

| Category | Count today | Plan |
|---|---|---|
| Public reads that already are KV-only | many | untouched |
| Reads with a KV contract but still on Neon (`admin/pipeline-failures`, `admin/pipeline-steps`, `ipo/cum-volume` history, `ipo/tick-feed` history) | 4 | ship the missing KV publishers; delete from allowlist |
| Writes (`access-note`, `admin/access`, `admin/jobs`, `admin/secrets`, `admin/kv-put`, `auth/zerodha/callback`, ...) | 9 | swap `sql` → new `db-d1` client bound via `DB_CORE`; **still not readable from the public plane** because the DB binding is only available to those specific routes' handlers |

**Rule to enforce:** in Wrangler routes/handlers, `DB_CORE` binding is only injected into the admin/auth/write cluster. Public read routes are compiled without that binding and the contract test asserts no import of `lib/db-d1` in `components/**` or in the non-allowlisted subtree of `app/**`. The current test only needs a rename + one new banned specifier.

---

## 6. Financial-precision policy (explicit, documented)

- **Unit convention** — one row of truth per field:
  | Field | Unit | Storage |
  |---|---|---|
  | `ipo_issue.issue_price`, `price_band_low/high`, `face_value` | ₹ per share | `TEXT` decimal string, 4 dp (`"41.5000"`) |
  | `*_cr` (issue_size, fresh, ofs, market_cap, revenue, pat, ebitda) | ₹ crore | `TEXT` decimal string, 4 dp |
  | `eps`, `roe`, `roce`, `debt_equity`, `*_margin`, `*_growth`, `*_pct`, `*_x` (subscription multiples) | ratio / % / multiplier | `TEXT` decimal string, 4 dp |
  | `lot_size`, `anchors_count`, `v` (volume), `qty` | integer count | `INTEGER` |
  | `d` | market-date IST | `TEXT` `YYYY-MM-DD` |
  | `ts`, `observed_at`, `captured_at`, `refreshed_at`, `created_at`, `updated_at` | timestamp | `TEXT` ISO-8601 UTC (always `Z`) |
- **No arithmetic in SQL** on rupee values. All fair-value / MoS / gap arithmetic happens in TS (`lib/fair-value.ts` — unchanged) or Python (`pipeline/*`).
- **Round-trip test** (part of the reconciliation suite): every migrated rupee value must satisfy `Neon.value == Decimal(D1.value)` exactly. Floats never touch these fields.

---

## 7. D1 storage & cost assessment

Assumptions (conservative): 200 IPO spine rows/yr, ~1,500 subscription snapshots/yr, ~150 tracked tickers for daily candles, ~50 tracked for 15-min bars, 25 listing days/yr.

| Table | Row count (1 yr) | Row size (est) | Yearly bytes | 5-yr bytes |
|---|---|---|---|---|
| `ipo` | 200 | 400 B | 80 KB | 400 KB |
| `ipo_issue` | 200 | 300 B | 60 KB | 300 KB |
| `subscription_snapshots` | 1,500 | 200 B | 300 KB | 1.5 MB |
| `financial_statements` | 600 | 250 B | 150 KB | 750 KB |
| `documents` (metadata) | 400 | 500 B (blob in R2) | 200 KB | 1 MB |
| `source_facts` | 30,000 | 500 B | 15 MB | 75 MB |
| `market_regimes` | 250 | 100 B | 25 KB | 125 KB |
| `market_candles` | 250 × 150 ≈ 37,500 | 120 B | 4.5 MB | 22.5 MB |
| `market_candles_15m` | 26 × 250 × 50 ≈ 325,000 | 120 B | 39 MB | 195 MB |
| `listing_observations` | 25 listings × ~2,000 obs | 300 B | 15 MB | 75 MB |
| `listing_outcomes` | 25 | 200 B | 5 KB | 25 KB |
| `valuation` + `decisions` + `insights` + `rhp_findings` | ~200 + logs | 1 KB avg | 500 KB | 2.5 MB |
| Pipeline ops tables (`runs`, `steps`, `failures`) | ~5,000/yr | 500 B | 2.5 MB | 12.5 MB |
| **Total** | | | **~77 MB/yr** | **~385 MB / 5 yr** |

- **D1 free tier: 5 GB storage, 5M reads/day, 100k writes/day.** We're two orders of magnitude under storage; well under writes (pipeline is 6–8 writer bursts/day of a few thousand rows each). No paid D1 tier needed until the app scales far beyond the personal-tool scope.
- **KV cost**: dominated by hot read snapshots. With `x-cache` HIT on almost every request, we bill only on the write-per-publication (< 20/day) plus reads. Free-tier headroom is comfortable.
- **R2**: already in use; no change. Documents remain immutable.

**Decision: single D1 database is correct.** Splitting to D1 Market only if `market_candles_15m` growth trajectory exceeds 5M rows or list of tracked tickers expands beyond IPO scope (contract §3 forbids the second condition anyway).

---

## 8. Migration plan (Stages A–H, non-destructive)

| Stage | What | Success gate | Rollback |
|---|---|---|---|
| **A. Schema** | Land `d1/migrations/0001–0004`; `wrangler d1 create aacapital_core`; `d1 migrations apply` in **staging** first. Land ingest Worker skeleton with no consumer yet. | `wrangler d1 execute --command 'SELECT name FROM sqlite_schema WHERE type=\"table\"'` returns exact expected set; `pipeline/inspect_schema.py` gets a D1 sibling and both report parity. | drop tables |
| **B. Historical copy** | Export Neon → transform → load D1. Copy script `_scripts/migrate/neon_to_d1.py` (new). Streams row-by-row per table, decimal-string coercion in Python (`decimal.Decimal → str`), timestamp coercion to UTC ISO. Idempotent (INSERT OR IGNORE on PK). | copy log: 100% of rows placed; per-table `SELECT COUNT(*)` matches Neon. | Neon untouched; D1 tables can be `DELETE FROM` and rerun |
| **C. Reconciliation** | `_scripts/migrate/reconcile.py`: for each table, compare (a) row count, (b) PK set, (c) FK integrity in D1, (d) representative critical-field diff on `ipo`, `ipo_issue.issue_price / price_band_*`, `subscription_snapshots`, `financial_statements`, `market_candles`, `market_candles_15m`, `listing_outcomes`, `valuation`, `decisions`. Report to `_migrate/reconciliation_report.md`. | zero diffs on rupee fields; zero orphan FKs; missing rows report ≤ 0 | fix loader, re-run B |
| **D. Parallel pipeline** | `pipeline/cron.py` gains flag `--sink both|neon|d1`. Default `both` for the parallel window. Every write goes to Neon (unchanged) AND to D1 via ingest Worker. Snapshot builder still reads Neon in this stage. | 2 weeks (10 business days incl. ≥1 listing day) of `--sink both` with zero unreconciled diffs after each daily run. | flip flag to `neon` |
| **E. Snapshot equivalence** | Snapshot builder gets a D1 backend (`build_snapshots.ts` alt). Publish to KV keys **prefixed with `d1:snapshot:*`** (not user-visible). Compare byte-for-byte with the primary snapshot each day for 10 days. | 10 consecutive days of `sha256(neon_snapshot) == sha256(d1_snapshot)` for every route. | none needed — never user-facing until F |
| **F. Cutover reads** | Flip `SNAPSHOT_PUBLISH_URL` to publish from D1-based snapshots. `snapshot:*:previous` still holds the Neon-built payload for one publish cycle → transparent rollback path already lives in `lib/versioned-snapshot.ts`. | production traffic sees no error rate change; ntfy silent; `x-cache` HIT rate unchanged. | flip publisher back; `snapshot:*:previous` still valid |
| **G. Cutover writes** | Flip `--sink d1` (Neon no longer written). Neon becomes read-only reference. Keep `--sink both` re-enable option in code. | 30 days of D1-only writes + green pipeline + zero regressions. | `--sink both` re-armed; Neon replays via reconciled diff |
| **H. Retire Neon** | After 30 clean days: dump `pg_dump` to R2, revoke DATABASE_URL from Actions secrets, remove `lib/db.ts`, remove pg from `package.json`, remove `psycopg2-binary` from `requirements.txt`, delete Neon project. | test suite green; `web-plane-db-contract.test.ts` passes with new ban list; no import of `pg`/`psycopg2` anywhere except archived paths. | irreversible — Stage G must be settled |

Neon is **never** deleted during the migration; the earliest deletion is Stage H, after 30 days of D1-only clean operation and after the pg dump lands in R2.

---

## 9. Test additions

- **`tests/d1_reconciliation.test.ts`** — parses the generated `_migrate/reconciliation_report.md` and fails CI if any diff row is present.
- **`tests/d1_migration_smoke.test.ts`** — spins up an ephemeral local D1 via `wrangler d1 execute --local`, applies migrations, seeds 10 canonical IPOs, exercises the ingest Worker's schema validation, asserts `source_facts` provenance rows appear.
- **`lib/web-plane-db-contract.test.ts`** — extended banned specifiers: `@/lib/db`, `@/lib/db-d1`, `pg`, `postgres`, `@neondatabase/*`, direct `D1Database` binding usage outside the allowlist.
- **`_scripts/tests/test_pipeline_sink.py`** — asserts `pipeline/cron.py --sink d1 --dry-run` writes nothing and prints the intended ingest payload; asserts `--sink both` calls both writers.
- **KV publish test** (already exists in `lib/versioned-snapshot.test.ts` / `lib/snapshot-integration.test.ts`) — no change needed.
- **Playwright UAT (uat/)** — add a KV-only assertion: block Neon FQDN at the browser layer during test; the app must render the last snapshot successfully.

---

## 10. Failure-behavior contract (preserved)

- If NSE / BSE / SEBI / Kite / Anthropic fails: writers already fall back to `SourceUnavailable` no-op (`pipeline/nse_identity_backfill.py`, `pipeline/cron.py`). D1 migration does **not** relax this; the ingest Worker rejects `null` overwrites of a previously non-null value unless the payload declares `mode: "correction"` (owner-approved path only).
- If D1 is unavailable: pipeline exits non-zero, ntfy fires, **KV is untouched** — the last valid snapshot keeps serving because `snapshot:*:active` was not rewritten. This is the same guarantee `publishVersionedSnapshot` gives today.
- If the snapshot builder produces malformed JSON: `readVersionedSnapshot` transparently reads `previous` (already implemented; `lib/versioned-snapshot.ts:24-33`).

---

## 11. Observability page (`/dashboard/ops` — small, internal)

Reads only from `SNAPSHOTS` KV (never D1):

- last successful discovery (from `snapshot:ipo-index:v1` published_at)
- last daily-pipeline run (from `snapshot:pipeline-health:v1` — new B-2 contract)
- last subscription capture / listing-day capture
- last document / RHP / SBI refresh
- last snapshot publication + active version + age
- source status (from `pipeline_failures` published as `snapshot:pipeline-health:v1`)
- D1 migration stage indicator (A–H) from `platform_config` mirrored into KV

No secrets, no raw error bodies — status booleans and timestamps only.

---

## 12. Cost control assertions before we start writing code

- No new paid service. D1 free tier suffices (§7).
- Anthropic caps (`RHP $3/day`, `SBI $0.50/day`) already in `platform_config`; unaffected by migration.
- Kite tick capture already batched to 60 s (`docs/architecture/ASSET_LIGHT_ARCHITECTURE.md` Step 3); unaffected.
- KV writes at publication cadence (≤ 20/day) + rare warm; unaffected.
- No new "keep-alive" polling loops added. CF Cron Triggers added are edge-scheduled; they cost nothing at this scale.

---

## 13. Risks & blockers

| # | Risk | Mitigation |
|---|---|---|
| R1 | D1 SQL dialect surprises (e.g. `GENERATED ... STORED` semantics, JSON functions, window functions availability) | Stage A includes a smoke query catalog run against `--local` D1; any incompatibility is caught before ingest is wired |
| R2 | Decimal-string fields lose ordering in SQL `ORDER BY` (`"9.00" > "10.00"` lexicographically) | Every rupee-sort adds a paired integer sort key column (e.g. `issue_price_paise INTEGER`), populated by the writer. Documented in `d1/CONVENTIONS.md` |
| R3 | Python `psycopg2` → HTTP ingest adds latency to a run that already touches 60+ modules | Ingest Worker accepts batched payloads (`rows: [...]`); pipeline batches per step (already true for `fill_v2`, `kite_fetch`). Expected added latency: < 30 s per run |
| R4 | Wrangler cron trigger drift (CF cron min granularity, cold start) vs GH Actions | Keep the pipeline itself on GH Actions during the migration; only add CF cron for **KV warm** and **watchdog** roles until we're confident in CF triggers for a listing-day-critical role |
| R5 | Namespace confusion (`JOB_FLAG` and `CACHE` share id today) | Stage A creates real `CACHE` and `SNAPSHOTS` namespaces with `wrangler kv namespace create`, updates `wrangler.jsonc` in the same commit that lands the D1 binding |
| R6 | Neon-era views used silently by TS builders | Grep pass in Stage A across `pipeline/build/*.ts` and `_scripts/**/*.sql` before migration; recreate as build-time TS query composers |
| R7 | 15-min candle growth outstripping estimate (§7) | Reconciliation report includes a growth-projection table each day; if trajectory exceeds 3 M rows/yr, trigger the D1 Market split under the pre-approved plan §3.1 |
| R8 | Kite session table + TOTP secret handling on D1 | `broker_sessions.access_token` stored plaintext today in Neon; keep same policy under D1 (row-level access via binding scope). No secrets mirrored into KV, ever |
| R9 | Rollback complexity in Stage G | `--sink both` is a permanent flag, not a temporary hack — leaving it in the codebase for 90 days post-cutover costs nothing and buys a one-command rollback |
| R10 | Two builds during Stages D/E doubling pipeline runtime | Ingest Worker is async; Python `--sink both` fires-and-forgets to D1 while continuing Neon writes. Additional runtime < 20 s |

---

## 14. What I need from you before writing code

1. **Confirm the plan direction** (D1 + KV, Python pipeline stays, single D1 to start).
2. **Cloudflare account access.** I do not need to be handed the API token; you run `wrangler` locally or via GH Actions. But I need to know:
   - CF account id (only if you want the created binding ids pre-filled)
   - Preferred DB name (`aacapital_core` proposed) — confirm.
   - Whether you want the **ingest Worker** on a subdomain (`ingest.aacapitalprivatelimited.com`) or a `*.workers.dev` route (both work).
3. **Neon export access.** For Stage B I need one of:
   - a read-only `NEON_READONLY_DATABASE_URL` (Actions secret already referenced in `pipeline.yml`) — best;
   - or a `pg_dump` you place in R2 and point me to.
4. **Green-light for the wrangler-config PR.** The first code change is a *config-only* PR: real CACHE + SNAPSHOTS namespaces, D1 binding placeholder (id TBD), cron trigger list added but commented, no code changes to routes. That PR is safe to review and merge before we touch anything else.
5. **Confirm the KV namespace split** (fix the shared `JOB_FLAG`/`CACHE` id incident) can land in the same PR.

Once you approve, I execute Stage A end-to-end and land it as a single reviewable PR titled `feat(d1): stage A — schema + ingest worker + namespaces`. Then we take Stage B on its own PR, and so on. Nothing merges past staging until reconciliation is green.

---

_Prepared as the audit output required by the Cloudflare-native migration brief (Phase-0 execution rule). Every table, path and cron above is grounded in a real file in `main` at HEAD (commit `8b05a27`, 2026-08-19)._
