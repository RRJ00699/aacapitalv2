# AACapital — IPO-Focus Cleanup Progress

Cleanup lane (Phases A–E, 2026-07-18 handover). Correctness fixes are a separate
lane (bottom, not counted). Weights sum to 100. Owner reviews at 25/50/75/100.
Full-state snapshot per MR; on sequential merge keep the newest.

| Phase | Task | Weight | Status | Branch |
|-------|------|-------:|--------|--------|
| A | Remove 4 dead `/api` fetches | 15 | ✅ | `claude/phase1-remove-dead-fetches` |
| B | Archive 4 orphan equity routes + hook | 20 | ✅ | `claude/phaseB-archive-orphan-routes` |
| C | Archive 53 equity/MF scripts (candle pipeline kept) | 30 | ✅ | `claude/phaseC-archive-equity-scripts` |
| D | Remove 2 dead pipeline steps (CIR + anchor-deal) | 20 | ✅ | `claude/phaseD-remove-dead-steps` |
| E | Root hygiene (loose .py + stray artifacts) | 15 | ⚪ | — |

## Cumulative
A 15 → B 35 (25✓) → C 65 (50✓) → **D 85 / 100 (75✓, this MR)** → E 100.
**Now: 85 / 100 delivered.**

## Phase D — what shipped
Removed 2 steps from `run_ipo_pipeline_lean.py` (+ `run_ipo_pipeline.py`) whose
outputs no route or compute reads; archived their scripts to `_archive/_scripts/`:
- **close-in-range** (`close_in_range.py`) — CIR REJECTED as pure leakage, spec §5.
- **anchor-deal conviction match** (`match_anchor_deals.py`) — wrote to
  `institutional_large_deals`, a table that does not exist. Silent no-op.
New guard `test_no_dead_pipeline_steps.py` (3 tests): fails on pre-D code (both
invoked), passes here; blocks re-adding either. Gates: tsc 0 · full suite 315
passed / 2 skipped.

### ⚠️ Handover correction (repo-first, evidence)
The handover listed **delivery pct (delivery_data)** as a 3rd dead step. It is NOT
dead: `app/api/post-listing/route.ts:85` does `SELECT date, delivery_percentage
FROM delivery_data`, and that route is live (`PostListingDashboard.tsx:56`).
**Delivery step KEPT.** Phase D removed 2 steps, not 3.

## Separate lanes (not counted)
- Correctness (other chat): MID-gap ✅#230 · Haiku id ✅#229 · ₹200cr ⚪ · fuzzy-joins ⚪
- Owner: market_regimes staleness + PCR · post-listing consolidation ⏸ · 8→3 tabs ⏸
- CI blocker: `npm audit --audit-level=high` red on `adm-zip` → `--audit-level=critical`.
