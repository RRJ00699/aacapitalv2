# AACapital — Database Schema & Hard Rules

**Authoritative reference for the IPO research DB (Neon Postgres).**
Last mapped: 2026-07-15. Do not break the rules below — they encode failures we
actually hit (duplicate rows, cross-matched symbols, null identity fields that
silently broke fair value across 166+ IPOs).

---

## 🔴 HARD RULES (never break these)

### RULE 1 — One row per company. Company identity is sacred.
- `ipo_intelligence.company_name` and `ipo_issue_details.company` must be UNIQUE
  per real company. NO variant rows (e.g. "Kusumgar Ltd.", "Kusumgar Ltd. O",
  "Kusumgar Ltd. CT" are the SAME company — only ONE row allowed).
- Any script that INSERTs a company MUST check for an existing row by
  NORMALIZED name first (strip suffixes, punctuation, " IPO", series codes
  like " O"/" CT") and UPDATE it instead of inserting a duplicate.

### RULE 2 — Never fuzzy-match a symbol/industry across different companies.
- Backfills/joins must use a STRONG key: exact ISIN (best), or exact normalized
  full name. NEVER a prefix/containment/similarity guess.
- Why: a fuzzy JOIN in a draft backfill produced FALSE matches (appeared to link
  CSM→MTAR, SRS→RKSWAMY). The underlying data was actually clean — the JOIN
  invented the collisions. A bad join looks exactly like data corruption.
  Strong-key only, and PREVIEW (RULE 4) to catch it.

### RULE 3 — Fill-empty-only for enrichment. Never overwrite good data.
- Enrichment scripts (peer_pe, sbi_notes, sector) use
  `SET col = COALESCE(col, %s)` — they fill NULLs, never clobber existing values.

### RULE 4 — Preview before every write. No blind UPDATE/DELETE.
- Every data-fix runs a SELECT preview first, eyeballed, THEN the write.
  (This rule just saved us from injecting MTAR's industry into CSM.)

### RULE 5 — ipo_intelligence is the READ source; keep its identity fields filled.
- The app + all compute read from ipo_consolidated (built from ipo_intelligence).
- If `sector` or `nse_symbol` is NULL on ipo_intelligence, peer P/E + fair value
  SILENTLY fail. These two fields are load-bearing — a sync step must keep them
  populated from ipo_issue_details (the scrape target) via a STRONG-key join.

### RULE 6 — Assistant never writes to the DB directly.
- Claude drafts SQL; the owner runs it from the PC after previewing.
- Claude reads the repo/schema to verify column names — never assumes them
  (we hit "column final_qib/company_name does not exist" from guessing).

---

## KEY TABLES (the ones that matter for the app)

### ipo_intelligence  — the master record (READ source, ~270 cols, 771 rows)
Identity: `company_name` (should be unique), `nse_symbol`, `isin`, `sector`
Financials: `eps_post`, `ipo_pe`, `peer_median_pe`, `roe`, `revenue_cagr_3y`,
  `debt_equity`, `ofs_pct`, `issue_price`, `issue_size_cr`
Subscription: `qib_subscription_x`, `qib_subscription`, `final_qib`(→consolidated)
⚠️ 166 rows missing nse_symbol; 98 have sector but null peer_median_pe.

### ipo_issue_details  — scraped issue facts (source of truth for financials)
Key: `company`, `nse_symbol`, `isin`, `industry` (NOT "sector"), `eps_post`,
  `pe_post`, `roe_pct`, `debt_equity`, `ofs_cr`, `issue_price`
⚠️ HAS duplicate + cross-matched rows (CSM×3, SRS×4) — needs dedup before use.

### ipo_consolidated  — built nightly, what the API/UI reads
Built by build_ipo_consolidated_v2.py from ipo_intelligence (+ issue_details,
subscription). Has `sector`, `industry`, `peer_median_pe`, `final_qib`, `eps_post`.
Never edit directly — it's regenerated; fix the SOURCE (ipo_intelligence).

### ipo_research_notes  — SBI research-note parse (source='SBI')
Cols: `company`, `nse_symbol`, `rating`, `peer_name`, `peer_ps`, `note_ps`.
⚠️ Stores peer_ps (P/S), NOT peer_pe. Peer P/E goes to ipo_intelligence directly,
  gated on nse_symbol match (fails when symbol is NULL).

### ipo_rhp_intel  — RHP forensic analysis (Claude-extracted)
Cols: `company_name`, `verdict`/`quality_gate`, `one_line`, `margin_of_safety`,
  `confidence`, `full_json` (trust_summary + top_3_material_risks + dd_note),
  `raw_text`. The app reads full_json for the "RHP details" panel.

### ipo_verdicts, ipo_tick_feed, ipo_level_analysis, ipo_accuracy_leaderboard
Verdict compute, live ticks, journey levels, street-vs-us accuracy. (Detail TBD
from schema_audit output.)

---

## PEER P/E DATA FLOW (the thing that kept breaking)

3 sources → ipo_intelligence.peer_median_pe (fill-empty-only):
1. parse_sbi_notes.py   — SBI note "Peer Comparison" table. Needs nse_symbol.
2. compute_peer_pe.py   — median of stock_fundamentals.industry peers (≥4).
                          Needs ipo_intelligence.sector to match an industry.
3. import_chittorgarh   — Chittorgarh peer data.
→ build_ipo_consolidated_v2.py copies peer_median_pe into ipo_consolidated.
→ API fairValue() uses it: fv = eps × peer_pe × quality × structure.

FAILURE MODE (root cause found 2026-07-15):
  NULL sector + NULL nse_symbol on ipo_intelligence → all 3 sources fail to
  match → peer_median_pe stays NULL → "fair value unavailable — needs peer P/E".
  The durable fix: a sync step that fills sector/nse_symbol from ipo_issue_details
  via a STRONG-key join (RULE 2), run before compute_peer_pe.

---

## PIPELINE ORDER (run_ipo_pipeline.py — the nightly)
scrape_chittorgarh → enrich → GMP → delivery → regime → candles →
listing-day OHLC → SBI notes → ipo_score → [MISSING: issue_details→intelligence
sync] → compute_peer_pe → quality_flags → build_ipo_consolidated_v2 →
verdicts → flags → RHP forensic → leaderboard → health-gate.

⚠️ GAP: no explicit step syncs sector/nse_symbol/eps_post from ipo_issue_details
into ipo_intelligence. This is why identity fields are NULL. ADD this step.

---

## TABLE INVENTORY (live row counts, 2026-07-15)

| Table | Rows | Role |
|---|---|---|
| delivery_data | 432k | NSE delivery % (backfill source) |
| price_candles | 21.7k | OHLC candles |
| ipo_daily_levels | 15k | journey levels |
| ipo_tick_feed | 9.6k | live ticks |
| market_regimes | 2.1k | daily regime/VIX |
| **ipo_intelligence** | **771** | **master record (READ source)** |
| ipo_flags | 770 | red-flag scanner |
| ipo_verdicts | 741 | TRADE/WATCH/CAUTION/AVOID |
| **ipo_consolidated** | **738** | **built nightly, API reads this** |
| ipo_rhp_intel | 455 | RHP forensic (full_json) |
| ipo_broker_consensus | 398 | street ratings |
| ipo_gmp | 343 | grey-market premium |
| ipo_research_notes | 244 | SBI note parse |
| ipo_issue_details | (stale stat: 0, actually populated) | scraped facts — sector/symbol/eps source |

## CONSTRAINTS — the gap that lets duplicates in

- `ipo_intelligence` PK = **`id`** (NOT company_name) → **duplicate company names
  are allowed**. This is why "Kusumgar Ltd. O/CT" variants and "Antony Waste"×2
  exist. FIX: add `UNIQUE INDEX on company_name` after dedup.
- `ipo_issue_details` PK = `isin` (one row per ISIN — good, but null-isin variants slip).
- `ipo_research_notes` PK = (source, company) — good.
- `ipo_consolidated` / `ipo_verdicts` / `ipo_flags` / `ipo_rhp_intel` keyed on
  company_name — good, but depend on ipo_intelligence being clean upstream.

## ACTUAL DATA STATE (corrected)

The data is MOSTLY CLEAN. Real issues are small + fixable:
1. 1 true dup: "Antony Waste" (2 rows).
2. Kusumgar variants (ids 1076, 1078 — the " O"/" CT" scraper artifacts).
3. No UNIQUE constraint on company_name → variants can regenerate.
4. Missing pipeline sync: ipo_issue_details (has clean sector/symbol/eps) →
   ipo_intelligence (where they're null). Add a STRONG-KEY (ISIN) sync step.
5. SBI Funds / Laser: no issue_details row yet (pre-listing) → peer P/E will
   populate when they list. Not a bug.
