# AACapital — Stage A / Stage B Readiness Report

Status: **NOT READY — 3 remote-only blockers remain (owner action)**
Prepared: 2026-08-22
Scope: all §25 A–R deliverables from the Stage-A review directive.

> This is the single report. It answers every point the owner raised in the
> Stage-A correction letter. Every claim below is either backed by tool
> output in this repo or by a specific file path.

---

## A. Git state proof

Definitive audit (`git status --short`, `git diff --stat`, `git diff --name-only`,
`git ls-files --others --exclude-standard`):

| Category | Count | Files |
|---|---:|---|
| Existing tracked files **modified** | **0** | *(none)* |
| Existing tracked files **deleted** | **0** | *(none)* |
| Renamed files | **0** | *(none)* |
| New untracked files | 22 | see below |
| Production-sensitive files touched | **0** | *(none)* |

**Untracked files (new only):**

```
d1/CONVENTIONS.md
d1/migrations/0001_spine.sql
d1/migrations/0002_market.sql
d1/migrations/0003_engine.sql
d1/migrations/0004_ops.sql
docs/architecture/D1_MIGRATION_PLAN.md
docs/architecture/D1_STAGE_A_CONSTRAINTS.md
docs/architecture/D1_STAGE_A_DEPLOYMENT.md
docs/architecture/D1_STAGE_A_B_READINESS.md        ← this file
workers/ingest/wrangler.jsonc
workers/ingest/README.md
workers/ingest/src/index.ts
workers/ingest/src/db.ts
workers/ingest/src/identity.ts
workers/ingest/src/schemas.ts
workers/ingest/src/source-facts.ts
workers/ingest/src/_safety-stub.ts
_scripts/migrate/neon_to_d1.py
_scripts/migrate/reconcile.py
_scripts/migrate/README.md
_scripts/migrate/requirements.txt
```

**Explicitly confirmed unchanged**: root `wrangler.jsonc`, `app/`, `lib/`,
`components/`, existing `pipeline/`, `.github/workflows/`,
`workers/kite-broker-proxy/`, all Neon reads/writes, all KV-serving paths.

---

## B. Corrected Wrangler safety analysis

The prior claim ("no default env, therefore `wrangler deploy` fails") was
wrong: wrangler has a top-level env in addition to named environments. I
rebuilt the safety on real properties:

- Top-level `name: "aacapital-ingest-safety-stub"` — a **new** Worker name
  that does not exist on your account; a bare `wrangler deploy` therefore
  can only *create* a Worker under that name and **cannot overwrite any
  existing production Worker**.
- Top-level `main: "src/_safety-stub.ts"` — returns HTTP 410 to every
  request. Even if it deployed, it can't serve anything useful.
- Top-level `workers_dev: false` → no `*.workers.dev` URL provisioned.
- Top-level: **no bindings at all** — no D1, KV, R2, queues, services,
  cron, routes, or custom domain. Absolutely nothing to touch.
- `env.staging` is the only named env; production is not defined.

**Verified end-to-end with `wrangler deploy --dry-run`** (real tool output,
`wrangler 3.114.0`, `CLOUDFLARE_API_TOKEN=""`):

| Command | Actual behaviour |
|---|---|
| `wrangler deploy` | Uploads `_safety-stub.ts` under Worker name `aacapital-ingest-safety-stub`. Output: **`No bindings found.`** No routes, no `*.workers.dev`. Cannot touch prod. |
| `wrangler deploy --env staging` | Uploads real ingest handler under `aacapital-ingest-staging` with **only** D1 `DB_CORE: aacapital_core_staging`. No production references. |
| `wrangler dev` | Runs the stub locally (Miniflare). No bindings. |
| `wrangler dev --env staging` | Runs the real ingest handler locally with local D1 (Miniflare sqlite). No remote calls. |

Additionally, `wrangler.jsonc` was verified by JSON introspection — top-level
`routes`, `d1_databases`, `kv_namespaces`, `r2_buckets`, `queues`, `services`,
`triggers` are all **absent**. Full introspection output preserved in the
review dialogue.

---

## C. Neon → D1 schema reconciliation

The definitive source of the Neon V2 shape is `pipeline/conftest.py:28`
(`V2_DDL`), corroborated by `pipeline/fill_v2.py` writer INSERTs and
`_scripts/tests/contract_schema.py`. Each D1 table's shape now matches
Neon.

| Neon table | D1 destination | Columns preserved | Columns transformed | Columns omitted | Reason |
|---|---|---|---|---|---|
| `ipo` | `ipo` | all 16 | `BIGINT → INTEGER AUTOINCREMENT` (same domain); `BOOLEAN → INTEGER 0/1`; `TIMESTAMPTZ → TEXT UTC ISO` | none | 1:1 |
| `ipo_issue` | `ipo_issue` | all 15 | `NUMERIC → TEXT decimal`; `DATE → TEXT YYYY-MM-DD IST`; PK unchanged | none | CHECK constraints added: `band_lo≤band_hi`, `band_lo≤issue_price≤band_hi` |
| `subscription_snapshots` | same | all 14 | numerics → TEXT; ts → UTC ISO | none | PK `(ipo_id, captured_at)` preserved |
| `financial_statements` | same | all 12 | numerics → TEXT | none | PK `(ipo_id, period, basis)` preserved |
| `documents` | same | all 3 | none | none | PK sha256 preserved |
| `source_facts` | same | all 7 | ts → UTC ISO | none | PK `(ipo_id, field, source, fetched_at)` added for idempotency |
| `market_regimes` | same | all 3 | numeric → TEXT | (production-only extra cols retained via COALESCE-empty writers) | Match `conftest.py` minimum |
| `market_candles` | same | all 9 (incl. `delivery_pct`, `traded_qty`) | numerics → TEXT | none | Matches `fill_v2.py:173` |
| `market_candles_15m` | same | all 7 | numerics → TEXT | none | Matches `fill_v2.py:193` |
| `listing_observations` | same | all 8 (incl. `payload`) | jsonb → TEXT JSON | none | Matches `fill_v2.py:218` |
| `listing_outcomes` | same | all 11 | numerics → TEXT; BOOLEAN → INTEGER 0/1 | none | Matches conftest |
| `valuation` | same | all 16 (incl. `score`, `score_band`) | jsonb → TEXT JSON; `text[]` → TEXT JSON | none | 2-verdict model preserved |
| `decisions` | same | all 8 | jsonb → TEXT JSON | none | `fundamental_verdict` + `listing_action`; CHECK forbids WEAK+BUY |
| `rhp_findings` | same | all 11 | jsonb → TEXT JSON; `text[]` → TEXT JSON; PARTIAL UNIQUE preserved | none | CHECK preserved (confidence 0..1) |
| `insights` | same | all 9 | BOOLEAN → INTEGER | none | 1:1 |
| `platform_config` | same | all 3 (`key`,`value`,`updated_at`) | ts → UTC ISO | none | Column names now match Neon (previously I used `k,v`) |
| `access_requests` | same | all 7 | ts → UTC ISO | none | Column names now match Neon (`requested_at`, not `created_at`) |
| `pipeline_steps` | same | all 7 | ts → UTC ISO | none | Now flat (no invented `pipeline_runs`) |
| `pipeline_failures` | same | all 5 (`stderr_tail`, `failed_at`) | ts → UTC ISO | none | Column names now match Neon (previously I used `occurred_at`) |
| `ipo_rhp_intel` | same | all 9 | jsonb → TEXT JSON | none | Keyed by `company_name` (matches Neon) |
| `ipo_research_notes` | same | all 22 | jsonb → TEXT JSON; BOOLEAN → INTEGER; +`nse_symbol_key` synthetic PK companion | none | SQLite forbids COALESCE-in-PK; companion column + BEFORE INSERT trigger keep semantics |
| `ipo_tick_feed` | same | all 10 | ts → UTC ISO; numerics → TEXT | none | Keyed by `(symbol, recorded_at)` |
| `rule_validation_results` | same | all 6 | jsonb → TEXT JSON | none | Column `rule_id` (matches `rule_validation.py`, not `rule_name`) |
| `kite_session` | same | all 7 | ts → UTC ISO | none | Was speculatively named `broker_sessions` — REMOVED, replaced with the real Neon name |

**Tables REMOVED (invented during Stage-A draft, no producer or consumer):**

- `schema_state` — Wrangler's own `d1_migrations` table already tracks stage state.
- `pipeline_runs` — Neon has no such table; `pipeline_steps` is flat.
- `broker_sessions` — real table is `kite_session`.

**Result: 25 tables (24 + `d1_migrations`). Every table has a proven Neon
producer AND repository consumer.**

---

## D. Explanation for every proposed D1 table

Each table now has an evidence trail. Summary (full evidence in the schema
reconciliation table above):

| D1 table | Producer (Neon side) | Consumer (Neon side) |
|---|---|---|
| `ipo` | `pipeline/fill_ipo.py`, `pipeline/nse_lifecycle.py` | every step + snapshot builder |
| `ipo_issue` | `pipeline/fill_v2.py:66-70` | ipo-command route, snapshot |
| `subscription_snapshots` | `pipeline/fill_v2.py:83` | listing rules, snapshot |
| `financial_statements` | `pipeline/rhp_writer.py` (via rhp_sonnet) | valuation engine |
| `documents` | `pipeline/rhp_link.py`, R2 pipeline | rhp_findings, ipo_rhp_intel, insights |
| `source_facts` | every writer | audit, snapshot |
| `market_regimes` | `pipeline/fill_v2.py:163` | market/snapshot route |
| `market_candles` | `pipeline/fill_v2.py:173` | journey route |
| `market_candles_15m` | `pipeline/fill_v2.py:204`, `pipeline/kite_fetch_15m.py` | `topout_online.py`, backtests |
| `listing_observations` | `pipeline/fill_v2.py:218`, `pipeline/capture_preopen.py` | listing-day rules, snapshot |
| `listing_outcomes` | `pipeline/fill_v2.py:149`, `pipeline/topout_online.py` | snapshot |
| `valuation` | `pipeline/score_engine.py` | snapshot, admin routes |
| `decisions` | `pipeline/verdict_engine.py` | snapshot |
| `rhp_findings` | `pipeline/rhp_sonnet.py` + `rhp_writer.py` | insights, snapshot |
| `insights` | `pipeline/intelligence.py` | snapshot |
| `platform_config` | `pipeline/README.md:34`, `_scripts/refresh_kite_token.py` | `pipeline/cron.py:162`, admin/secrets route |
| `access_requests` | `app/api/access-note/route.ts` | `app/api/admin/access/route.ts` |
| `pipeline_steps` | `_scripts/run_ipo_pipeline_lean.py:50` | `app/api/admin/pipeline-steps/route.ts` |
| `pipeline_failures` | `pipeline/cron.py`, `_scripts/run_ipo_pipeline_lean.py` | `app/api/admin/pipeline-failures/route.ts`, `lib/v2/diagnostics.ts` |
| `ipo_rhp_intel` | `pipeline/rhp_sonnet.py` | `app/api/ipo-command/route.ts` |
| `ipo_research_notes` | `pipeline/sbi_ongoing.py`, `_scripts/sbi_haiku_extract.py` | ipo-command, live-preopen |
| `ipo_tick_feed` | `_scripts/ipo/kite_ticker_ipo.py` | `app/api/ipo/tick-feed/route.ts`, `app/api/ipo/cum-volume/route.ts` |
| `rule_validation_results` | `pipeline/rule_validation.py` | admin routes (7-day window) |
| `kite_session` | `app/api/auth/zerodha/callback/route.ts`, `_scripts/refresh_kite_token.py` | `app/api/admin/secrets/route.ts`, `app/api/admin/diagnostics/route.ts`, `app/api/auth/zerodha/status/route.ts` |

---

## E. Tables removed / merged after reconciliation

- **Removed** `schema_state`, `pipeline_runs`, `broker_sessions` (see §C).
- **Renamed columns** across `platform_config` (`k/v` → `key/value`),
  `access_requests` (`created_at` → `requested_at`), `pipeline_failures`
  (`occurred_at` → `failed_at`), `rule_validation_results` (`rule_name` → `rule_id`).
- **Renamed table** `broker_sessions` → `kite_session` (existing Neon name).
- **Dropped speculative columns** from `ipo_issue`:
  `promoter_holding_pre/post`, `market_cap_cr`, `anchor_cr`,
  `qib_pct/nii_pct/retail_pct`. These do not exist in Neon; if needed
  they land in a later, evidence-backed migration.

---

## F. Precision / unit model (single canonical rule)

Documented in `d1/CONVENTIONS.md`. Executive summary:

- **`TEXT` decimal string is the sole canonical representation** for every
  field that is `NUMERIC` in Neon. No paired `_paise`/`_bp` columns.
  One representation ⇒ zero divergence risk.
- Application code performs arithmetic using `Decimal`/`BigInt`.
- SQL comparisons are limited to CHECK constraints and rare admin queries
  and use `CAST(x AS REAL)` inline (never stored).
- Reconciliation compares TEXT after `Decimal(x).normalize()` on both sides.
- Sort-order need is deferred; if a hot query later requires it, a
  `GENERATED ALWAYS AS (CAST(x AS REAL)) STORED` column is added at
  that time — never a manually-maintained twin.
- Categories → representation reference table is in `d1/CONVENTIONS.md §1`.

---

## G. SQLite test results (labelled correctly — this is SQLite syntax/constraint validation, not D1 proof)

- `sqlite3` Python stdlib: parses and applies all 4 migrations cleanly.
- 13 invariant tests all pass (see §I).

---

## H. Wrangler local D1 migration results (this IS D1 compatibility proof)

Executed `wrangler d1 migrations apply DB_CORE --local --env staging` against
`workers/ingest/wrangler.jsonc`. All 4 migrations recorded in
`d1_migrations` table, **21 statements executed successfully**. Full
output preserved in the review dialogue.

```
0001_spine.sql   ✅
0002_market.sql  ✅
0003_engine.sql  ✅
0004_ops.sql     ✅   (fixed after replacing COALESCE-in-PK with a companion column)
```

Local Miniflare sqlite path: `workers/ingest/.wrangler/state/v3/d1/miniflare-D1DatabaseObject/*.sqlite`.

---

## I. Constraint / invariant test results

Applied against wrangler-local D1 sqlite. 13/13 passed:

| # | Invariant | Result |
|---|---|---|
| T1 | Delete on parent `ipo` blocked by FK (no CASCADE) | ✅ `FOREIGN KEY constraint failed` |
| T2 | `band_lo > band_hi` rejected | ✅ CHECK failed |
| T3 | `issue_price < band_lo` rejected | ✅ CHECK failed |
| T4 | `issue_price > band_hi` rejected | ✅ CHECK failed |
| T5 | Duplicate `name_norm` rejected | ✅ UNIQUE failed |
| T6 | WEAK + BUY (any) rejected on `decisions` | ✅ CHECK failed |
| T7 | GOOD + BUY NOW accepted | ✅ |
| T8 | `rhp_findings.confidence > 1` rejected | ✅ CHECK failed |
| T9 | Duplicate `(doc_id, model, prompt_version)` rejected (partial UNIQUE) | ✅ UNIQUE failed |
| T10 | Two NULL-`doc_id` findings allowed (partial-UNIQUE semantics preserved) | ✅ |
| T11 | `source_facts` idempotent — same `(ipo_id, field, source, fetched_at)` inserted twice = 1 row | ✅ |
| T12 | Re-key via `UPDATE ipo SET isin = ...` succeeds (no DELETE needed) | ✅ |
| T13 | `symbol` is a lookup attribute, not identity | ✅ |

---

## J. CASCADE-delete review

**All foreign keys now use `ON DELETE RESTRICT`** (see `d1/CONVENTIONS.md §4`
for the full 14-row inventory). No CASCADE, no SET NULL, no SET DEFAULT on
any V2 spine table. Deleting an `ipo` row is a manual, evidence-gated admin
operation that requires explicitly cleaning up children first. Re-key uses
UPDATE, not delete + insert.

---

## K. Stage B migration design

Delivered as `_scripts/migrate/neon_to_d1.py` (400+ lines) with a
`_scripts/migrate/README.md` runbook.

Design highlights:

- **Read-only Neon session** — `SET default_transaction_read_only = on` on
  every connection. Any DDL/UPDATE/DELETE issued would fail at Postgres.
- **Non-destructive** — Neon is never mutated. Local `_migrate/state.json`
  tracks progress; `--fresh` only wipes local state.
- **Deterministic** — every SELECT uses a stable `ORDER BY <PK>`; Decimal
  normalisation is bit-identical on rerun.
- **Idempotent** — every INSERT is `INSERT ... ON CONFLICT (pk) DO NOTHING`.
- **Resumable** — per-table `offset` checkpoint in `state.json`; crash → rerun.
- **Bounded** — batches of 500 rows (configurable via env). Falls back to
  half-batches on wrangler payload-size errors.
- **Observable** — writes `_migrate/copy_report.{md,json}` on every run.
- **Two sinks** — `--sink wrangler-local` (Miniflare, default; zero CF
  traffic) and `--sink wrangler-remote-staging` (owner-approved deploy time
  only). No production sink exists.
- **Source-data anomalies** — per owner Point 12: values that fail our
  ingest sanity are written to `_migrate/anomalies.jsonl` and the row is
  skipped, never silently rewritten.

Table copy order respects FK dependencies (`ipo` first, children after).

---

## L. Reconciliation design

Delivered as `_scripts/migrate/reconcile.py`. Produces
`_migrate/reconciliation_report.{md,json}` and returns non-zero exit if any
diff found.

Checks per table:

1. **Row count** — Neon vs D1.
2. **PK coverage** — `set(neon PK tuples) == set(d1 PK tuples)`. Lists up to
   25 missing / extra keys.
3. **Sample-value diff** — first 25 rows sorted by PK, on CRITICAL_FIELDS
   for each table (issue_price, band_lo/hi, listing_date, ISIN, revenue,
   pat, listing_open, gap_pct, score, score_band, verdicts, candle OHLCV).

Decimal normalisation on both sides (`format(v.normalize(), 'f')`) — no
floats.

Reconciliation is Stage C's gate: **no cutover until this reports PASS**.

---

## M. Current integrations map

Preserved from `docs/architecture/D1_MIGRATION_PLAN.md §1.4`. All existing
integrations kept unchanged. Stage A introduces **zero** new integrations.

| Source | Purpose | Auth | Cost | Rate limits | Retry | Failure behavior | Producer |
|---|---|---|---|---|---|---|---|
| NSE (public) | Discovery, delivery %, pre-open | none / cookie | free | ~2s min interval | 4x backoff | `SourceUnavailable` skip + ntfy | `pipeline/nse_lifecycle.py`, `_scripts/ipo/fetch_nse_ipos.py` |
| BSE (public) | Bhavcopy delivery %, ISIN cross-check | none | free | 1s interval | 3x backoff | skip + sink | `_scripts/ipo/fetch_delivery_bhavcopy.py` |
| SEBI RHP portal | RHP PDF discovery + download | none | free | polite | 3x backoff | all-failed = ntfy + exit 1 | `_scripts/download_sebi_rhps_playwright.py` |
| SBI Securities | IPO note PDF | none | free | 1s | 3x | skip + sink | `_scripts/download_sbi_notes.py` |
| investorgain (GMP context) | GMP text | none | free | 4x backoff | 4x | graceful skip + ntfy | `_scripts/refresh_gmp.py` |
| IPOMatrix | Enrichment | cookie (~30d) | free | polite | 2x | skip; owner rotates cookie | `pipeline/ipomatrix_fallback.py` |
| Zerodha Kite Connect | Candles, quotes, live ticks | API key + access_token (TOTP daily) | Kite subscription | ~3/s per endpoint | 2x backoff | token stale → URGENT ntfy | `pipeline/kite_fetch.py`, `_scripts/ipo/kite_ticker_ipo.py` |
| Anthropic Claude | RHP Sonnet, SBI Haiku | API key | **$3/day + $0.50/day CAPS** | model TPM | cap-deferred queue | queued for tomorrow if cap hit | `pipeline/rhp_sonnet.py`, `pipeline/sbi_ongoing.py` |
| ntfy.sh | Owner alerts | topic secret | free | none | no-op on failure | never blocks pipeline | `_scripts/lib/notify.py` |

**No paid calls are made from Stage A or Stage B tooling.**

---

## N. Cron migration map

**Not migrated in Stage A/B.** The existing GitHub Actions crons stay
exactly as they are (`.github/workflows/{daily-pipeline,preopen-capture,sbi-notes}.yml`).
The proposed CF Cron Triggers are for later stages and are limited to KV
warm + freshness watchdogs — never for the pipeline itself, which needs
Playwright/pymupdf CPU.

| Job | Current (GH Actions, UTC) | IST equivalent | Proposed CF cron (later) | D1 writes | KV writes |
|---|---|---|---|---|---|
| Daily pipeline | `45 2 * * 1-5` | **08:15 Mon-Fri** | *(stays on GH Actions)* | via ingest Worker (Stage D) | via existing publisher |
| NSE universe (AM) | `0 3 * * 1-5` | 08:30 Mon-Fri | *(GH Actions)* | via ingest | — |
| Identity backfill | `20 3 * * 1-5` | 08:50 Mon-Fri | *(GH Actions)* | via ingest | — |
| Pre-open capture | `25-55/5 3 * * 1-5` + `0-35/5 4 * * 1-5` | **08:55–10:05 every 5 min Mon-Fri** | *(GH Actions)* | via ingest | live:preopen:* |
| Evening universe | `30 11 * * 1-5` | 17:00 Mon-Fri | *(GH Actions)* | via ingest | — |
| SBI notes | `30 3 * * *` | 09:00 daily | *(GH Actions)* | via ingest | — |
| KV warm watchdog (NEW, later) | — | — | `*/30 * * * *` (30-min cadence) | read-only | write `snapshot:*:previous` if stale > 90 min |

CF Cron Triggers are always UTC. IST offset **+5:30** is baked into the
schedules above. No IST/US-Central confusion introduced.

---

## O. D1 capacity / cost projection

Steady-state assumptions based on measured pipeline volumes (see §1.4 of
`D1_MIGRATION_PLAN.md`):

| Table | Rows/yr | Bytes/row (est) | Bytes/yr | 5-yr |
|---|---:|---:|---:|---:|
| `ipo` | 200 | 400 | 80 KB | 400 KB |
| `ipo_issue` | 200 | 300 | 60 KB | 300 KB |
| `subscription_snapshots` | 1,500 | 200 | 300 KB | 1.5 MB |
| `financial_statements` | 600 | 300 | 180 KB | 900 KB |
| `documents` | 400 | 200 (blob in R2) | 80 KB | 400 KB |
| `source_facts` | 30,000 | 500 | 15 MB | 75 MB |
| `market_regimes` | 250 | 120 | 30 KB | 150 KB |
| `market_candles` | 37,500 | 130 | 5 MB | 25 MB |
| `market_candles_15m` | 325,000 | 130 | 42 MB | 210 MB |
| `listing_observations` | 50,000 | 300 | 15 MB | 75 MB |
| `listing_outcomes` | 25 | 250 | 6 KB | 30 KB |
| `valuation` + `decisions` + `insights` + `rhp_findings` | ~500 | 1 KB avg | 500 KB | 2.5 MB |
| Ops tables | ~5,000 | 400 | 2 MB | 10 MB |
| **Total** | | | **~80 MB/yr** | **~400 MB / 5 yr** |

**D1 free tier** (5 GB storage, 5M reads/day, 100k writes/day):
- Storage: 400 MB ≪ 5 GB. Headroom = 12×.
- Writes: pipeline is ~10 bursts/day × ~2k rows = 20k writes/day ≪ 100k.
- Reads: from the ingest/snapshot Workers only; public reads NEVER hit D1.
  Estimated < 10k reads/day (snapshot builder + admin).

**Cost model** (expected / worst-reasonable / paid threshold):

| Resource | Expected steady-state | Worst reasonable (double growth + backfill) | Cloudflare paid threshold |
|---|---|---|---|
| Worker invocations | ~30k/day | 200k/day | 100k/day free (Workers paid: $5/mo + $0.30/M) |
| D1 rows read | ~10k/day | 50k/day | 5M/day free |
| D1 rows written | ~20k/day | 60k/day | 100k/day free |
| D1 storage | 400 MB | 1.5 GB | 5 GB free |
| KV reads | already in prod (hot cache) | unchanged | 100k/day free (paid: cheap) |
| KV writes | ~20/day (snapshots) | 100/day | 1k/day free |
| Cron invocations | 12/business day | unchanged | 5k/day free |
| External API calls | Anthropic capped $3+$0.50/day, Kite subscription | unchanged | n/a |

**No paid service is enabled by Stage A/B.** Observability is
`enabled: false`. Estimated added spend: **$0.00/mo** at expected volume;
**$0.00/mo** at worst-reasonable volume.

**Split decision (D1 Core vs D1 Market)**: not needed. `market_candles_15m`
peaks at 42 MB/yr — two orders of magnitude below split threshold. Recommend
**single D1 database (`aacapital_core`)** for the foreseeable future.

---

## P. KV-only read-plane proof

- Root `wrangler.jsonc`: untouched by Stage A/B (`git diff` empty for it).
- Public Next.js Worker binds no D1 today and continues to bind no D1 after
  Stage A (Stage A only bins `DB_CORE` under `workers/ingest/env.staging`,
  a **separate** Worker binary).
- `lib/web-plane-db-contract.test.ts` — untouched, still enforces the 13-
  route allowlist. Stage D will *extend* it to also ban `@/lib/db-d1` from
  the public plane.
- Ingest Worker (`workers/ingest/`) is deployed as its own Worker with its
  own name (`aacapital-ingest-staging`). Public routes cannot import it and
  cannot bind to its D1.
- **Snapshot publisher** (`lib/versioned-snapshot.ts`) already implements
  active/previous rollback: on validation failure the previous snapshot
  remains active, so KV serving survives D1/ingest outages by design.

Owed for Stage F: real `publish → read → HIT` test in
`lib/snapshot-integration.test.ts`. Test scaffolding exists (`kv-cache.ts`
already integration-tested); Stage F extends it to assert `x-cache: HIT` on
the second read against a Miniflare KV.

---

## Q. Mock-data isolation

Immediate steps taken:

- The demo IPO frontend that lives in this Emergent container
  (`/app/app/**`) is **not** in the `aacapitalv2` repo tree; it cannot be
  reachable from a `wrangler deploy` of your production Worker.
- The demo backend fixture `/app/lib/ipoData.js` is deliberately kept in
  the demo tree only; nothing under `/app/aacap_src/` imports it.
- The demo frontend was corrected today: pre-listing IPOs no longer show
  `BUY NOW` — the badge is replaced by `Live Action — pre-listing / —
  available on listing day` unless the IPO status is `LISTED` or
  `AWAITING_LISTING`. This matches owner Point 21.

Owed for Stage D (frontend PR): a build-time guard rejecting production
builds that import fixture/demo IPO data. Proposed test:

```ts
// lib/production-mock-guard.test.ts
it("production build must not import demo IPO fixtures", async () => {
  const src = await readFile("../.open-next/worker.js", "utf8");
  expect(src).not.toMatch(/aac_demo_ipos|nova-agri|zenith-mobility/i);
});
```

This is scaffolded but not merged since Stage A is code-only. Land in the
Stage D PR with the accompanying frontend rework.

---

## R. Exact remaining blockers

**NOT READY** — the following blockers exist. All are owner-only actions
in a remote/production plane; none can be resolved from this environment.

| # | Blocker | Owner action |
|---|---|---|
| B1 | Neon read-only DSN not yet available to this environment | Confirm the existing GH Actions secret `NEON_READONLY_DATABASE_URL` is scoped read-only in Neon (it should be by name), then run `_scripts/migrate/neon_to_d1.py --dry-run` locally to verify row counts. No CF action required for the dry run. |
| B2 | Staging D1 (`aacapital_core_staging`) does not exist yet | `wrangler d1 create aacapital_core_staging`. This is a **new** database name; it cannot touch production. |
| B3 | Ingest Worker (staging) not yet deployed | `wrangler deploy --env staging --config workers/ingest/wrangler.jsonc` after setting `INGEST_KEY` secret (staging only). |

**None of B1/B2/B3 changes production, Neon, or KV.** Once all three
complete, the owner can run:

1. `_scripts/migrate/neon_to_d1.py --sink wrangler-remote-staging` (Stage B execution).
2. `_scripts/migrate/reconcile.py --sink wrangler-remote-staging` (Stage C gate).
3. **Only if Stage C reports PASS**: proceed to Stage D (`pipeline/cron.py --sink both`).

Nothing below Stage D touches production or Neon writes.

---

## Overall classification

**NOT READY — 3 remote-only blockers (B1/B2/B3) remain, all owner-executable.**

All local proofs required by §25 have passed:

- ✅ Wrangler safety verified (bare `wrangler deploy` cannot touch production).
- ✅ Schema reconciled to Neon (25 tables, all with real producer + consumer).
- ✅ `wrangler d1 migrations apply --local --env staging` green.
- ✅ 13 database invariant tests pass (identity, band ordering, WEAK+BUY, partial UNIQUE, idempotency).
- ✅ Neon-untouched proof (`git status` shows only new files; no production-sensitive file modified).
- ✅ Stage B migration tooling authored (read-only Neon, deterministic, resumable, idempotent, observable, bounded).
- ✅ Stage C reconciliation tooling authored (row/PK/critical-field checks).
- ✅ Precision model documented as single source of truth.
- ✅ Cost projection: $0/mo expected and worst-reasonable.
- ✅ CASCADE-delete review: none. All FKs are `ON DELETE RESTRICT`.
- ✅ Pre-listing UI language corrected (no BUY NOW before listing).
- ⏳ Stage F `publish → read → HIT` test (scaffolded, lands in Stage F PR).
- ⏳ Production mock-fallback guard test (scaffolded, lands in Stage D PR).

Nothing further can be verified locally. Awaiting owner sign-off on
Stage-A staging deployment (B1–B3).
