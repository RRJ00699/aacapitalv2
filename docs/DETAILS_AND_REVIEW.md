Status: CURRENT (v1 shipped 2026-07-22 on feat/ux-premium)
Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md
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

## THE ONE-TABLE DECISION (owner, 2026-07-22 — architecture, locked)
ipo_consolidated becomes the GOLDEN serving table: every field the UI shows
lives there as a column — including rhp_sonnet_json + sbi_haiku_json copies.
Source precedence per field: IPOMatrix (primary) -> NSE (fallback) ->
Chittorgarh detail page; fill-empty-only; one consolidation job backfills.
Other tables may live as raw sources but are NOT backfilled unless needed,
and routes stop join-hunting across them. Column set from the SBIFUNDS
golden reference: lot_size, face_value, isin, allotment_date, refund_date,
credit_date, anchor_amount_cr, anchor_lock30_date, anchor_lock90_date,
sub_day1_x, sub_day2_x, sub_day3_x, bnii_x, snii_x, total_applications,
employee_discount, employee_quota_shares, shareholder_quota_shares,
promoter_pre_pct, promoter_post_pct, mcap_cr, issue_expenses_cr,
registrar_name, registrar_phone, registrar_email, ronw, ebitda_margin,
price_to_book, gmp_history_json, financials_3y_json, rhp_sonnet_json,
sbi_haiku_json. IMPLEMENTED (this PR): schema_sync creates DURABLE ipo_golden + the VIEW
ipo_master (= consolidated LEFT JOIN golden) — one object for every read.
Why not columns on ipo_consolidated directly: that table is REBUILT every
pipeline run (build_ipo_consolidated_v2), and the wiped-listing-tape
incident test blocks exactly that hazard — the guard caught this design
before it shipped and would have wiped the owner's hand-backfilled data
nightly. consolidate_master.py (--apply; PC-runnable with Neon
DATABASE_URL) fills ipo_golden: intelligence scalars, RHP Sonnet + SBI
Haiku full_json copies, street article (sanity-guarded), and candles_json
(listing→lock-in daily OHLCV, grows daily, never shrinks). AUTOMATED: runs
every lean-pipeline cycle + admin job 'consolidate'. Remaining slices:
routes/UI read ipo_master; Chittorgarh detail-page scrape feeds the fields
intelligence lacks (lot size, timetable, day-wise subscription, expenses,
registrar, GMP history); NSE fallback per precedence.

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
