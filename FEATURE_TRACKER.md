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
- ✅ WINNER (v2 backtest, 357 IPOs): PROFIT-LOCK — avg 42%, win 57%, worst -18%, captures 27% of >20% runners. Beats target+20% (caps winners) AND hold-30 (-76% blowups).
- RULE: once +15% hit, never close below +5% floor (bank partial); else 18% trailing stop from peak.
- STATUS: RULE LOCKED. Bake into journey page decision engine.

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

## 🔧 INFRA / DATA HYGIENE
### 7. Pipeline timing — add pre-open (~08:00 IST) + post-close (~19:00 IST) runs for final subscription
### 8. "candles: full NSE universe" step fails (exit 1) + re-bloats price_candles — trim it
### 9. Name canonicalization — the recurring gremlin (Laser RHP mismatch, Kusumgar dupes). Canonical symbol↔name map.
### 10. Cloudflare migration — lay doc, execute fresh, Vercel stays live till proven
### 11. 21-table merge — fold ipo_intelligence→consolidated, resolve master/live/predictions overlap

## ✅ DONE (this stretch)
- IPO-only refactor (app/DB/pipeline/admin/cron) · PWA on phone · Kite token fix · score-circle verdict fallback · Laser RHP fuzzy-join · 3rd calculator (target ladder) · DB purge ~4M rows · delivery% + distribution signals wired · dupe-cleanup SQL (Kusumgar) · exit backtest v1

## ⚠️ DEPLOY DISCIPLINE
- Batch changes → FEW Vercel deploys (rate limit). Prefer 1 big PR over many small.
