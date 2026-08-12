# AACAPITAL PRODUCT CONTRACT

Status: CURRENT
Authority: docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-21
Verified commit: efa45de — **AUTHORITATIVE**
Last updated: 2026-07-20 (repo audit session; Phases 1–4 branches)

This is the single authoritative product document. Where any other document,
comment, or memory disagrees with this file, this file wins. Supporting
documents explain implementation; archived documents are history only.

---

## 1. Product mission

AACapital is a **personal, IPO-only, evidence-first decision-support system**
for Indian mainboard IPOs, covering:

- **Pre-listing research** — evaluate the IPO before it lists
- **Listing-day execution** — an entry decision from executable market data
- **Post-listing monitoring** — track the position after listing
- **Disciplined exit management** — hold / reduce / exit by locked rules

Core thesis (owner, 2026-07-18, `docs/specifications/IPO_BUSINESS_REQUIREMENTS.md §1`): allotment
is a lottery; the edge is buying at the listing **open** on the right IPOs and
selling with discipline. Motto: **"research signal, not a buy call."** The app
informs; the owner trades manually.

## 2. Product flow (actual routes/components)

Three product areas, all served by `app/dashboard/ipo2/page.tsx` (views are
tab state) plus one standalone page:

| Area | View / route | Feed | Purpose |
|---|---|---|---|
| **Command** | `ipo2` view `command` | `/api/ipo-command` (KV-cached) | Pre-listing research: score band, SBI note, RHP verdict, GMP context, fair value |
| **Live** | `ipo2` view `live` | `/api/ipo/live-preopen`, `/api/ipo/tick-feed?live=1` (KV), `/api/ipo/cum-volume` | Listing-day house-rules decision + live tick panel (7-day window) |
| **Journey** | `/dashboard/journey` + `ipo2` HoldStrip | `/api/ipo/journey` (+ `/api/broker/quote` live price) | Post-listing hold/exit engine (lock-8 / trail-12) |
| Post audit | `ipo2` view `post` | `/api/ipo-command` `post` section | Band-vs-outcome accountability table |

Entry redirects: `/` and `/ipo` → `/dashboard/ipo2` (`app/page.tsx:3`,
`app/ipo/page.tsx:4`).

## 3. Non-goals (permanently out of scope)

- General equity screening; any "1500-stock" or "200-stock" dashboard
- Mutual-fund / AMFI scoring; management-commentary pipelines
- Generic technical-signal marketplaces; untested multi-signal mega-scores
- Unsupported AI stock recommendations; speculative commentary without evidence
- Portfolio/brokerage execution (the app never places orders)
- Fabricated fair values or presenting unavailable data as estimated fact
- SME IPOs and issues under ₹200cr as *tradeable* candidates (research display
  only; the <₹200cr floor is a LOCKED avoid — `docs/specifications/IPO_BUSINESS_REQUIREMENTS.md`,
  `app/api/ipo-command/route.ts:261`)

Old equity-era code (`lib/intelligence/*`, `lib/watchlist.ts`,
`lib/constants/stocks.ts`, `lib/providers/*`, archived tables
`technical_signals`, `company_master`, …) must not be revived. See the
2026-07-20 audit for the residue list; removal is tracked cleanup work.

## 4. Approved scoring systems

Company-quality analysis and trade-setup analysis are **separate by design** —
do not merge them into one number.

| Score | Purpose | Canonical implementation | Output / UI | Status |
|---|---|---|---|---|
| **Gap bucket** (trade setup) | The validated edge: gap = (listing_open − issue_price)/issue_price | `compatibility/consolidated/build_ipo_consolidated_v2.py:354-358` — LOW <4% · **MID 4–15%** · HIGH >15% | `gap_bucket` on cards, post table | **PRODUCTION** (backtests: `real_return_analysis.py`, `regime_mid_backtest.py`) |
| **ipo_score / score_band** | Pre-listing composite from validated factors | `_scripts/ipo_score.py` (pipeline "ipo score v0") | `score_band` chip | PRODUCTION |
| **Quality score** | Company quality (Laser-pattern flags) | `_scripts/compute_quality_score.py`, `compute_quality_flags.py`; spec `docs/specifications/QUALITY_SCORE_SPEC.md` | `quality_score`, `quality_conf` | PRODUCTION |
| **RHP verdict** | Sonnet forensic read of the RHP ($3/day cap) | `_scripts/rhp_sonnet.py` → `ipo_rhp_intel.full_json->verdict` | Command card RHP gate | PRODUCTION |
| **SBI note extract** | Broker-note rating/peers (Haiku, $0.50 cap) | `_scripts/sbi_haiku_extract.py` → `ipo_research_notes` | Command/Live SBI block | PRODUCTION |
| **Fair value** | 3-step model (PR #112) | `lib/fair-value.ts` (imported by live-preopen, ipo-command) | Command card | PRODUCTION |
| **GMP band** | Context only, never a gap substitute | `app/api/ipo-command/route.ts:246-254` | GMP hint text | PRODUCTION (context) |
| LQI "Strong Buy/Avoid" | superseded verdict | — | — | **DISABLED/REJECTED** (code comments: "disproven LQI", `app/dashboard/ipo/page.tsx:6`) |

Missing-data rule: absent inputs render as "—"/"pending", never as estimates
(`docs/specifications/IPO_BUSINESS_REQUIREMENTS.md`; e.g. live-preopen rule details show
"band pending" / "size pending").

## 5. Approved data sources (production)

| Source | Data | Ingestion | Refresh | Cost | Failure behavior |
|---|---|---|---|---|---|
| ~~Chittorgarh (cloud API)~~ *(RETIRED — quarantined, not run)* | formerly IPO calendar, prices, sizes, BRLMs, ISIN | `compatibility/scripts/scrape_chittorgarh.py` (quarantined; superseded by NSE discovery via `pipeline/nse_lifecycle.py`) | — | — | n/a — not run |
| NSE | discovery, bhavcopy delivery %, pre-open | `ipo/fetch_nse_ipos.py`, `fetch_delivery_bhavcopy.py`, `nse_preopen_capture.py` | pipeline / listing-day | free | skip + sink |
| SEBI | RHP PDFs | `_scripts/fetch_new_rhps.py` (direct-URL first, viewer fallback) | pipeline | free | all-failed = ntfy + exit 1 |
| SBI Securities | IPO note PDFs | `download_sbi_notes.py` → `parse_sbi_notes.py` | pipeline | free | skip + sink |
| investorgain | GMP | `scrape_investorgain_gmp.py` (4-attempt backoff) | pipeline | free | graceful skip + ntfy; GMP stales |
| IPOMatrix | enrichment (cookie) | `ipomatrix_ingest.py` | pipeline drip | free (cookie ~30d) | skip; cookie rotation via Settings |
| Zerodha Kite | candles, OHLC, live ticks, quotes, depth | `refresh_kite_token.py` (TOTP 08:00 IST) → ticker/candle scripts | daily token; ticks listing-day | Kite Connect subscription | token stale → Kite steps skip + ntfy URGENT |
| Anthropic API | RHP/SBI extraction | `rhp_sonnet.py` / `sbi_haiku_extract.py` | pipeline | **$3/day + $0.50/day caps** (`rhp_auto.py`) | cap-deferred queue, run log |

Storage: Neon Postgres (source `ipo_intelligence`, derived `ipo_consolidated`,
per `docs/archive/SCHEMA_V1.md`). Serving: Cloudflare KV (`ipo-command:v1` + `:stale`,
`live:tick:*`, `journey:candles:*`, `cumvol:*`) — reads are KV-first; Neon
wakes for writes/warms (`docs/architecture/ASSET_LIGHT_ARCHITECTURE.md`, Phase-2 branch).

## 6. Locked rules

Exact values from current code — changing any requires the §8 process.

**Hard filters (entry):** mainboard only; **avoid <₹200cr**
(`ipo-command/route.ts:261`, playbook `is_sme=false` filter).
**Listing-day house rules** (`app/api/ipo/live-preopen/route.ts` WIN table +
rules): mega issue >₹2000cr; 30+ anchors; band <₹300 + fresh (OFS <30%) —
82–90% win; The Stack (mega + open 0–50% + 30 anchors); House Stack
(30 anchors + ≥₹200cr + fresh, 72.7% win / +17.2% median); avoid: band >₹600,
open ≥ +50% (pop priced in, ~1-in-3.5 fades).
**Core trade** (LOCKED, `build_ipo_consolidated_v2.py:408`,
`docs/architecture/CURRENT_STATE.md §1`): **MID gap 4–15% → buy open, sell D1 close
(65% win / +3.3 median)**. Research signal, not a buy call.
**Journey exits** (`app/api/ipo/journey/route.ts:11-13`): ARM at +8% high →
floor +3% (lock the gain); TRAIL 12% off peak; candles floored at
`listing_date` (Phase-1 fix).
**Volume confirm**: 10:29–11:00 IST window; confirmed only with both bounds
AND window close (`cum-volume/route.ts`, Phase-2 fix).
**Evidence bars** (`docs/architecture/CURRENT_STATE.md §0`): backtest-before-build;
**n≥30 = SIGNAL** (below = indicative only); leakage checks required (CIR
lesson); executable prices only — never theoretical allotment returns.
**Data-write rules** (`docs/archive/SCHEMA_V1.md`): strong-key joins (ISIN > exact normalized
name), never fuzzy; raw scraped facts fill-EMPTY-only (COALESCE); derived may
UPDATE; fix `ipo_intelligence` (source), never `ipo_consolidated`; QIB is the
only accepted demand proxy pre-open — GMP is context, not gap.

## 7. Rejected-factor register

Rejected / zero-weight factors must NOT silently return to production scoring.

| Factor | Status | Reason | Evidence | Reviewed |
|---|---|---|---|---|
| CIR (circular intensity) | PARKED (re-run at MID+STRONG n≥30; n=14) | d10_best_pct leakage — day-1 close inside its own outcome window | PR #49, `_scripts/cir_forward_test.py`; `docs/AACapital_Handover_v3.md` | 2026-07-08 |
| Market regime filter (red Nifty / VIX / 200EMA) | REJECTED as MID filter | No effect; MID edge is idiosyncratic (t≈0.2–0.5 ns) | PR #51, `research/backtests/regime_mid_backtest.py` | 2026-07-08 |
| LQI verdict (Strong Buy/Avoid) | REJECTED | Disproven; superseded by gap_bucket edge | code comments `app/dashboard/ipo/page.tsx:4-6`, `IpoSignalCard` header | 2026-07 |
| Old gap bands (LOW <10 / MID 10–30 / HIGH >30) | REJECTED | Superseded by validated 4–15 MID | `real_return_analysis.py:46,142` asserts; audit 2026-07-20 (residue in `lib/ipoSignal.ts:36` pending cleanup) | 2026-07-20 |
| GMP as listing-gap proxy | REJECTED (context only) | QIB is the only accepted pre-open demand proxy | owner rule 2026-07-20; `ipo-command` gmp_hint wording | 2026-07-20 |
| Insider PIT feed | PARKED | NSE blocks datacenter IPs (empty 200s) | `docs/AACapital_Handover_v3.md` addendum 07-05 | 2026-07-05 |
| Allotment-return framing | REJECTED | Non-executable; product trades the market event | `docs/specifications/IPO_BUSINESS_REQUIREMENTS.md §1` | 2026-07-18 |
| Equity/AMFI/commentary scoring | REJECTED (product non-goal) | IPO-only scope | §3; old README (archived) | 2026-07-20 |

## 8. Documentation authority & change process

- `docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md` (this file) is **authoritative**.
- Supporting CURRENT docs: `docs/specifications/IPO_BUSINESS_REQUIREMENTS.md` (rating detail),
  `docs/architecture/CURRENT_STATE.md` (session state), `docs/archive/SCHEMA_V1.md`, `docs/architecture/DATA_ARCHITECTURE.md`,
  `docs/specifications/PIPELINE_SPEC.md`, `docs/architecture/ASSET_LIGHT_ARCHITECTURE.md`,
  `docs/specifications/QUALITY_SCORE_SPEC.md`, `docs/specifications/UI_REQUIREMENTS.md`,
  `docs/runbooks/NSE_PREOPEN_CAPTURE.md`, `docs/archive/FEATURE_TRACKER.md`.
- `docs/archive/**` is historical only, never an implementation spec.
- Any product-rule change requires, in order: (1) evidence, (2) backtest or
  validation meeting the n≥30 bar, (3) update to this contract, (4) code
  change, (5) tests. PRs that change a locked rule without all five are
  rejected in review.

## 9. Evidence, provenance & four-state gating (PR #265)

Every qualitative UI conclusion is traceable or it does not render.

**States** (never collapsed to null/false/empty): `CONFIRMED` (analysis done,
row + fingerprint written) · `PARTIAL` (artifact exists, analysis incomplete —
e.g. PDF downloaded, Sonnet not run; verdict without pdf fingerprint =
legacy/stale = PARTIAL) · `PENDING` (source not yet published) · `FAILED`
(parser/model/download crashed; carries `last_error` + `next_retry_at`).
`NOT_VERIFIED` exists only in audit/runtime reports, never as a production
IPO state.

**Provenance store**: `ipo_insights` (additive, `schema_sync.py`) — one row
per evidence-backed statement with category, direction
(positive|negative|neutral|incomplete), source_type (RHP·DRHP·SBI·NSE·SEBI·
Chittorgarh·Screener·Backtest·House Rule·Live Market Data), the source's own
`source_excerpt` (hard rule: **no excerpt, no row**), locator, models,
run id, `is_current` supersede-not-delete. Populated by fan-out from paid
Sonnet/Haiku JSON — zero new AI spend. Document identity = `pdf_sha256`;
a changed checksum invalidates prior insights (`is_current=false`) and
re-opens the stage.

**Stage truth**: `ipo_stage_state` (ipo_id, stage, status, attempt_count,
timestamps, last_error, next_retry_at, fingerprints, version). Writers:
fetch (RHP_DOWNLOADED), Sonnet store (SONNET_COMPLETE, input_fp=sha), Haiku
(SBI_EXTRACTED). FAILED carries a backoff that gates ONLY that IPO. Bounded
retries = 2×/day cron × the [-45d,+60d] eligibility window.

## 10. Three decision layers (never blended)

- **A · Company quality** — GOOD/WATCH/JUNK/INCOMPLETE from evidence
  (RHP forensics, governance, financial quality, SBI context). Incomplete
  required research ⇒ INCOMPLETE, never a defaulted GOOD.
- **B · Pre-listing trade setup** — the approved backtested score only
  (§4/§6); no untested factors.
- **C · Live listing-day decision** — BUY/WATCH/SKIP/INCOMPLETE at the
  executable price under house rules. Server attests `research_ready` +
  `research_missing[]` (live-preopen); the Live UI renders RESEARCH
  INCOMPLETE and demotes any go-signal to WATCH. A GOOD company can be a
  SKIP at a rich price; an attractive tape never upgrades JUNK/INCOMPLETE.

## 11. Fair-value & eligibility gating

Fair value computes only with real EPS **and** approved peer valuation; else
"Fair value unavailable — requires valid EPS and comparable peer valuation."
No EPS manufacture, no issue-price-as-fair-value, no MoS from an unavailable
fair value (the MoS rule reports unavailable, never a fake pass). Eligibility
(one rule, every feed): mainboard only, `COALESCE(is_sme,false)=false`,
confirmed size ≥ ₹200cr excluded when below, NULL size stays visible.
