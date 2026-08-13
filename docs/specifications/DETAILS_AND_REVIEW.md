Status: CURRENT (v1 shipped 2026-07-22 on feat/ux-premium)
Authority: docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-22

# COMPLETE DETAILS + LISTING REVIEW + STREET NEWS

## What shipped in v1
- **Complete Details view** (`/dashboard/ipo2?view=details&ipo=<SYM>`): the
  A–O skeleton rendering EVERY field the production payload already carries
  (identity/decision, timeline, issue structure, demand & anchors,
  financials & valuation, research evidence with quoted excerpts, street
  report). Missing fields render `— · pending (source)` — named, never
  invented. Deep-linkable; exact-symbol strong key (never fuzzy).
- **Street news module** (free tier, §F of the directive): `ipo_news` table
  (metadata + short RSS snippet ONLY — never article text, never paywall
  bypass); `_scripts/fetch_ipo_news.py` = whitelisted Google News RSS
  discovery (Reuters 1 > ET 2 > MC 3 > BS 4 > Mint 5; listing-context +
  exact-company + ±7d gates; GMP-only/sponsored rejected); pipeline step +
  admin job `news`; **manual override wins**: insert `source='manual'` and
  discovery never touches it. Surfaced: Details card, Command payload
  (`news` per card), Live hero one-liner.
- **Listing-review derivations** (`lib/listing-review.ts`, pure + executed
  tests): review states PRE-LISTING → WEEK COMPLETE; max-5 ranked
  observations with facts / impact / certainty (Confirmed vs Supported
  inference) / counter-evidence; PROHIBITED attribution regexes
  (test-pinned: "mutual funds sold", "FIIs dumped", "anchors exited",
  "operators", "retail panic" can never render).

## Field matrix (payload today vs directive)
| Section | Available now (source) | Missing (proposed source, next) |
|---|---|---|
| Header/identity | name, sym, state, open/close/listing dates, band, price, size (Chittorgarh/NSE) | lot size, ISIN, allotment date, exchange field (Chittorgarh/NSE scrape columns) |
| Issue structure | fresh/OFS cr + %, band (RHP/Chittorgarh) | shares counts, face value, holdings pre/post, dilution, objects, sellers (RHP tables extraction) |
| Timeline | open/close/listing | DRHP/RHP/anchor/allotment/refund/credit dates + anchor unlocks (NSE/Chittorgarh) |
| Anchors | anchor_count (NSE report) | amount, price, investor table, MF/FPI split, unlock dates (NSE anchor PDF parse) |
| Subscription | final QIB/NII/retail/total (NSE) | day-wise, bNII/sNII, applications (NSE archive scrape) |
| Basis of allotment | — | full section (NSE PDF; not yet captured) |
| Financials | EPS, ROE, D/E, CAGRs (IPOMatrix/RHP) | 3-year restated table, EBITDA, OCF (RHP financial-table extraction) |
| Valuation | P/E, peer median P/E, FV via lib/fair-value.ts | P/B, NAV, RoNW, margins |
| Peers | SBI note peer list (sbi_full) | dated peer table with per-column dates |
| GMP | day-before/max/min (InvestorGain) | full history table + chart (ipo_gmp_history additive table) |
| Registrar/BRLM | brlm_names | registrar contact + allotment link (Chittorgarh) |
| News | ipo_news (this release) | — |
| Listing review tape | journey candles (D0-D5 via /api/ipo/journey), listing fields | VWAP, delivery %, turnover (Kite/NSE bhavcopy — next) |

## THE ONE-TABLE DECISION (2026-07-22) — SUPERSEDED, do not implement
The "one golden serving table" plan below is RETIRED. It proposed making
`ipo_consolidated` (plus a durable `ipo_golden` and an `ipo_master` view) the
single serving object every route reads, backfilled by a `consolidate_master.py`
consolidation job. That architecture was never adopted as the serving spine and
its tables are now forbidden: `ipo_consolidated`, `ipo_golden`, and `ipo_master`
are in the `FORBIDDEN` set enforced by `tests/contracts/test_no_v1_tables.py`,
`consolidate_master.py` is absent from `_scripts/` (enforced by
`tests/contracts/test_repository_spine.py::test_consolidated_compatibility_is_not_called_by_production`),
and there is no `consolidate` admin job.

The real serving spine is the **V2 canonical facts + versioned KV snapshots**
described in `docs/architecture/CANONICAL_SPINE.md`: the pipeline publishes
immutable, versioned KV snapshots (`ipo-command:v6`, `ipo-details:isin:*:v1`,
`journey:isin:*:v1`) and the public consumers read those snapshots from KV — not
a golden/master serving table. Field precedence and enrichment live in the V2
`fill_v2`/intelligence path, not a nightly consolidation rebuild. This section is
kept only to record that the one-table decision was reversed; for the current
architecture read `CANONICAL_SPINE.md`.

## Next slices (in order)
1. Listing Review view UI (state machine + outcome summary + observations
   are DONE in lib; wire the view like Details, feed the week tape from the
   journey route).
2. NSE day-wise subscription + basis-of-allotment capture (new additive
   tables; ipo_consolidated stays derived).
3. RHP financial-table extraction (existing Sonnet output reuse first).

## Cost & legal
Zero new paid APIs; zero additional Anthropic calls (news scoring is
deterministic Python). Reuters linked + summarized, never scraped; no
paywall/anti-bot circumvention; snippets are RSS-provided and short.
