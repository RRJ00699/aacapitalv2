# AACapital — IPO Business Requirements & Rating Spec (FINAL)

**Purpose:** the single authoritative record of how AACapital rates IPOs — what
we decided, why, from what data, and how every command-center parameter is judged.
Built from the actual transcript archive (2026-07-05 → 07-15) + live code, not memory.
Each major claim is traceable to a transcript or a code file. Read this before
changing any rating logic — if a change contradicts a LOCKED finding, stop.

Owner: Jammula Rakesh Reddy · US-CST · IPO listings IST.

---

## 1. THE CORE THESIS (what the whole system is for)

Allotment is a lottery, so the edge is NOT getting allotted — it's **buying at
listing OPEN on the right IPOs, then an informed, disciplined sell post-listing.**
The app makes INFORMED DECISIONS ONLY; the owner trades manually. Motto:
"research signal, not a buy call."

**WHY ALLOTMENT IS NOT THE GAME (owner, 2026-07-18):** apply to 50 IPOs and you
may get allotted 2-3, and even then the lot is tiny — an oversubscribed HNI
allotment lands you one lot, the same as sHNI. So **treat every IPO as a market
EVENT, and derive where buying AFTER listing returned real value.** Worked
examples where buy-at-open paid: Groww, Go Digit, Aadhar Housing, Bharti Hexacom,
NTPC Green, Canara Robeco, Ixigo.

**THE CRITICAL REFRAME (2026-07-10, data-rebuild):** every early backtest measured
issue-price → close — a return you CANNOT capture without allotment. The REAL,
tradeable outcome is **buy-at-listing-OPEN → exit by rule.** All rating/backtest
logic was re-derived against this executable outcome. Any metric derived against
`d10_best_pct` (a hindsight ceiling) is research-only, never a trade signal.

---

## 2. HOW WE RATE A COMPANY: JUNK vs GOOD

Two independent layers combine into the verdict:

### Layer A — The quantitative SCORE (predicts listing-open outcome)
`ipo_score.py` — "Score v0: evidence-weighted buy-at-open setup score." Every
weight traces to a factor_backtest SIGNAL (n≥30, era-consistent) on n=370,
baseline 72% / +5.9%, hold=10 sessions:

| Weight | Factor | Backtest evidence |
|---|---|---|
| **+2** | issue size > ₹2000cr | 81.8% win / +9.2 (n=77) — strongest single factor |
| **−2** | issue size ₹150–500cr | 58.9% / +1.5 (n=73); LOW×150-500 = 50% |
| **+2** | gap MID *(see §5 — now DEAD)* | 84.1% on polluted data; collapsed on clean |
| **−1** | gap HIGH | 64% (n=89), decayed to 50% in 2025+ |
| **+1** | peer-PE < 0.6× (cheap vs peers) | 76.7% / +7.6 (n=30) |
| **+1** | PE > 60 | 78.9% / +8.2 (n=38) |
| **−1** | PE 30–60 | 66.2% / +3.4 (n=136) |

Zero-weighted by evidence (≈baseline, don't add): OFS mix, GMP level, final QIB, ROE.
PENDING (insufficient data): anchors, regime, QIB-backloading, GMP-trajectory.

**Score bands — VERIFIED monotonic on clean data (this is the product):**
AVOID 60% → NEUTRAL 73% → FAVORABLE 79% → STRONG 81% (n = 93/145/92/43).
Higher band = higher win rate, cleanly. Unlike any single gap rule, the *combined
score* holds up. Acceptance test: bands must be monotonic or the model is rejected.
Writes: `ipo_score, score_band, score_expected_win, score_expected_med, score_evidence`.

### Layer B — The RHP forensic GATE (governance junk-detector — the moat)
Claude Sonnet 4.6 reads the actual RHP (prospectus) PDF and returns a governance
judgment — NOT a threshold formula, but expert reading. Stored in `ipo_rhp_intel`
(`rhp_sonnet_store.py`). Fields:
- `verdict`, `quality_gate`, `one_line`, `margin_of_safety`, `requires_further_dd`,
  `confidence`
- Boolean/text flags: auditor_qualified, sebi_action, criminal_litigation,
  litigation_watch_count, related_party_concern, ofs_heavy, customer_concentration_high,
  numbers_integrity_flag, cash_conversion_flag, debt_trend, working_capital_flag,
  contingent_liabilities_material, promoter_pledge_flag
- `full_json` (trust_summary + top_3_material_risks + aacapital_decision.dd_note),
  raw_text, model, cost_usd

**Why Sonnet, not local LLM (2026-07-12):** llama3.2:3b produced rampant false
positives (DMart flagged "wilful defaulter"; 124/131 records had false alarms from
a negation-inversion bug). Pivoted to premium Sonnet with a best-in-class forensic
prompt, section-gathering to keep tokens low, hard $20 cost cap. Validated:
SBI Funds (clean AMC → watch), Paytm/One97 (junk → reject).

**RHP = governance moat ONLY.** Financials come from Screener/SBI/Chittorgarh, NOT
the RHP. Dropped as "investor judgments not facts": moat, governance-score, execution.

### The JUNK philosophy (owner's, locked)
"We don't trade the 370 — we trade one cell." The score's AVOID grade + the RHP
gate + hard exclusions ARE the junk filter. Owner's hard exclusions:
- **Issue size < ₹200cr → RULED OUT** (SARSAR junk zone). Below this floor, don't touch.
- SME / tiny / weird-sector → excluded from tests and trades.
- Owner rules out junk by experience across the 2022+ universe; the system encodes it.

---

## 2C. THE OWNER'S FACTOR MODEL (full thesis, 2026-07-18)

The complete decision framework as stated by the owner. Items marked **[MODELED]**
are in `ipo_score` / the live engine today; **[GAP]** are agreed edges the code does
not yet compute. Do not delete a GAP row — it is a build queue, not a wish list.

### 1. Issue size AND price-band width
- Very large issues get a narrow band; sub-₹150cr also narrow. **Both end in ±5%
  moves — avoid.** The target is an IPO with a **10-20% band and real liquidity**.
- **[MODELED]** size >₹2000cr +2 · size ₹150-500cr −2 · junk floor <₹200cr ruled out.
- **[GAP]** band-width % as its own factor (currently only size is scored).

### 2. OFS vs Fresh issue — the classification matters more than the ratio
- 100% OFS is NOT automatically bad. Evaluate WHY:
  - **Growth** — Premier Energies, Waaree
  - **Niche** — Netweb
  - **Promoter quality** — NSDL, Bajaj Housing, HDB Financial, Brainbees, Ola
- Fresh issue: is it **expansion** (capacity doubling)? DEE Development, KRN Heat,
  Sai Life — these stated expansion in the RHP.
- **[MODELED]** ofs_pct thresholds (<20 / 20-60 / >60).
- **[GAP]** OFS *classification* (growth/niche/promoter) and *use-of-proceeds*
  extraction from the RHP. This is the difference between "100% OFS = bad" and
  "100% OFS by a quality promoter = fine".
- **[GAP]** track which IPOs hit **UC/LC on listing day** — a UC/LC hit raises the
  probability of the same next day.

### 3. Valuation AND who is bringing it
- **BRLM / registrar / book-runner reputation matters.** Notorious managers hype:
  Hyundai (parent at ~5 P/E, IPO at ~30), LG — same pattern.
- **[MODELED]** ipo_pe bands, peer_median_pe ratio, brlm_tier.
- **[GAP]** the **hype detector**: IPO P/E vs the *parent/sector* P/E, flagged when
  the multiple expansion is unjustified.

### 4. Anchors and promoter identity
- **>30 anchors = good money when buying at open.** Even an IPO that opens
  NEGATIVE can be supported by anchors + QIB (example: CMPDI opened ~-10% and
  still returned).
- **Promoter quality by identity**: LIC / ICICI / SBI-class holders do not sell —
  they hold long term. That changes the post-listing supply picture.
- **[MODELED]** anchor_count >30 (77%) / >50 (79%), quality_promoter flag.
- **[GAP]** promoter-identity tiering (institution-backed vs individual).

### 5. Fundamentals — a risk margin, not a predictor
- Pre-IPO fundamentals are hard to trust; use **peer comparison + ROE / P/E / P/B /
  EPS** as a *margin of risk*, not a forecast.
- **High valuation = lower probability of profit.** But cheap alone is not enough:
  BPCL-type cases listed ~90% above issue price, so buying at OPEN still lost
  5-15% on day one.
- **[MODELED]** FV = EPS × peer P/E × quality × structure; MoS vs the open.

### 6. GMP — track the arc, not the point
- Follow GMP **from announcement through to listing** (max and min), because
  **retail panics and sells when the IPO lists below GMP** — that panic is the
  opportunity.
- **[MODELED]** `gmp_day_before_pct` only (>20% = +50.9% avg, 100% win, n=14;
  the generic `gmp_percentage` is junk, r=-0.05).
- **[GAP]** GMP **trajectory** (max, min, slope over the window).

### 7. Listing-day mechanics
- Pre-listing open interest and selling in the IPO window is **heavily
  manipulated by institutions** — example: Urban Company, GMP >25%, buy-at-open
  gave +40%, then the stock tumbled to listing price within 3 days.
- **Decision must be made before 10:15**; NSE declares the price band at ~10:25.
- **[MODELED]** decision deadline **09:58 IST** (corrected after LASER; the old
  10:14 model was wrong), static rules 09:30, live rules firm to ~10:08.

### 8. VWAP
- VWAP against the live tape shows how price is being pushed.
- **[GAP]** VWAP-derived manipulation read is computed live but is not a factor in
  the decision score.

### 9. Per-IPO data points we want on EVERY IPO
`ipo_price` · `gmp_max` · `gmp_min` · `listing_price` · `listing_day_low` ·
`listing_day_high` · `UC/LC hit (y/n)`.
- **[GAP]** gmp_max / gmp_min / UC-LC flag are not captured today.

### 10. Market regime — the black-swan filter
- A good IPO listing on a bad day is a different trade. Track **market regime,
  global markets, PCR, and Nifty euphoria** — listing into euphoria vs into fear
  changes the buy-at-open odds.
- Counter-example that proves regime is not destiny: **Afcons (Shapoorji
  Pallonji)** — weak market, strong promoter, still worked.
- **[MODELED]** `market_regimes` (Nifty/VIX) exists.
- **[GAP]** **PCR is not captured**; regime data was found **STALE (latest
  2026-07-03)** on 2026-07-18 — a data bug, not a dead feature. **Regime is
  REQUIRED, not retired.**

---

## 3. DATA SOURCES — what each feeds (the "pull data per requirement" record)

| Source | Pulled how | Feeds |
|---|---|---|
| **Chittorgarh** | scraper (primary IPO feed) | issue details, subscription, GMP, peer table, broker consensus |
| **IPOMatrix** | private JWT API — inject session COOKIE to pull clean JSON (issue details → anchors, everything). Cracked 2026-07-13 | 24-field ingester filled 396 IPOs — anchors, price band, fresh %, structure. THE cleanest structured source. |
| **SBI research notes** | download + parse PDFs | peer comparison (peer_ps/PS, NOT PE), SBI rating |
| **RHP PDFs** | download + Claude Sonnet forensic | governance flags, verdict, quality_gate (the moat) |
| **Kite (Zerodha)** | API | live price, listing-day candles, journey/exit engine, trade journal |
| **NSE bhavcopy** | fetch | delivery % (delivery_data) |
| **Nifty/VIX** | market feed | regime (market_regimes) |
| **GMP (grey market)** | investorgain/chittorgarh | gmp_day_before_pct (the predictive one) |

### APPROVED SOURCES — owner-locked 2026-07-18 (nothing else enters the system)
**NSE · BSE · SEBI · Zerodha · IPOMatrix · Chittorgarh · Screener.**

**Commodity data = INGEST, never rebuild.** IPOMatrix + Chittorgarh cover ~99% of
issue details, anchors, subscription, GMP, peer P/E and financials — cleaner than
any bespoke scraper we can maintain, and every broker gives it free. Building our
own version of this is waste.

**The moat = the only thing worth BUILDING:**
1. **RHP governance forensics** (Sonnet on the prospectus) — auditor qualification,
   SEBI action, related-party, numbers integrity, concentration. No free source
   reads the prospectus.
2. **Backtested win rates by factor** — brokers publish ratings; we publish
   evidence ("30+ anchors = 77%, n=X, era-consistent").
3. **Exit discipline** (lock8/trail12) — nobody tells you when to sell.
4. **Owner's hard filters** — <₹200cr ruled out, SME excluded, band-width screen.

If a feature is not in that list, it should be a vendor paste, not a pipeline.

Each was built because a specific rating requirement needed it (e.g. anchors>30
needed IPOMatrix; governance needed the RHP; peer P/E needed SBI/Chittorgarh).

---

## 4. EVERY COMMAND-CENTER PARAMETER + ITS RATING RULE

### Score / Conviction
`score` = `(c.vscore ?? c.ipo_score)`, band AVOID→STRONG (see §2A). Shown as the
score dial + decision pill.

### Fair Value (app/api/ipo-command route, fairValue())
- eps = eps_post, else derived issue_price/ipo_pe (marked `*`)
- base = eps × peer_median_pe
- quality factor ±15%: ROE≥18 (+6%), revCAGR≥20 (+5%), D/E≤0.3 (+4%); clamp 0.85–1.15
- structure factor ±10%: OFS<20% (+6%), OFS>60% (−8%); clamp 0.90–1.10
- fair_value = base × quality × structure
- Margin of Safety = (fv/price − 1)×100; ≥+10 undervalued, ≤−10 rich, else fair
- Missing input → honest "unavailable — needs peer P/E / eps", never a fake number

### Verdict (TRADE / WATCH / CAUTION / AVOID)
Surfaced from ipo_verdicts + the RHP quality_gate. ⚠️ **GAP:** the exact threshold
rules that map score+flags→verdict are not in the current repo (the writer script
isn't present); verdicts exist in the table from prior runs. NEEDS RECOVERY or
re-specification — do not invent thresholds.

### RHP Trust (governance)
From ipo_rhp_intel: trust_summary, top_3_material_risks, dd_note, + the boolean
flags (§2B). Rendered as the RHP panel + trust verdict.

### House Rules pills (per-IPO factor badges)
Each proven factor shows as a pass/warn pill: size, fresh-issue, PE band, QIB,
price band, anchors. Split on `;`/`|`, deduped, max 3 + "+N more".

### Street vs AACapital vs RHP (3-verdict footer)
Broker consensus (issue-price ratings — quality signal only, NOT buy-open),
AACapital score verdict, RHP trust.

---

## 5. PROVEN EDGES (LOCKED) vs DEAD (rejected)

### LOCKED — real, leakage-free, era-consistent
- **Issue size > ₹2000cr = 82% win / +9.4 med** (n=78, all eras) — strongest factor
- **MEGA (>₹2000cr) + gap >15% = 92% win** — the mega exception
- **THE STACK (>30 anchors + mega + positive gap) = 84.6%**
- **Anchors > 30 = 77.4%** (FACTOR4, confirmed on IPOMatrix clean data)
- **Fresh-issue heavy (<30% OFS) = 82.4%**; OFS 100%-fresh 82%; HIGH+fresh 87%/+24.7
- **Low price band wins**; PE bands (PE<15, PE15-30) 72–84%; QIB 5–25x 77.6%
- **GMP day-before > 20% = +50.9% avg, 100% win (n=14)**, r=+0.74. NOTE:
  `gmp_percentage` (n=228) is junk r=−0.05 — only the DAY-BEFORE reading works.

### DEAD — confirmed rejected (do NOT resurrect without new evidence)
- **MID gap** — was the founding edge (65%), built on POLLUTED data (mismapped
  symbols); COLLAPSED to coin-flip (49% D1) on clean data. DEAD.
- **CIR (close-in-range)** — spectacular 100% was pure LEAKAGE (overlapped the
  outcome); leakage-free forward test → does NOT confirm. Rejected.
- **Anchor-quality** (n=38, unprovable), base-breakouts (n=18, folklore),
  momentum (flat most years), quality-flags@d10/d30.
- **SBI ratings** ≈ coin flip (Subscribe ≈ base rate). Kept for quality context only.

---

## 6. EXIT DISCIPLINE (post-listing "when to sell")

Progression of the research:
- Stop-loss backtest: **tighter stop = worse.** −3% stop → 36% win (shaken out of
  61% of trades before recovery — the Knack problem). No hard stop + trailing = best.
- Real-trade sim (buy open, +20 take / −5 stop / EOD, n=431): 37% hit +20%,
  60% hit −5%, 3% timeout.
- **FINAL LOCKED RULE — "lock8/trail12"** (app/api/ipo/journey, live engine):
  entry = listing open. ARM=0.08, FLOOR=0.03, TRAIL=0.12.
  Armed once high ≥ entry×1.08. EXIT if (armed AND live ≤ floor) OR (live ≤ trail).
  Polls /api/broker/quote every 60s, gated to IST market hours.
- Distribution/topping detector (volume-fade + peak-drawdown) surfaces "when to sell".

**MEASURED 2026-07-18 (backtest_journey_exits.py, n=297 listings 2021→now,
intraday-low fills, no same-bar look-ahead):**

| Strategy | median | p10 (downside) | p90 | win% |
|---|---|---|---|---|
| Sell at day 10 | +0.6% | −14.4% | +21.8% | 51.5% |
| Sell at day 30 | +9.3% | −43.1% | +137.9% | 57.9% |
| **lock8/trail12 (ours)** | **+3.0%** | **−25.9%** | **+69.5%** | **79.8%** |
| Hold 90 days | +9.6% | −43.3% | +140.3% | 59.3% |

**What this proves:** the rule is a **reliability product, not a return-maximiser**
— 4 wins in 5 versus ~52-59% for any naive alternative, and the typical trade is
green. Patient holding makes MORE money on average; our rule makes money MORE
OFTEN with a shallower tail. That is the trade we are choosing, deliberately.

**Honest limit — the copy must say this:** there is **no downside stop**. A
position that never reaches +8% never arms, so it rides to day 90 (the −25.9%
tail). Adding a hard stop was tested: −12% stop lifts the tail to −12% but
**collapses win rate 79.8% → 59.9% and p90 69.5% → 25.8%** — it cuts positions
that dip early and later run. Delaying the stop 2-5 bars recovered only ~3 points
of win rate. **Decision: keep the no-stop rule (consistent with the earlier
finding "tighter stop = worse", −3% stop → 36% win, the Knack problem) and make
the Journey copy state plainly that there is no downside exit — size accordingly.**

---

## 6B. LISTING-DAY LIVE DECISION ENGINE (pre-open buy-at-open scoring)

The live trading surface for listing day. Scores each listing IPO against the
Quick-Profit Playbook in real time, so the buy/skip call lands before the NSE
bid cutoff. Endpoint: `GET /api/ipo/live-preopen` → array of listing-window IPOs
(listing_date within -7 days .. +1 day), each scored independently so multiple
same-day listings are handled (15 such days in our history, some x3).

**Timeline (IST, NSE new-listing pre-open):**
- 09:30 — static rules resolve (known pre-listing, no live ticks)
- 09:30 → 10:15 — live rules firm as the open prints; re-evaluate every minute after 10:00
- ~10:08 — full rule-score + confidence should be settled
- 10:14 — decision deadline (2-min grace before NSE's ~10:16 bid cutoff; bid must be above discovery price or rejected)
- 10:25–10:28 — NSE declares price band
- 10:29–11:00 — cumulative volume (liquidity confirmation)

**Static rules (scored 09:30, two-card green/red-tick display):**
- 30+ anchors — `anchor_count >= 30` (77% win; 50+ = 79%, stronger). Shows count.
- Low band + fresh — `issue_price < 300` AND `ofs_pct < 30` (82–90% win).
- Mega issue — `issue_size_cr > 2000` (92% win when it also opens positive).

**Live rules (firm as the open prints):**
- Opening positive — open >= issue_price; euphoric `open >= +50%` = AVOID (pop priced in).
- The Stack — mega AND opening-positive AND 30+ anchors (85% win, near-zero floor — the cleanest setup).
- Margin of safety — see below.

**Margin of safety (MoS) — the buy-at-open quality check:**
Fair-anchor waterfall (best available first):
1. Modeled fair value (EPS × peer P/E × quality × structure) — when eps_post + peer P/E exist.
2. GMP-implied fair — `issue_price × (1 + gmp_day_before_pct/100)` — the market's pre-listing read. Used when modeled FV is unavailable, and the UI shows a side note flagging that it is GMP-derived, not modeled.
3. Issue-price floor — when no premium data at all.

`MoS% = (fair_anchor / listing_open − 1) × 100` · cushion₹ = fair_anchor − listing_open.
PASS if `MoS% >= +5%` AND RHP verdict is not "reject". Green when positive (margin exists), red when negative (paying above fair). GMP shown alongside as cross-check.
Worked examples: fair ₹150 / open ₹120 → +25% (₹30) green; fair ₹120 / open ₹130 → −7.7% (−₹10) red.

**AVOID flags (any true = red):** `issue_size_cr < 500`, `issue_price > 600`, `ofs_pct > 50`, `ipo_pe > 70`. The high-OFS + high-PE combo (`ofs_pct > 50` AND `ipo_pe > 70`) is a harder reject (backtested).

**RHP gate:** `rhp_verdict = reject` is a hard kill regardless of any signal (confidence → 0).

**Confidence:** win-rate-weighted blend of the passed rules (e.g. The Stack passing → ~85), penalised for AVOID flags. Ties confidence to backtested win rates, so "85% confidence" means "this setup won 85% in testing."

**Pre-open book lean (when broker depth is live):** Kite `/quote` depth → buy vs sell quantity → `book_lean_pct` (positive = buy-heavy = positive-listing lean). Degrades to null off-hours; the money-critical DB rules never depend on it.

**Thresholds (owner-confirmed, locked):** MoS pass ≥ +5% · PE-rich > 70 · OFS-heavy > 50% · mega > 2000cr · small < 500cr · euphoric ≥ +50% · deadline 10:14 IST.

**Known limit:** `eps_post` is currently null for upcoming IPOs, so modeled FV is null and MoS uses the GMP-implied anchor (labeled as such). Populating eps_post for true modeled FV is a separate, non-blocking backend workstream.

---

## 7. LOCKED vs OPEN

**LOCKED (never change without a new leakage-free backtest):**
- Buy-at-open outcome as the ground truth (not issue-price, not d10-best)
- The factor edges in §5 (size, mega+gap, anchors>30, fresh-issue, GMP day-before)
- Score bands must stay monotonic (acceptance test)
- lock8/trail12 exit
- RHP = governance moat only; financials from Screener/SBI/Chittorgarh
- Junk floor: issue size < ₹200cr ruled out

**OPEN / KNOWN GAPS:**
- ~~Verdict threshold rules missing~~ — **RECOVERED**: `compute_verdicts.py` runs
  in the pipeline (758 verdicts written 2026-07-17). `regime` deprecated by owner
  → always NULL; `confidence` maps high=90 / medium=65 / low=40.
- **Owner factor GAPS (§2C)**: band-width %, OFS classification, use-of-proceeds,
  BRLM hype detector, promoter-identity tier, GMP trajectory (max/min/slope),
  UC/LC listing-day flag, PCR. These are the build queue.
- **Decision deadline is 09:58 IST** (not the 10:14 recorded earlier in §6B —
  corrected after LASER).
- PENDING score factors: anchors, regime, QIB-backloading, GMP-trajectory (data thin)
- Listed-parent hypothesis (Tata Tech / Bajaj Housing quality proxy) — proposed,
  not yet fully tested last I have record.

---

## 9. PROCESS RULES (owner-set 2026-07-18 — non-negotiable)

**RULE 1 — Nothing ships to production without a test that proves the FEATURE
works, not merely that the code compiles.**
Proof of why: `sbi_haiku_extract.py` shipped, ran nightly, and processed **zero
rows for its entire life** — 244 SBI notes with PDFs sat untouched, $0.000 spent,
0 attempts logged. A test seeding one eligible row would have caught it on day one.

**RULE 2 — Every code change ships with a test case covering it.**

**RULE 3 (derived) — "Done" means the value renders on the screen.**
Not "endpoint built", not "columns exist", not "compute written". The recurring
bugs (cumulative-volume tile, quality-score dial) were each *correct code* declared
done at a layer nobody was looking at. Where a feature only shows data on listing
mornings, done means **a test that injects synthetic data and asserts the number
appears** — because you cannot verify a listing-day feature on a Tuesday.

**RULE 4 — Read this document before building.** The exit-stop question was
re-litigated on 2026-07-18 despite §6 already recording "tighter stop = worse".

---

## 10. MEASURED STATE (2026-07-18 — replace, do not append, when re-measured)

| Fact | Value | Implication |
|---|---|---|
| `ipo_intelligence` columns referenced in code | **230** | staging bloat; only **1 route** reads this table |
| App's real read contract | `ipo_consolidated` (7 routes), `ipo_research_notes` (6), `price_candles` (3), `ipo_verdicts` (2), `ipo_tick_feed` (2) | clean the staging layer freely; do not touch this contract |
| `price_candles` | 442 symbols / **442 are IPOs** / 23.5k rows | **no full-universe waste** — earlier assumption of 1500-symbol bloat was WRONG |
| SBI notes | 244 total / 244 with PDF / **0 extracted**; 34 match current IPOs | Haiku blocked by a **2-day date gate**; widen to the 30-day window |
| `market_regimes` | 2,106 rows, latest **2026-07-03** (stale) | regime is REQUIRED (see §2C.10) — this is a data bug to FIX |
| `delivery_data` | 439k rows, written daily, **no rating rule consumes it** | drop the pipeline step |
| `institutional_large_deals` | **table does not exist** | its pipeline step is a silent no-op — remove |
| `quality_score` | **590 / 759 rows scored** (78%), conf 53-62% | live; coverage capped by RHP `db_fields` availability |
| RHP extraction | content-SHA256 dedupe (GUARDRAIL G) | **no double-billing** — Caliber cost $0.103 once |
| Legacy 1500-stock tables | **12 tables, 113 file references** | archive to local; tables stay in DB untouched |

---

## 8. CROSS-CHECK NOTES (transparency — where this doc needs your eye)
- §2B RHP fields taken from the live ipo_rhp_intel schema (code) + 07-12 transcript;
  the exact final Sonnet PROMPT wording is in the 07-12 transcripts if you want it verbatim.
- §4 verdict thresholds: genuinely missing from current code — flagged as a gap, not guessed.
- IPOMatrix anchor numbers (§5) from the 07-13 journal summary; full detail in that transcript.
- If any factor % here differs from what you remember, the transcript line is the
  source of truth — tell me and I'll pull the exact quote.
