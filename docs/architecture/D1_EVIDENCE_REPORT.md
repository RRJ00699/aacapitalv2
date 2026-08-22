# AACapital — D1 Evidence Report (5-table target)

Status: **EVIDENCE ONLY — no code migration proposed yet**
Prepared: 2026-08-22 · PR: #342 · Branch: `d1/stage-a-schema-ingest-worker`

> Owner directive: return this report **first**, before revising migrations.
> Every claim below cites an actual file path in this repo at HEAD `5e6c7ef`.

---

## 1. Neon / AACapital table inventory (relevant to migration)

Evidence sources: `pipeline/conftest.py:28` (V2_DDL), `_scripts/tests/contract_schema.py`,
`pipeline/fill_v2.py`, `pipeline/capture_preopen.py`, `pipeline/rhp_writer.py`,
`app/api/**/route.ts`.

| Existing table | Producer | Consumer | Category |
|---|---|---|---|
| `ipo` | `pipeline/fill_ipo.py`, `pipeline/nse_lifecycle.py` | every step, snapshot | **A. ipo** |
| `ipo_issue` | `pipeline/fill_v2.py:66-70` | ipo-command route, snapshot | **B. fundamentals** |
| `subscription_snapshots` | `pipeline/fill_v2.py:83` (`nse_lifecycle.py`) | listing rules, snapshot | **B. fundamentals** (latest row → current KPIs) + **E. source_facts** (history) |
| `financial_statements` | `pipeline/rhp_writer.py`, `pipeline/sbi_ongoing.py` | valuation engine | **B. fundamentals** (latest per period-basis) |
| `valuation` | `pipeline/score_engine.py` | snapshot | **B. fundamentals** (fair value, MoS, score fields) |
| `decisions` | `pipeline/verdict_engine.py` | snapshot | **B. fundamentals** (current verdict pair) + **E. source_facts** (history) |
| `market_candles` (daily) | `pipeline/fill_v2.py:173` (`kite_fetch.py`) | journey route | **C. market_observations** interval=`1d` |
| `market_candles_15m` | `pipeline/fill_v2.py:204`, `pipeline/kite_fetch_15m.py` | `topout_online.py`, backtests | **C. market_observations** interval=`15m` |
| `listing_observations` | `pipeline/fill_v2.py:218`, `pipeline/capture_preopen.py:53`, `pipeline/topout_online.py:253` | listing rules, snapshot | **C. market_observations** observation_type in `preopen`, `open`, `tick`, `orderbook` |
| `listing_outcomes` | `pipeline/fill_v2.py:149`, `pipeline/topout_online.py` | snapshot | **B. fundamentals** (single derived row) — recomputable; if migration cost is trivial, keep in fundamentals; do NOT create a separate D1 table |
| `market_regimes` | `_scripts/market_regime.py` | market/snapshot | **B. fundamentals** at market-day level; if row cost matters, keep as JSON blob on the snapshot side — no separate D1 table needed |
| `documents` | `pipeline/rhp_link.py`, `pipeline/r2.py` | rhp_findings, ipo_rhp_intel | **D. research_findings** (document_sha column) — no separate documents table |
| `rhp_findings` | `pipeline/rhp_sonnet.py`, `pipeline/rhp_writer.py` | insights, snapshot | **D. research_findings** finding_type=`rhp` |
| `insights` | `pipeline/intelligence.py` | snapshot | **D. research_findings** finding_type=`insight` |
| `ipo_rhp_intel` | `pipeline/rhp_sonnet.py` | ipo-command route | **D. research_findings** finding_type=`rhp_summary` (or drop — is a derived cache) |
| `ipo_research_notes` | `pipeline/sbi_ongoing.py`, `_scripts/sbi_haiku_extract.py` | ipo-command, live-preopen | **D. research_findings** finding_type=`sbi_note` / `broker_note` |
| `source_facts` | every writer | audit, snapshot | **E. source_facts** (schema needs the fix in §11) |
| `platform_config` | pipeline & admin routes | admin routes, `pipeline/cron.py:162` | **F. DO NOT MIGRATE** — belongs in Cloudflare secrets/env, not a business table |
| `access_requests` | `app/api/access-note` | `app/api/admin/access` | **F. DO NOT MIGRATE to D1** — belongs in KV under `access:<email>` or in the auth control plane |
| `pipeline_steps`, `pipeline_failures` | `_scripts/run_ipo_pipeline_lean.py`, `pipeline/cron.py` | admin routes | **F. DO NOT MIGRATE** — pipeline observability. Emit to `pipeline-health:v1` KV snapshot instead |
| `ipo_tick_feed` | `_scripts/ipo/kite_ticker_ipo.py` | tick-feed, cum-volume routes | **C. market_observations** interval=`tick` if historical retention is required; otherwise KV live-only (`live:tick:*`) — **decision needs owner sign-off**. Currently the archival trickle is per-minute; low value if journeys never re-read it. |
| `rule_validation_results` | `pipeline/rule_validation.py` | admin routes | **F. DO NOT MIGRATE** — owner-approved feature-flag; keep in KV `rule-validation:v1` snapshot |
| `kite_session` | `app/api/auth/zerodha/callback`, `_scripts/refresh_kite_token.py` | admin, auth routes | **F. DO NOT MIGRATE** — Kite access_token is a **SECRET**. Keep in Cloudflare Worker secret store (`wrangler secret put`), not D1 |

Net effect: **5 D1 tables (ipo, fundamentals, market_observations, research_findings, source_facts)** replace ~24 Neon tables. 6 tables migrate to KV / secrets / snapshot payloads instead of D1.

---

## 2. Pre-open pipeline status

**Verdict: PARTIAL — writer works, sparse output is a bounded-target design choice.**

Evidence — `pipeline/capture_preopen.py:19-30`:

```sql
SELECT i.id, i.name_display, i.isin, UPPER(i.symbol), i.listing_date, ...
FROM ipo i LEFT JOIN (SELECT ipo_id, MAX(issue_size_cr) AS issue_size_cr
                     FROM ipo_issue GROUP BY ipo_id) issue ON issue.ipo_id=i.id
WHERE i.listing_date = <IST today> AND i.isin IS NOT NULL
  AND i.symbol IS NOT NULL AND i.is_mainboard = true
ORDER BY CASE WHEN COALESCE(issue.issue_size_cr,0) >= 150 THEN 0 ELSE 1 END, ...
LIMIT <limit + 1>
```

- **Producer**: `pipeline/capture_preopen.py` (writes `listing_observations` with `obs_type='preopen'`).
- **Schedule** (`.github/workflows/preopen-capture.yml`): `25-55/5 3 * * 1-5` + `0-35/5 4 * * 1-5` = **every 5 min from 08:55–10:05 IST Mon–Fri** (14 opportunities per listing day).
- **Idempotency**: `ON CONFLICT (ipo_id, obs_type, observed_at) DO NOTHING` with `observed_at = now.replace(second=0, microsecond=0)` — so ≤1 row per IPO per minute.
- **Target-selection rules** (four **AND**-joined filters explain the sparseness):
  1. `listing_date == IST today` — non-listing days produce 0 rows.
  2. `isin IS NOT NULL` — an IPO without ISIN in `ipo` is silently skipped.
  3. `symbol IS NOT NULL` — no Kite symbol → skipped.
  4. `is_mainboard = true` — SME IPOs are skipped by design.
  5. Sorted by `issue_size_cr >= 150 → highest first`, then bounded by `--limit N` (workflow default `5`).

**Why "sparse rows for recent listings"**: any listing missing ISIN or symbol in `ipo` at the moment of capture (identity-backfill lag) never enters the target set. That is the exact intended behaviour — the capture is **forward-only and evidence-gated**, not a scraper.

**Recommendation**: do **NOT** change the pre-open pipeline. If sparseness matters, tighten `pipeline/nse_identity_backfill.py`'s 08:50-IST run instead of touching the capture. Migration should preserve `listing_observations` semantics exactly and only re-shape at the D1 sink layer.

---

## 3. Market-data coverage today

Evidence — all `INSERT INTO`s that touch market data:

| Source table | Writer | Interval / type | Historical coverage available | D1 target |
|---|---|---|---|---|
| `market_candles` | `pipeline/fill_v2.py:173`, `pipeline/kite_fetch.py` | daily (`1d`) OHLCV + delivery_pct + traded_qty | yes; per-ticker post-listing | `market_observations` interval=`1d` |
| `market_candles_15m` | `pipeline/fill_v2.py:204`, `pipeline/kite_fetch_15m.py` | 15-minute OHLCV | yes; recent tickers | `market_observations` interval=`15m` |
| `listing_observations` obs_type=`preopen` | `pipeline/capture_preopen.py:53` | pre-open snapshot (ltp, buy_qty, sell_qty, payload) | yes; from live listing days | `market_observations` observation_type=`preopen`, interval=`preopen` |
| `listing_observations` other | `pipeline/fill_v2.py:218`, `pipeline/topout_online.py:253` | `open`, `tick`, `close_d1` | yes | `market_observations` matching observation_type |
| `ipo_tick_feed` | `_scripts/ipo/kite_ticker_ipo.py` | archival trickle from Kite ticker | yes; keyed by symbol | see §1: owner decision |

**5-minute candles: NO HISTORICAL SOURCE.** Grep of `pipeline/**`, `_scripts/**`, and the whole DDL history returns zero results for `market_candles_5m`, `_5m`, or any 5-minute interval. Do **NOT** create a D1 table for 5m data based on Stage-A assumptions; treat it as a future capture feature if ever added. The `market_observations.interval` column can accommodate `5m` when a producer arrives.

---

## 4. IPO Matrix 2026 raw archive — field/unit mapping plan (BEFORE ingestion)

The 60 IPO JSON files are **not in the repo** (`find . -iname 'ipomatrix*.json' -o -type d -iname '*ipomatrix*'` returns nothing at HEAD `5e6c7ef`). Existing code `pipeline/ipomatrix_fallback.py:26` also declares itself **RETIRED** (comment: "ipomatrix_raw dropped in the V1 sweep, nothing repopulates it").

**Action required from owner**: place the 60 JSON files under a repo path such as `_data/ipomatrix_2026/*.json` (raw, unchanged) so I can produce a JSON-path → verified-unit mapping. Until then, the plan is:

1. **Repo path** (proposed): `_data/ipomatrix_2026/` — files immutable, checked in.
2. **Mapper**: `_scripts/migrate/ipomatrix_map.py` (new; not authored yet) reads each JSON, records `{ipomatrix_id, seen_fields, sample_values}` to `_migrate/ipomatrix_field_survey.jsonl`.
3. **Human-verified unit table**: filled by the owner and me together, one line per JSON path. Format:

    | JSON path | Example value | Meaning | Raw unit | Verified normalization → D1 | D1 destination |
    |---|---|---|---|---|---|
    | e.g. `fresh_issue_amt_cr` | `112.00` | fresh issue size | **suffix says crore, but per Neon evidence sometimes rupees** — verify from 3+ IPOs before mapping | Decimal string, unit = ₹ crore | `fundamentals.fresh_cr` |
    | `price_band_lo` | `39` | band low | ₹/share | Decimal string | `fundamentals.band_lo` |
    | `subscription.qib_x` | `4.2` | QIB times | ratio | Decimal string | latest `subscription_snapshot` → `fundamentals.qib_x` |

4. **Ingestion gate**: no field is ingested until its row in that table is signed off. Ambiguous fields go to `source_facts` under a `pending_normalization=true` flag, NOT `fundamentals`.
5. IPO Matrix is a **one-shot bootstrap**, not a running scraper dependency (per your directive).

---

## 5. Sonnet document pipeline integration map

Preserved unchanged from existing `pipeline/rhp_sonnet.py` + `pipeline/rhp_writer.py` + `pipeline/sbi_ongoing.py`; only the destination changes.

| Sonnet product | Current Neon target | Proposed D1 target | Field on target |
|---|---|---|---|
| RHP forensic verdict (risk, related-party, auditor, litigation, use-of-proceeds, concentration) | `rhp_findings`, `ipo_rhp_intel.full_json` | `research_findings` | `finding_type='rhp'`, `severity`, `confidence`, `evidence_refs`, `document_sha`, `model_version` |
| RHP restated financials | `financial_statements` | **`fundamentals`** (as structured facts; NOT research_findings) | current period-basis fields |
| Anchor-doc names / allocations | *(deterministic parser preferred; Sonnet only classifies)* | `research_findings` finding_type=`anchor` | evidence-backed narrative + refs |
| SBI / broker note rating + valuation commentary | `ipo_research_notes.full_json` | `research_findings` finding_type=`sbi_note` / `broker_note` | rating, evidence_refs |
| Peer commentary | `ipo_research_notes.peers_json` | `research_findings` finding_type=`peer_comment` | evidence_refs to filing |

**Firewall**: Sonnet **must never write to `fundamentals` numeric fields directly**. The RHP financial-statement write is an exception because the RHP is itself the structured authoritative document; even then, `source='sebi_rhp'` and `confidence` must be recorded in `source_facts`. When evidence is absent, Sonnet returns `INSUFFICIENT_DATA` and no row is written.

---

## 6. Proposed final D1 schema (5 tables, matches your target)

**DDL delivered post-review, not now** (per your "return this report first" gate). Shape sketch only:

```sql
-- ipo: identity + lifecycle spine, matches current V2 identity doctrine.
CREATE TABLE ipo (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  isin TEXT UNIQUE, symbol TEXT,               -- symbol = routing metadata ONLY
  name_norm TEXT NOT NULL UNIQUE, name_display TEXT NOT NULL,
  sector TEXT, industry TEXT,
  is_mainboard INTEGER, status TEXT,
  listing_date TEXT,
  ipomatrix_id TEXT, bse_code TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- fundamentals: one authoritative row per IPO; latest structured facts + engine outputs.
CREATE TABLE fundamentals (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id) ON DELETE RESTRICT,
  -- Issue
  open_date TEXT, close_date TEXT, allotment_date TEXT,
  band_lo TEXT, band_hi TEXT, issue_price TEXT, face_value TEXT, lot_size INTEGER,
  issue_size_cr TEXT, fresh_cr TEXT, ofs_cr TEXT, market_cap_cr TEXT,
  -- Ownership
  promoter_holding_pre TEXT, promoter_holding_post TEXT, registrar TEXT, brlm_count INTEGER,
  allocation_qib_pct TEXT, allocation_nii_pct TEXT, allocation_retail_pct TEXT,
  -- Financials (latest FY)
  revenue TEXT, ebitda TEXT, pat TEXT, net_worth TEXT, total_debt TEXT, total_assets TEXT,
  eps_pre TEXT, eps_post TEXT, roe TEXT, roce TEXT, ronw TEXT,
  debt_equity TEXT, pat_margin TEXT, ebitda_margin TEXT,
  -- History for the two above blocks: minimal JSON array by period
  financial_history_json TEXT,
  -- Valuation
  ipo_pe TEXT, pe_pre TEXT, pe_post TEXT, pb TEXT, peer_median_pe TEXT,
  fair_value TEXT, margin_of_safety_pct TEXT, valuation_score TEXT, valuation_band TEXT,
  -- Subscription/anchor snapshot (latest final)
  qib_x TEXT, nii_x TEXT, bnii_x TEXT, snii_x TEXT, retail_x TEXT, total_x TEXT,
  anchor_amount_cr TEXT, anchor_count INTEGER,
  -- Verdicts (current)
  fundamental_verdict TEXT, listing_action TEXT,
  computed_at TEXT NOT NULL,
  CHECK ( NOT (fundamental_verdict='WEAK' AND listing_action LIKE 'BUY%') ),
  CHECK ( band_lo IS NULL OR band_hi IS NULL OR CAST(band_lo AS REAL) <= CAST(band_hi AS REAL) ),
  CHECK ( issue_price IS NULL OR band_lo IS NULL OR CAST(band_lo AS REAL) <= CAST(issue_price AS REAL) ),
  CHECK ( issue_price IS NULL OR band_hi IS NULL OR CAST(issue_price AS REAL) >= CAST(band_hi AS REAL)*0 + CAST(issue_price AS REAL) )
);

-- market_observations: unified time-series (candles + preopen + listing observations).
CREATE TABLE market_observations (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  observed_at TEXT NOT NULL,                   -- UTC ISO-8601 for intraday; date for daily
  interval TEXT NOT NULL,                      -- '1d' | '15m' | '5m'(future) | 'preopen' | 'tick'
  observation_type TEXT NOT NULL,              -- 'candle' | 'preopen' | 'open' | 'tick' | 'close_d1'
  o TEXT, h TEXT, l TEXT, c TEXT, v INTEGER,
  ltp TEXT, buy_qty INTEGER, sell_qty INTEGER, iep TEXT,
  source TEXT NOT NULL,                        -- 'kite' | 'nse' | 'bse'
  payload TEXT,                                -- optional JSON (depth, delivery_pct, ...)
  PRIMARY KEY (ipo_id, interval, observation_type, observed_at)
);
CREATE INDEX mo_ipo_time_idx ON market_observations(ipo_id, observed_at DESC);

-- research_findings: AI/document-derived intelligence, always evidence-backed.
CREATE TABLE research_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  finding_type TEXT NOT NULL,                  -- 'rhp' | 'sbi_note' | 'broker_note' | 'anchor' | 'insight' | 'risk_factor'
  source_type TEXT NOT NULL,                   -- 'sebi_rhp' | 'sbi' | 'anchor_doc' | 'derived'
  document_sha TEXT,                           -- R2 blob sha256
  finding TEXT NOT NULL,                       -- JSON body
  severity INTEGER,
  confidence TEXT,                             -- 0..1 decimal string
  evidence_refs TEXT,                          -- JSON [{page, quote}]
  model_version TEXT,
  created_at TEXT NOT NULL,
  CHECK ( confidence IS NULL OR (CAST(confidence AS REAL) >= 0.0 AND CAST(confidence AS REAL) <= 1.0) )
);
CREATE INDEX rf_ipo_type_idx ON research_findings(ipo_id, finding_type, created_at DESC);

-- source_facts: append-only provenance ledger with true idempotency.
CREATE TABLE source_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  field TEXT NOT NULL,                         -- e.g. 'fundamentals.issue_price'
  value TEXT,
  source TEXT NOT NULL,
  document_sha TEXT,
  confidence TEXT,
  pipeline_version TEXT,
  is_current INTEGER NOT NULL DEFAULT 1,
  observation_hash TEXT NOT NULL,              -- sha256(field||value||source||document_sha||pipeline_version)
  fetched_at TEXT NOT NULL,
  UNIQUE (ipo_id, field, observation_hash)     -- true idempotency, not timestamp-based
);
CREATE INDEX sf_ipo_field_idx ON source_facts(ipo_id, field, fetched_at DESC);
```

**Notes:**
- `market_observations.PRIMARY KEY (ipo_id, interval, observation_type, observed_at)` — one row per (IPO, interval, type, instant). Retries with the same tuple = 0 new rows.
- `source_facts.observation_hash` = sha256 of the tuple `(field, value, source, document_sha, pipeline_version)`. Two retries with the same value ⇒ same hash ⇒ 1 row. A genuinely different observation (new source, new value, new doc, or new pipeline version) ⇒ different hash ⇒ new row. **Fixes the timestamp-granularity idempotency defect** (previous PK was `(ipo_id, field, source, fetched_at)`).
- Verdicts, valuation, and derived KPIs live on `fundamentals` (current) + `source_facts` (history). Command Center, Fair Value, Company Quality, Trade Setup, Live Action are all derivable from the 5 tables.

---

## 7. Exact changes required to PR #342

Applied now in this commit:

1. ✅ Add `Status:` header at the top of `docs/architecture/D1_STAGE_A_CONSTRAINTS.md` (unblocks CI doc-lint).
2. ✅ Add `Status:` header at the top of `workers/ingest/README.md` (unblocks CI doc-lint).
3. ✅ Add this evidence report (`docs/architecture/D1_EVIDENCE_REPORT.md`).

Deferred to a follow-up commit on the same PR after your review approves the 5-table shape:

4. Delete `d1/migrations/0001..0004_*.sql` and replace with new `0001_ipo.sql`, `0002_fundamentals.sql`, `0003_market_observations.sql`, `0004_research_findings.sql`, `0005_source_facts.sql`.
5. Rewrite `workers/ingest/src/schemas.ts` for the 5-table shape (remove `subscription_snapshots`, `financial_statements`, `decisions`, `valuation` as separate tables — those fields land on `fundamentals` upsert or on `research_findings` where derived).
6. Rewrite `_scripts/migrate/neon_to_d1.py` mapping section: 24 Neon tables → 5 D1 targets. Remove any `DATABASE_URL` fallback (must be `NEON_READONLY_DATABASE_URL` only). Replace `LIMIT N OFFSET M` pagination with **keyset pagination** on the source PK for snapshot stability.
7. Remove `kite_session`, `platform_config`, `access_requests`, `pipeline_steps`, `pipeline_failures`, `rule_validation_results` from the migration entirely (§1 category F). Kite token is a **secret**, not a business fact.
8. Correct identity normalisation: reuse `pipeline/nse_identity_backfill.py`'s existing normalisation function verbatim instead of my re-implementation in `workers/ingest/src/identity.ts:normaliseName`.
9. Update `source_facts` writer in ingest Worker to compute `observation_hash` and INSERT with `ON CONFLICT (ipo_id, field, observation_hash) DO NOTHING`.

---

## 8. Migration / reconciliation plan (unchanged direction; retarget only)

- **Direction**: Neon (READ-ONLY) → staging D1 (write). No production cutover.
- **Order**: `ipo` → `fundamentals` (assembled from `ipo_issue` + latest `subscription_snapshots` + latest `financial_statements` + latest `valuation` + latest `decisions` + `listing_outcomes`) → `market_observations` (union of `market_candles` + `market_candles_15m` + `listing_observations`) → `research_findings` (union of `rhp_findings` + `insights` + `ipo_rhp_intel` + `ipo_research_notes`) → `source_facts`.
- **Reconciliation** per your requirements:
  - `market_observations`: `count(interval='1d') == Neon market_candles`, `count(interval='15m') == Neon market_candles_15m`, `count(observation_type='preopen') == Neon listing_observations WHERE obs_type='preopen'`.
  - `fundamentals`: 1 row per IPO in `ipo`; critical fields (`issue_price`, `band_lo/hi`, `issue_size_cr`, `fair_value`, `margin_of_safety_pct`, `fundamental_verdict`, `listing_action`) sample-diffed against latest Neon rows.
  - `research_findings`: total_count = sum(source counts); document_sha coverage.
  - `source_facts`: full row-count match; unique `observation_hash` count.

---

## 9. Risks / blockers

| # | Item | Impact | Action |
|---|---|---|---|
| R1 | IPO Matrix 2026 JSONs not in repo | Cannot produce field/unit map | Owner: place raw JSONs under `_data/ipomatrix_2026/` |
| R2 | 5-minute candle table proposal in an earlier draft was speculative | Would create a permanent empty table | Deleted from proposal — `market_observations.interval` can absorb 5m later |
| R3 | `kite_session.access_token` was in the Stage-A migration list | Would leak a live token into a business DB | Removed from migration; store in `wrangler secret` only |
| R4 | Pre-open sparseness misread as "broken" | Would trigger unneeded pipeline changes | Verified as intentional design (§2); no change |
| R5 | Timestamp-based `source_facts` idempotency | Two identical retries with different `fetched_at` created duplicate rows | Replace with `observation_hash` (§6) |
| R6 | `neon_to_d1.py` had `LIMIT/OFFSET` pagination | Not snapshot-stable under concurrent writes | Replace with keyset pagination on source PK (§7.6) |
| R7 | `neon_to_d1.py` accepts `DATABASE_URL` fallback | Could inadvertently connect to a writeable Neon DSN | Remove fallback; require `NEON_READONLY_DATABASE_URL` explicitly |
| R8 | Identity normalisation re-implemented in TS | Divergence risk vs Neon pipeline | Reuse existing Python normaliser via a shared spec or port character-for-character |

**Stopping here for review** per your directive. No schema DDL written in this commit; only the two Status headers + this evidence report.
