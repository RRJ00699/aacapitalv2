# D1 Storage Conventions (AACapital, Stage A \u2014 5-table target)

Status: **CURRENT** \u2014 the single rulebook for every D1 writer and reader.
Where any comment or ad-hoc code disagrees with this file, this file wins.

---

## 0. The 5-table target

D1 stores exactly **five** tables. Every business fact lives in one of them.

| Table | Purpose | Writer semantics |
|---|---|---|
| `ipo` | Canonical identity + lifecycle spine | `coalesce_empty` on non-identity columns; identity fields (`isin`, `name_norm`) never overwritten |
| `fundamentals` | One authoritative row per IPO: latest structured facts, financials, valuation, verdict | `coalesce_empty` for raw scrapers; `upsert` for engine outputs |
| `market_observations` | Unified time-series (candles + pre-open + listing observations + tick, if retained) | `append` with `ON CONFLICT (ipo_id, interval, observation_type, observed_at) DO NOTHING` |
| `research_findings` | AI / document-derived intelligence (RHP, SBI notes, insights, risk factors, peer commentary) | `append` (with partial UNIQUE on `(document_sha, model, prompt_version)`) or `upsert` when reruns replace prior finding |
| `source_facts` | Append-only provenance ledger keyed by `observation_hash` | `INSERT ... ON CONFLICT (ipo_id, field, observation_hash) DO NOTHING` |

Neon tables that MUST NOT be migrated (secrets / observability / KV plane):
`kite_session`, `platform_config`, `access_requests`, `pipeline_steps`,
`pipeline_failures`, `rule_validation_results`.

---

## 1. Precision & unit model (single source of truth)

**Canonical storage for every field that is `NUMERIC` in Neon is a `TEXT`
decimal string.** No paired `_paise`/`_bp` integer columns exist. There is
exactly one representation per value; divergence between representations is
structurally impossible.

Why: D1/SQLite has no native `DECIMAL`. `REAL` would silently corrupt IPO
prices. Storing a paired integer alongside the string would introduce a
second source of truth. One representation. One comparison rule.

| Meaning | Canonical storage | Display unit | Example row value |
|---|---|---|---|
| Per-share price (`fundamentals.issue_price`, `band_lo`, `band_hi`, `face_value`, `fair_value`) | `TEXT` decimal, \u2264 6 dp | \u20b9 per share | `"41.5000"` |
| Rupees-crore aggregate (`fundamentals.issue_size_cr`, `fresh_cr`, `ofs_cr`, `anchor_amount_cr`, `market_cap_cr`) | `TEXT` decimal, \u2264 6 dp | \u20b9 crore | `"143.8100"` |
| Subscription multiple (`fundamentals.qib_x` etc.) | `TEXT` decimal | \u00d7 (multiplier) | `"12.8000"` |
| Ratio / percent (`fundamentals.roe`, `roce`, `debt_equity`, `gap_pct`, `margin_of_safety_pct`) | `TEXT` decimal | % or raw ratio | `"18.7000"` (%) or `"0.2200"` (D/E) |
| Confidence (`research_findings.confidence`, `source_facts.confidence`) | `TEXT` decimal, 0..1 | 0..1 fraction | `"0.87"` |
| Candle OHLC (`market_observations.o/h/l/c`, `ltp`, `iep`) | `TEXT` decimal | \u20b9 | `"128.4500"` |
| Volumes (`market_observations.v`, `traded_qty`, `buy_qty`, `sell_qty`) | `INTEGER` | shares | `256413` |
| Booleans (`ipo.is_mainboard`, `source_facts.is_current`) | `INTEGER` 0/1 | true/false | `1` |
| IPO date (`ipo.listing_date`, `fundamentals.open_date`) | `TEXT` `YYYY-MM-DD` (IST) | day | `"2026-06-17"` |
| Instant (`*_at`, `*_ts`, `market_observations.observed_at` when intraday) | `TEXT` ISO-8601 UTC ending `Z` | UI renders IST | `"2026-06-17T03:30:00Z"` |
| Identity surrogate (`ipo.id`) | `INTEGER` autoincrement | never shown | `4218` |
| Identity ISIN (`ipo.isin`) | `TEXT`, UNIQUE, may be NULL until discovered | display + lookup | `"INE0R2Q01034"` |

### Calculation rule

- **All arithmetic on rupees / ratios happens in application code**
  (Python `decimal.Decimal`, TypeScript `Number` where precision matters).
  SQL never adds, multiplies, or averages canonical numeric fields.
- If SQL comparison IS required (only place today: `fundamentals` CHECK
  constraints for `band_lo <= issue_price <= band_hi`, and
  `market_observations` non-negative guards), we `CAST(x AS REAL)` in the
  comparison expression only. The `TEXT` value on disk is untouched.
- **Reconciliation** (Stage C) compares the TEXT string after a normalising
  step (`Decimal(x).normalize()` on both sides) \u2014 no cast-to-float allowed.

### Sort order

If a future query needs `ORDER BY numeric_field DESC`, use
`ORDER BY CAST(numeric_field AS REAL) DESC`. This is legal \u2014 we only pay a
full-scan cost. If a hot query proves this slow, at *that* point we add a
computed generated column rather than a manually-maintained companion.

---

## 2. Identity rules (LOCKED \u2014 product contract \u00a76)

1. **ISIN exact match** \u2014 always wins.
2. **`name_norm` exact match** \u2014 fallback when ISIN is not yet known.
3. **Symbol (`ipo.symbol`) MUST NOT be used for identity.** Symbols are
   reused across delistings.

On resolution, the ingest layer returns the `INTEGER` `ipo.id` (surrogate
PK). Downstream tables reference `ipo_id INTEGER REFERENCES ipo(id) ON DELETE RESTRICT`.

**Normalisation rule (LOCKED)** \u2014 `workers/ingest/src/identity.ts:normaliseName`
is a character-for-character port of `pipeline/fill_ipo.py:_norm`:

1. lowercase the input
2. replace every char that is not `[a-z0-9 ]` with a space
3. collapse runs of whitespace to a single space and strip

Any drift between the Python and TypeScript implementations is a bug.
`tools/migrate/neon_to_d1.py:_norm_name` is the migration mirror of the
same function and is used to resolve `ipo_rhp_intel` / `ipo_research_notes`
into `ipo.id` during copy.

**Duplicate identity rejection** is enforced by `ipo_name_norm_uidx`
(unique index on `ipo.name_norm`) and `UNIQUE` on `ipo.isin`.

---

## 3. Writer semantics per table

| Table | Allowed modes | Rules |
|---|---|---|
| `ipo` | `coalesce_empty` | Identity fields (`isin`, `name_norm`) never overwritten. Enrichment fields (`symbol`, `sector`, `industry`, `kite_token`, `ipomatrix_id`, `bse_code`, `listing_date`, `status`) fill NULL only. |
| `fundamentals` | `coalesce_empty` (raw scrapers), `upsert` (engine outputs: valuation, verdict) | CHECK: `band_lo <= issue_price <= band_hi` (CAST to REAL, transient). CHECK: `WEAK` fundamental_verdict cannot pair with a `BUY%` listing_action. |
| `market_observations` | `append` | PK `(ipo_id, interval, observation_type, observed_at)`. Retries with the same tuple = 0 new rows. |
| `research_findings` | `append`, `upsert` | Partial UNIQUE on `(document_sha, model, prompt_version)`. `confidence` in `[0,1]`. `finding_type` whitelisted. |
| `source_facts` | append only via `ON CONFLICT (ipo_id, field, observation_hash) DO NOTHING` | `observation_hash = sha256(field \| value \| source \| document_sha \| pipeline_version)`. Retries with identical values converge to one row regardless of `fetched_at`. |

---

## 4. Referential integrity (LOCKED \u2014 no CASCADE deletes)

**Every foreign key uses `ON DELETE RESTRICT`.** An IPO row is never a
routine deletion target. Deletion is a manual, evidence-gated, admin-only
operation; cascading it would silently destroy investment history.
Re-keying (TEMP \u2192 real ISIN) is done via `UPDATE`, not delete+insert.

### FK inventory (all `ON DELETE RESTRICT`)

| Child | Column | Parent |
|---|---|---|
| `fundamentals` | `ipo_id` | `ipo.id` |
| `market_observations` | `ipo_id` | `ipo.id` |
| `research_findings` | `ipo_id` | `ipo.id` |
| `source_facts` | `ipo_id` | `ipo.id` |

No table references `ipo` with CASCADE, SET NULL, or SET DEFAULT.

---

## 5. JSON blobs

Stored as `TEXT`; validated as JSON by the ingest Worker on write and
rejected on parse failure. Used for provenance / extractor payloads
(`research_findings.finding`, `research_findings.evidence_refs`,
`market_observations.payload`, `fundamentals.financial_history_json`).
Never queried via `json_extract` in a hot path.

---

## 6. Never do

- Never store rupees as `REAL`.
- Never compare rupees with SQL `<`/`>` without `CAST(x AS REAL)`, and only
  inside a CHECK constraint or a rare admin query.
- Never use `symbol` / `nse_symbol` / `bse_code` as identity.
- Never overwrite a non-NULL raw fact via a scraper (`coalesce_empty`).
- Never `DELETE FROM ipo` or any V2 spine table without an explicit admin
  audit trail. Use `status = 'withdrawn'` (or similar upstream vocabulary)
  instead.
- Never allow the public Next.js Worker to bind `DB_CORE`. That invariant
  belongs to `lib/web-plane-db-contract.test.ts` and Stage D will extend it.
- Never let a build fall back to demo/fixture IPO data in production.
- Never store `kite_session.access_token` (or any secret) in D1. Secrets
  live in `wrangler secret put ... --env staging`.
- Never key `source_facts` idempotency on a timestamp alone \u2014 identical
  retries at different `fetched_at` values must NOT create duplicates.
