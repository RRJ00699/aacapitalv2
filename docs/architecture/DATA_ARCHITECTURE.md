Status: CURRENT

# AACapital — Canonical Data Architecture

**The formal contract for which tables the backend reads, which sources feed
them, and which tables are frozen.** Goal: one clean source per field, no
guessed column names, no poison, no NSE/BSE symbol mismatches. One-time fix,
then stable.

Principle: we did not set out to run 30 tables. The system started with one
vision (an ML-ish foundation/prediction engine) and evolved into a focused IPO
data engine. This doc freezes the abandoned parts and formalizes the live core.

---

## 1. LIVE tables — backend reads these, cron feeds these
Every table below is read by at least one live API route (verified from route
source, not assumed). These are the ONLY tables cron may write to.

### Core IPO record
| Table | Read by | Fed by |
|---|---|---|
| `ipo_intelligence` | 6 routes (command, intelligence, listing-day, playbook, post-listing) | IPOMatrix ingest, Chittorgarh, Screener, SBI, sync steps |
| `ipo_consolidated` | 4 routes (command, levels, live-preopen, post-listing) | built nightly by `build_ipo_consolidated_v2.py` |
| `ipo_issue_details` | playbook | Chittorgarh scrape |

### Computed outputs (we generate these — not fetched)
| Table | Read by | Fed by |
|---|---|---|
| `ipo_verdicts` | command | `compute_verdicts.py` |
| `ipo_flags` | command | `compute_flags.py` |
| `ipo_rhp_intel` | command | Sonnet RHP forensic (`rhp_sonnet*`) |
| `ipo_pe` | command | peer-PE compute |

### Enrichment / context
| Table | Read by | Fed by |
|---|---|---|
| `ipo_research_notes` | command | SBI notes parse |
| `ipo_broker_consensus` | command | broker ratings (IPOMatrix / Chittorgarh) |
| `ipo_gmp` | ipo/gmp | ⚠️ legacy GMP; real GMP is `gmp_day_before_pct` on consolidated (InvestorGain). Candidate to retire the route — see §4. |

### Live / market data (time-series — IPOMatrix does NOT provide these)
| Table | Read by | Fed by |
|---|---|---|
| `price_candles` | 5 routes | Kite sync |
| `ipo_tick_feed` | command, tick-feed | Kite live ticker |
| `ipo_level_analysis` | command, levels, playbook | listing-day analysis |
| `ipo_daily_levels` | levels | `ipo_daily_levels.py` |
| `market_snapshot` | 4 routes | market snapshot job |
| `market_regimes` | market/snapshot | regime backfill |
| `delivery_data` | post-listing | NSE bhavcopy |
| `daily_institutional_flows` | market/global, snapshot | (missing table — FII/DII; separate fix) |

### Infra
`platform_config` (secrets/settings incl. IPOMatrix + Kite tokens), `kite_session`
(Zerodha auth), `stock_fundamentals` (Screener peer universe).

---

## 2. APPROVED SOURCES (the only feeds cron may use)
IPOMatrix · Chittorgarh · Screener · Zerodha (Kite) · NSE · BSE · SEBI · SBI Securities.

IPOMatrix + Chittorgarh together carry A-to-Z IPO data (broker ratings → GMP →
anchors → financials). IPOMatrix is the authoritative source for IPO identity,
anchors, PE, OFS, price band, QIB, and NSE/BSE symbols — so symbol mismatches and
guessed columns stop here. No other sources are introduced without updating this doc.

---

## 3. FROZEN tables — exist in DB, but NO reads, NO writes
These are the abandoned early-vision sub-system. They stay in the database
(no data loss, fully reversible), but: no backend route reads them, and no cron
job writes them. They receive no further updates.

| Frozen table | Why frozen |
|---|---|
| `ipo_master` | Hub of the abandoned foundation/prediction engine. Only reader was the `premarket-brief` cron route, which is not wired into the pipeline or job_runner (dead). |
| `ipo_predictions` | Output of the abandoned listing-probability engine. 0 live routes. |
| `ipo_feature_store` | Feature table for the abandoned decision engine. 0 live routes. |
| `ipo_similarity` | Abandoned similarity engine. 0 routes, 0 scripts. |

**Frozen scripts (no longer run, not in pipeline/job_runner):**
`import_ipo_foundation.py`, `ipo_decision_engine.py`, `ipo_similarity_engine.py`,
`ipo_listing_probability_engine.py`, `ipo_feature_store.py`, `ipo_run_quality_decision.py`,
`map_ipo_tables.py`.

---

## 4. THE CONTRACT (rules going forward)
1. **Cron feeds only §1 LIVE tables**, only from §2 APPROVED SOURCES.
2. **No backend route reads a §3 FROZEN table.** (The one offender —
   `cron/premarket-brief` reading `ipo_master` — is neutralized; that cron is dead anyway.)
3. **One owning source per field** (per docs/archive/SCHEMA_V1.md): IPOMatrix for identity/anchors/
   PE/OFS/band/symbols; Screener for EPS/peer P/E; InvestorGain for GMP; Kite for
   candles/ticks; NSE for delivery; SBI/RHP for forensic.
4. **Strong-key joins only** (ISIN > exact normalized name), **fill-empty-only**,
   **preview before write**, **assistant drafts SQL / owner runs** — all per docs/archive/SCHEMA_V1.md.
5. **UI reads the live core** (ipo_consolidated + the computed/enrichment tables),
   which is fed from IPOMatrix as the accurate source of truth.
6. Frozen tables are never dropped by this contract — they simply stop being touched.

---

## 5. Open item flagged (not decided here)
- `ipo_gmp` + its `ipo/gmp` route: the app's real GMP lives on `ipo_consolidated`
  (`gmp_day_before_pct`, InvestorGain). If the UI does not call `/api/ipo/gmp`,
  the route + table can move to FROZEN. Needs a UI-usage check before deciding —
  left LIVE for now to avoid breaking anything.
- `ipo_daily_levels` vs `ipo_level_analysis`: both "levels", both read by the levels
  route. Possible overlap to rationalize later — both LIVE for now.

## `ipo_subscription_history` — the ghost table (do NOT rebuild)

**Status: does not exist in Neon. This is fine. Do not create it or build an
Excel loader for it.** Verified 2026-07-16.

`build_ipo_consolidated_v2.py` LEFT JOINs `ipo_subscription_history` (alias `s`)
for 19 subscription columns. The table was never created, so those `s.*` refs heal
to NULL and the join is skipped — **the build does not crash** (see heal() +
`table_exists["s"]` gate). What actually happens to the columns:

- **The 4 verdict-critical numbers already work** — `final_qib`, `final_nii`,
  `final_retail`, `final_total` COALESCE to `ipo_intelligence` (`i.qib_subscription`
  etc.), which the **IPOMatrix scrape already populates** (`subscription.summary`:
  qib/nii/rii/total). So subscription data reaches the cards without this table.
- **9 columns stay NULL by design** — `final_qib_ex_anchor`, `final_anchor`,
  `final_bnii`, `final_snii`, `final_employee`, `nii/qib/retail_alloc_pct`,
  `structure_type`. **IPOMatrix's scrape does NOT contain these** (ex-anchor splits,
  bNII/sNII breakdown, allocation %). There is no current source, so they cannot be
  filled without a new scraper. They are secondary display fields, not used by the
  verdict engine.

**Why the "19 cols NULLed every build" flag was overstated:** 4 work via IPOMatrix,
6 more (dates/isin/amount) COALESCE from intelligence/issue_details, only the 9
above are genuinely NULL — and those have no data source anywhere today.

**Decision (Option A+):** leave the code as-is (touching working verdict-critical
paths carries more risk than the marginal secondary columns are worth), and record
this so the ghost table isn't chased again. `_scripts/ipo/load_subscription_history.py`
exists but needs `Issue_Subscription_*.xlsx` files that aren't sourced — it is NOT
wired into the lean pipeline and should stay that way unless a real subscription-
detail source (with bNII/sNII/alloc %) is added later.
