# AACapital — Feature Tracker (every ask, nothing buried)
_Last updated: 2026-07-14 · deploy-batched to avoid Vercel rate limit_

## 🎯 CONFIRMED FEATURES TO BUILD (all "must")

### 1. Listing-Day Decision Panel  [live Kite]
- Lists during price-discovery 9:00–10:15 IST; entry/exit call after listing 10:30
- Live Kite price → compute live gap → run EXISTING house rules (mega>2000cr, anchors>30, gap, fresh<30% OFS, band<300)
- Show which rules PASS live + the setup (stack/core/watch/avoid)
- Show LIST DATE
- STATUS: planned. Reuses playbook engine (ipo-command L185-229) + ipo/live route.

### 2. Fair Value Range  [your 3-step model]
- Base = EPS × median peer P/E
- × Quality factor ±15% (ROE, rev CAGR, D/E vs peers)
- × IPO-structure factor ±10% (fresh vs OFS, use of proceeds)
- Output: IPO price · fair value · margin of safety · undervalued/fair/rich
- DATA: buildable for ~400 IPOs (peer_median_pe 428, ipo_pe 392, cagr 427, roe 246, D/E 476, ofs_pct 316). Thin where peer data missing → show "insufficient data" honestly.
- SBI parser DOES extract peer_median_pe/peer_ps/peer_name (parse_sbi_notes.py L56-90). peer_median_pe=428 already good. Run parser over all 240 notes to fill more.
- STATUS: data confirmed + parser works, ready to build.

### 3. Dynamic Exit Strategy  [NO hard-code — backtested]
- Turtlemint proof: hard +20% caps winners (₹152→sold at +20% misses ₹145 exit after ₹147 peak)
- BACKTEST RESULT (357 IPOs): hold-to-30 avg100%/median20%/worst-76%; target+20% win76% but caps upside; trail-15% avg27%/worst-15% (lets winners run, caps loss)
- ✅ FINAL RULE (v3, tuned for TYPICAL ipo): LOCK8/TRAIL12 — avg 12%, median +2%, win 53%, worst -12%, guides on 92% of trades (silent only 8%).
- RULE: arm at +8% gain → protect +3% floor (sell if closes below after arming); else 12% trailing stop from peak. Sell whichever fires first.
- COVERAGE: 75% of IPOs reach +15%, 88% reach +5% (buying at listing OPEN captures the intraday spike). So the rule arms on most trades.
- WHY not the +15% version: it stayed SILENT on choppy IPOs (Turtlemint peaked +9%, never armed). The +8% arm fixes that — guides the typical IPO.
- STATUS: RULE LOCKED (lock8/trail12). Bake into journey page.

### 4. IPO Journey Page (listing → first anchor lock-in, ~30d)  [dedicated page]
- Design: price-story chart (entry/VWAP/peak/low/now) + decision (hold/trim/exit + why) + lock-in timeline ribbon
- Includes SECOND-DAY view (day 2, 3... progression) — was missing
- Uses the 6 engines as annotations + the backtested exit rule
- ROLE: owns STAGE 3 (the HOLD) — your hardest, most emotional decision ("when do I sell?"). Shows profit-lock signal daily so you don't sell at the bottom (Turtlemint ₹130) or hold past distribution. This is the app's discipline motto made real.
- STATUS: designed + role justified + exit rule LOCKED (profit-lock). Ready to build.

### 5. SBI + Hem Sonnet combined verdict  [test worth first]
- Run cheap test: Sonnet reads both broker PDFs → combined good/junk verdict. Prove value before full build.
- STATUS: pending test.

## 🎨 DESIGN
### 6. Full-app theme — Midnight Teal (night) + Slate Blue (day), auto day/night switch
- Whole app, every screen, cohesive. Fix: readability (contrast, near-black text, whitespace)
- STATUS: palette locked, build as ONE big careful pass.

## 🔬 NEW RESEARCH (from Rakesh's insights)
### 12. Negative-listing pattern study
- Turtlemint listed -10% → that's WHY it popped after (weak hands shaken out, bounce)
- Negative listings = different playbook (buy the bounce, not panic)
- Testing: do neg-listers share traits (P/E, OFS%, GMP)? Can GMP predict a negative listing?
- If predictable → real edge: know to expect dip-then-pop pre-listing
- ✅ RESULT: NEG-listers are OFS-HEAVY (27% vs 3% for pos-listers!) + higher P/E (80 vs 68) + bigger. GMP does NOT predict it (34% both, GMP>10 still lists neg 30%).
- USABLE RULE: high OFS% + high P/E → expect weak/negative listing → dip-then-pop setup (Turtlemint). Surface on card as a listing-day expectation flag.
- STATUS: pattern found. Add "likely weak open" flag to card + note the bounce setup.

### 13. Real-time exit architecture (DECIDED)
- MODE A (daily, from stored candles): journey page hold decision. NO new infra. 95% of value.
- MODE B (live Kite/OBIR): listing-day page only, intraday. Reuses existing OBIR/tape code.
- lock8/trail12 needs: entry (stored at listing) + peak (high) + current price.
- FREQUENCY (Rakesh): for IPOs, 2h or 4h candles better than daily — catches intraday moves during the volatile early hold without needing live tick. Check if Kite sync can pull intraday candles for IPO symbols.

## 🔧 INFRA / DATA HYGIENE
### 7. Pipeline timing — add pre-open (~08:00 IST) + post-close (~19:00 IST) runs for final subscription
### 8. "candles: full NSE universe" step fails (exit 1) + re-bloats price_candles — trim it
### 9. Name canonicalization — the recurring gremlin (Laser RHP mismatch, Kusumgar dupes). Canonical symbol↔name map.
### 10. Cloudflare migration — lay doc, execute fresh, Vercel stays live till proven
### 11. 21-table merge — fold ipo_intelligence→consolidated, resolve master/live/predictions overlap

## 🔴 LIVE EXIT — architecture (Rakesh's insight, DECIDED)
- Floor/trail LEVELS = fixed numbers from stored candles (entry + peak). Live price = one Kite quote.
- Compare live price ≤ floor OR ≤ peak×0.88 → EXIT signal fires INTRADAY (11 AM, not EOD close).
- Why: waiting for close bleeds ₹193→₹185. Live trigger exits at the break.
- Infra EXISTS: /api/broker/quote (Zerodha→Yahoo fallback), /api/ipo/tape (OBIR), lib/ipo/tape.ts.
- Journey page: fetch live quote on open + 60s auto-refresh while watching. No streaming/storage.
- ✅ candle storage CLEAN: 21,750 rows / 432 IPO symbols (purge held, no re-bloat).

## ✅ DONE (this stretch)
- PR #112 fair value + weak-open flag (MERGED)
- IPO-only refactor (app/DB/pipeline/admin/cron) · PWA on phone · Kite token fix · score-circle verdict fallback · Laser RHP fuzzy-join · 3rd calculator (target ladder) · DB purge ~4M rows · delivery% + distribution signals wired · dupe-cleanup SQL (Kusumgar) · exit backtest v1

## ⚠️ DEPLOY DISCIPLINE
- Batch changes → FEW Vercel deploys (rate limit). Prefer 1 big PR over many small.
