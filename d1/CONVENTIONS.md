# D1 Storage Conventions (AACapital, Stage A)

Status: **CURRENT** — the single rulebook for every D1 writer and reader.
Where any comment or ad-hoc code disagrees with this file, this file wins.

---

## 1. Precision & unit model (single source of truth)

**Canonical storage for every field that is `NUMERIC` in Neon is a `TEXT`
decimal string.** No paired `_paise`/`_bp` integer columns exist. There is
exactly one representation per value; divergence between representations is
structurally impossible.

Why: D1/SQLite has no native `DECIMAL`. `REAL` would silently corrupt IPO
prices. Storing a paired integer alongside the string would introduce a
second source of truth (and the AACapital codebase has already been bitten
by unit-scaling defects — see the 2026-07 handover). One representation. One
comparison rule.

| Meaning | Canonical storage | Display unit | Example row value |
|---|---|---|---|
| Per-share price (`ipo_issue.issue_price`, `band_lo`, `band_hi`, `face_value`) | `TEXT` decimal, ≤ 6 dp | ₹ per share | `"41.5000"` |
| Rupees-crore aggregate (`ipo_issue.fresh_cr`, `ofs_cr`, `issue_size_cr`, `subscription_snapshots.anchor_amount_cr`, `ipo_research_notes.*_cr`) | `TEXT` decimal, ≤ 6 dp | ₹ crore | `"143.8100"` |
| Subscription multiple (`subscription_snapshots.qib_x` etc.) | `TEXT` decimal | × (multiplier) | `"12.8000"` |
| Ratio / percent (`valuation.pe`, `roe`, `roce`, `de`, `ofs_pct`, `listing_outcomes.gap_pct`) | `TEXT` decimal | % or raw ratio (see column comment) | `"18.7000"` (%) or `"0.2200"` (D/E) |
| Confidence (`rhp_findings.confidence`, `source_facts.confidence`) | `TEXT` decimal, 0..1 | 0..1 fraction | `"0.87"` |
| Candle OHLC (`market_candles.o/h/l/c`, `market_candles_15m.*`) | `TEXT` decimal | ₹ | `"128.4500"` |
| Traded volume (`market_candles.v`, `market_candles_15m.v`, `traded_qty`, `day_volume`) | `INTEGER` | shares | `256413` |
| Booleans (`ipo.is_mainboard`, `subscription_snapshots.is_final`, `listing_outcomes.ceiling_20`) | `INTEGER` 0/1 | true/false | `1` |
| IPO date (`ipo.listing_date`, `ipo_issue.open_date`) | `TEXT` `YYYY-MM-DD` (IST) | day | `"2026-06-17"` |
| Instant (`*_at`, `*_ts`) | `TEXT` ISO-8601 UTC ending `Z` | UI renders IST | `"2026-06-17T03:30:00Z"` |
| Identity (`ipo.id`) | `INTEGER` surrogate (matches Neon `BIGINT`) | never shown | `4218` |
| Identity (`ipo.isin`) | `TEXT`, UNIQUE, may be NULL until discovered | display + lookup | `"INE0R2Q01034"` |

### Calculation rule

- **All arithmetic on rupees / ratios happens in application code**
  (Python `decimal.Decimal`, TypeScript `Number` or `BigInt` where
  precision matters). SQL never adds, multiplies, or averages canonical
  numeric fields.
- If SQL comparison IS required (only place today: `ipo_issue` CHECK
  constraints for `band_lo <= issue_price <= band_hi`), we `CAST(x AS REAL)`
  in the comparison expression only. The `TEXT` value on disk is untouched;
  the REAL is transient and never stored.
- **Reconciliation** (Stage B) compares the TEXT string after a normalising
  step (`Decimal(x).normalize()` on both sides) — no cast-to-float allowed.

### Sort order

If a future query needs `ORDER BY numeric_field DESC`, use
`ORDER BY CAST(numeric_field AS REAL) DESC`. This is legal — we only pay a
full-scan cost. If a hot query proves this slow, at *that* point we add a
computed generated column (`GENERATED ALWAYS AS (CAST(x AS REAL)) STORED`)
rather than a manually-maintained companion column.

---

## 2. Identity rules (LOCKED — product contract §6)

1. **ISIN exact match** — always wins.
2. **`name_norm` exact match** — fallback when ISIN is not yet known.
3. **Symbol (`ipo.symbol`) MUST NOT be used for identity.** Symbols are
   reused across delistings.

On resolution, the ingest layer returns the `INTEGER` `ipo.id` (surrogate
PK). Downstream tables reference `ipo_id INTEGER REFERENCES ipo(id)`.

Normalisation rule (`workers/ingest/src/identity.ts:normaliseName`): upper
case → strip punctuation → collapse whitespace → strip common legal
suffixes (`LIMITED`, `LTD`, `PRIVATE`, `PVT`, `INDIA`, `INDIA LTD`, `PVT LTD`, …).

**Duplicate identity rejection** is enforced by `ipo_name_norm_uidx` (unique
index on `ipo.name_norm`) and `UNIQUE` on `ipo.isin`.

---

## 3. Writer semantics

- **Raw facts fill-empty-only.** A scraper never overwrites a non-NULL cell.
  Enforced in the ingest Worker by `coalesceEmptyPatch` (see `db.ts`), and
  documented per-table in the writer registry (`schemas.ts`).
- **Engine outputs upsert.** `valuation`, `decisions`, `rhp_findings`,
  `listing_outcomes` may replace their own prior rows. `rhp_findings`
  additionally enforces `(doc_id, model, prompt_version)` UNIQUE (partial,
  matching Neon).
- **`source_facts` is append with idempotency.** PK
  `(ipo_id, field, source, fetched_at)` prevents retry duplicates: a re-run
  at the same instant is a no-op via `INSERT ... ON CONFLICT DO NOTHING`;
  a genuine new observation carries a new `fetched_at`.

---

## 4. Referential integrity (LOCKED — no CASCADE deletes)

**Every foreign key uses `ON DELETE RESTRICT`.** Rationale: an IPO row is
never a routine deletion target. Deletion is a manual, evidence-gated,
admin-only operation; cascading it into `market_candles`, `subscription_snapshots`,
`decisions`, or `source_facts` would silently destroy investment history.
Re-keying (TEMP → real ISIN) is done via `UPDATE`, not delete+insert.

### FK inventory (all `ON DELETE RESTRICT`)

| Child | Column | Parent |
|---|---|---|
| `ipo_issue` | `ipo_id` | `ipo.id` |
| `subscription_snapshots` | `ipo_id` | `ipo.id` |
| `financial_statements` | `ipo_id` | `ipo.id` |
| `documents` | `ipo_id` | `ipo.id` |
| `source_facts` | `ipo_id` | `ipo.id` |
| `market_candles` | `ipo_id` | `ipo.id` |
| `market_candles_15m` | `ipo_id` | `ipo.id` |
| `listing_observations` | `ipo_id` | `ipo.id` |
| `listing_outcomes` | `ipo_id` | `ipo.id` |
| `valuation` | `ipo_id` | `ipo.id` |
| `decisions` | `ipo_id` | `ipo.id` |
| `rhp_findings` | `ipo_id` | `ipo.id` |
| `insights` | `ipo_id` | `ipo.id` |
| `rule_validation_results` | `ipo_id` | `ipo.id` |

No table references `ipo` with CASCADE, SET NULL, or SET DEFAULT.

---

## 5. JSON blobs

Stored as `TEXT`; validated as JSON by the ingest Worker on write and
rejected on parse failure. Used for provenance / extractor payloads
(`rhp_findings.findings`, `documents`-less/on `ipo_rhp_intel.full_json`,
`ipo_research_notes.full_json`, `decisions.reasons`, `decisions.evidence_refs`,
`valuation.inputs_used`, `valuation.missing_inputs`, `listing_observations.payload`).
Never queried via `json_extract` in a hot path.

---

## 6. Never do

- Never store rupees as `REAL`.
- Never compare rupees with SQL `<`/`>` without `CAST(x AS REAL)`, and never
  outside a CHECK constraint or a rare admin query.
- Never use `symbol`/`nse_symbol`/`bse_code` as identity.
- Never overwrite a non-NULL raw fact via a scraper.
- Never `DELETE FROM ipo` or any V2 spine table without an explicit admin
  audit trail. Use `status = 'withdrawn'` (or similar upstream vocabulary)
  instead.
- Never allow the public Next.js Worker to bind `DB_CORE`. That invariant
  belongs to `lib/web-plane-db-contract.test.ts` and Stage D will extend it.
- Never let a build fall back to demo/fixture IPO data in production. See
  `docs/architecture/D1_STAGE_A_MOCK_FIREWALL.md`.
