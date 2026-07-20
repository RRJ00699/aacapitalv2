# AACAPITAL PRODUCT CONTRACT

Status: CURRENT — **AUTHORITATIVE**
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

Core thesis (owner, 2026-07-18, `IPO_BUSINESS_REQUIREMENTS.md §1`): allotment
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
  only; the <₹200cr floor is a LOCKED avoid — `IPO_BUSINESS_REQUIREMENTS.md`,
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
| **Gap bucket** (trade setup) | The validated edge: gap = (listing_open − issue_price)/issue_price | `_scripts/build_ipo_consolidated_v2.py:354-358` — LOW <4% · **MID 4–15%** · HIGH >15% | `gap_bucket` on cards, post table | **PRODUCTION** (backtests: `real_return_analysis.py`, `regime_mid_backtest.py`) |
| **ipo_score / score_band** | Pre-listing composite from validated factors | `_scripts/ipo_score.py` (pipeline "ipo score v0") | `score_band` chip | PRODUCTION |
| **Quality score** | Company quality (Laser-pattern flags) | `_scripts/compute_quality_score.py`, `compute_quality_flags.py`; spec `docs/QUALITY_SCORE_SPEC.md` | `quality_score`, `quality_conf` | PRODUCTION |
| **RHP verdict** | Sonnet forensic read of the RHP ($3/day cap) | `_scripts/rhp_sonnet.py` → `ipo_rhp_intel.full_json->verdict` | Command card RHP gate | PRODUCTION |
| **SBI note extract** | Broker-note rating/peers (Haiku, $0.50 cap) | `_scripts/sbi_haiku_extract.py` → `ipo_research_notes` | Command/Live SBI block | PRODUCTION |
| **Fair value** | 3-step model (PR #112) | `lib/fair-value.ts` (imported by live-preopen, ipo-command) | Command card | PRODUCTION |
| **GMP band** | Context only, never a gap substitute | `app/api/ipo-command/route.ts:246-254` | GMP hint text | PRODUCTION (context) |
| LQI "Strong Buy/Avoid" | superseded verdict | — | — | **DISABLED/REJECTED** (code comments: "disproven LQI", `app/dashboard/ipo/page.tsx:6`) |

Missing-data rule: absent inputs render as "—"/"pending", never as estimates
(`IPO_BUSINESS_REQUIREMENTS.md`; e.g. live-preopen rule details show
"band pending" / "size pending").

## 5. Approved data sources (production)

| Source | Data | Ingestion | Refresh | Cost | Failure behavior |
|---|---|---|---|---|---|
| Chittorgarh (cloud API) | IPO calendar, prices, sizes, BRLMs, ISIN | `_scripts/scrape_chittorgarh.py` (Playwright, backoff+UA rotation) | 2×/day pipeline | free | retries → zero-total = ntfy + step fail |
| NSE | discovery, bhavcopy delivery %, pre-open | `ipo/fetch_nse_ipos.py`, `fetch_delivery_bhavcopy.py`, `nse_preopen_capture.py` | pipeline / listing-day | free | skip + sink |
| SEBI | RHP PDFs | `_scripts/fetch_new_rhps.py` (direct-URL first, viewer fallback) | pipeline | free | all-failed = ntfy + exit 1 |
| SBI Securities | IPO note PDFs | `download_sbi_notes.py` → `parse_sbi_notes.py` | pipeline | free | skip + sink |
| investorgain | GMP | `scrape_investorgain_gmp.py` (4-attempt backoff) | pipeline | free | graceful skip + ntfy; GMP stales |
| IPOMatrix | enrichment (cookie) | `ipomatrix_ingest.py` | pipeline drip | free (cookie ~30d) | skip; cookie rotation via Settings |
| Zerodha Kite | candles, OHLC, live ticks, quotes, depth | `refresh_kite_token.py` (TOTP 08:00 IST) → ticker/candle scripts | daily token; ticks listing-day | Kite Connect subscription | token stale → Kite steps skip + ntfy URGENT |
| Anthropic API | RHP/SBI extraction | `rhp_sonnet.py` / `sbi_haiku_extract.py` | pipeline | **$3/day + $0.50/day caps** (`rhp_auto.py`) | cap-deferred queue, run log |

Storage: Neon Postgres (source `ipo_intelligence`, derived `ipo_consolidated`,
per `SCHEMA.md`). Serving: Cloudflare KV (`ipo-command:v1` + `:stale`,
`live:tick:*`, `journey:candles:*`, `cumvol:*`) — reads are KV-first; Neon
wakes for writes/warms (`docs/ASSET_LIGHT_ARCHITECTURE.md`, Phase-2 branch).

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
`docs/CURRENT_STATE.md §1`): **MID gap 4–15% → buy open, sell D1 close
(65% win / +3.3 median)**. Research signal, not a buy call.
**Journey exits** (`app/api/ipo/journey/route.ts:11-13`): ARM at +8% high →
floor +3% (lock the gain); TRAIL 12% off peak; candles floored at
`listing_date` (Phase-1 fix).
**Volume confirm**: 10:29–11:00 IST window; confirmed only with both bounds
AND window close (`cum-volume/route.ts`, Phase-2 fix).
**Evidence bars** (`docs/CURRENT_STATE.md §0`): backtest-before-build;
**n≥30 = SIGNAL** (below = indicative only); leakage checks required (CIR
lesson); executable prices only — never theoretical allotment returns.
**Data-write rules** (`SCHEMA.md`): strong-key joins (ISIN > exact normalized
name), never fuzzy; raw scraped facts fill-EMPTY-only (COALESCE); derived may
UPDATE; fix `ipo_intelligence` (source), never `ipo_consolidated`; QIB is the
only accepted demand proxy pre-open — GMP is context, not gap.

## 7. Rejected-factor register

Rejected / zero-weight factors must NOT silently return to production scoring.

| Factor | Status | Reason | Evidence | Reviewed |
|---|---|---|---|---|
| CIR (circular intensity) | PARKED (re-run at MID+STRONG n≥30; n=14) | d10_best_pct leakage — day-1 close inside its own outcome window | PR #49, `_scripts/cir_forward_test.py`; `docs/AACapital_Handover_v3.md` | 2026-07-08 |
| Market regime filter (red Nifty / VIX / 200EMA) | REJECTED as MID filter | No effect; MID edge is idiosyncratic (t≈0.2–0.5 ns) | PR #51, `_scripts/regime_mid_backtest.py` | 2026-07-08 |
| LQI verdict (Strong Buy/Avoid) | REJECTED | Disproven; superseded by gap_bucket edge | code comments `app/dashboard/ipo/page.tsx:4-6`, `IpoSignalCard` header | 2026-07 |
| Old gap bands (LOW <10 / MID 10–30 / HIGH >30) | REJECTED | Superseded by validated 4–15 MID | `real_return_analysis.py:46,142` asserts; audit 2026-07-20 (residue in `lib/ipoSignal.ts:36` pending cleanup) | 2026-07-20 |
| GMP as listing-gap proxy | REJECTED (context only) | QIB is the only accepted pre-open demand proxy | owner rule 2026-07-20; `ipo-command` gmp_hint wording | 2026-07-20 |
| Insider PIT feed | PARKED | NSE blocks datacenter IPs (empty 200s) | `docs/AACapital_Handover_v3.md` addendum 07-05 | 2026-07-05 |
| Allotment-return framing | REJECTED | Non-executable; product trades the market event | `IPO_BUSINESS_REQUIREMENTS.md §1` | 2026-07-18 |
| Equity/AMFI/commentary scoring | REJECTED (product non-goal) | IPO-only scope | §3; old README (archived) | 2026-07-20 |

## 8. Documentation authority & change process

- `docs/AACAPITAL_PRODUCT_CONTRACT.md` (this file) is **authoritative**.
- Supporting CURRENT docs: `IPO_BUSINESS_REQUIREMENTS.md` (rating detail),
  `docs/CURRENT_STATE.md` (session state), `SCHEMA.md`, `DATA_ARCHITECTURE.md`,
  `PIPELINE_SPEC.md`, `docs/ASSET_LIGHT_ARCHITECTURE.md`,
  `docs/QUALITY_SCORE_SPEC.md`, `docs/UI_REQUIREMENTS.md`,
  `docs/NSE_PREOPEN_CAPTURE.md`, `FEATURE_TRACKER.md`.
- `docs/archive/**` is historical only, never an implementation spec.
- Any product-rule change requires, in order: (1) evidence, (2) backtest or
  validation meeting the n≥30 bar, (3) update to this contract, (4) code
  change, (5) tests. PRs that change a locked rule without all five are
  rejected in review.
