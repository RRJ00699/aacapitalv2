Status: CURRENT

# Pre-listing Quality Score (0–100) — SPEC v1 · 2026-07-16
**The mission metric**: "fundamentally strong, good promoters vs junk and
inflated numbers" — as a number, BEFORE listing, from data already in the DB.
Value/quality lens. ipo_score stays the trading lens. Disagreement = signal,
displayed, never merged.

## Factors (candidate weights — CALIBRATED BY BACKTEST BEFORE ANY UI USE)
| Block | Factor | Source (verified column) | Candidate pts |
|---|---|---|---|
| RHP forensics (40) | gate: clean/watch/reject | ipo_rhp_intel.full_json->db_fields->quality_gate | +20 / +8 / 0 |
| | criminal_litigation false | ...->criminal_litigation | +6 |
| | numbers_integrity ok | ...->numbers_integrity_flag | +5 |
| | related_party clean | ...->related_party_concern | +4 |
| | customer_concentration ok | ...->customer_concentration_high | +5 |
| Promoter (15) | quality_promoter true | ipo_intelligence.quality_promoter (compute_quality_flags) | +10 |
| | promoter_pledge low/none | promoter_pledge_pct | +5 |
| Structure (15) | OFS share | ofs_cr/(ofs_cr+fresh_issue_cr): <20% +10 · 20–60 +5 · >60 0 | |
| Valuation (10) | ipo_pe vs sector median | peer_median_pe ratio: <0.8 +10 · 0.8–1.2 +6 · >1.5 0 | |
| Fundamentals (12) | ROE≥18 +5 · CAGR≥20 +4 · D/E≤0.5 +3 | roe / revenue_cagr_3y / debt_equity | |
| External (8) | SBI "Subscribe" +5 · Tier-1 BRLM +3 | sbi_rating / brlm_names vs tier list | |
Missing factor = 0 pts + counted; **confidence = share of factor-weight with
data** (mirrors vconf). Bands: ≥75 STRONG · 55–74 SOLID · 35–54 MIXED · <35 WEAK.

## Discipline (locked-number class)
1. `backtest_quality_score.py` runs the candidate weights over ALL historical
   rows with outcomes (return_listing_open, d10_best_pct) → per-factor and
   per-band table (win rate, mean d10, n) — same evidence format as ipo_score
2. Rakesh reviews the table → weights adjust → weights LOCK
3. Only then: compute step joins lean + dial shows "Quality · pre-list"
   (hands to vscore at listing). NO UI wiring in this PR.
