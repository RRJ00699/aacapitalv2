# AACapital — IPO-Focus Cleanup Progress

Ledger for the "IPO-only, no equity residue" cleanup lane (Phases A–E per the
2026-07-18 handover). Correctness fixes (MID-gap, Haiku id, ₹200cr, fuzzy-joins)
are a SEPARATE lane owned by the correctness chat — listed at the bottom, not
counted here. Weights sum to 100 = this cleanup lane. Owner reviews at 25/50/75/100.

Status: ✅ DELIVERED (gate-passed, pending merge) · 🔵 IN PROGRESS · ⚪ TODO · ⏸ HOLD.
(This file is a full-state snapshot per MR; on sequential merge just keep the newest.)

## Cleanup lane (my scope)

| Phase | Task | Weight | Status | Branch |
|-------|------|-------:|--------|--------|
| A | Remove 4 dead `/api` fetches (today-screen, cron-monitor) | 15 | ✅ | `claude/phase1-remove-dead-fetches` |
| B | Archive 4 orphan equity routes + orphaned hook | 20 | ✅ | `claude/phaseB-archive-orphan-routes` |
| C | Archive 53 equity/MF scripts (candle pipeline KEPT) | 30 | ✅ | `claude/phaseC-archive-equity-scripts` |
| D | Remove 3 dead pipeline steps (delivery/CIR/inst-deals) | 20 | ⚪ | — |
| E | Root hygiene (21 loose .py + stray artifacts) | 15 | ⚪ | — |

## Cumulative

| After | +w | Cumulative | Gate |
|-------|---:|-----------:|------|
| A | +15 | 15 / 100 | |
| B | +20 | 35 / 100 | crossed **25** |
| **C (this MR)** | +30 | **65 / 100** | crossed **50** |
| D | +20 | 85 / 100 | crosses **75** |
| E | +15 | 100 / 100 | **100** |

**Now: 65 / 100 delivered (A + B + C).**

## Phase C — what shipped (this MR)
Archived 53 equity/MF Python scripts to `_archive/_scripts/…` (path preserved;
`.py` under `_archive/` is inert — not compiled, not test-collected — so no rename
needed, one `git revert` away). Set computed deterministically: equity/MF by tables
touched, minus the wired set (lean pipeline / job_runner / prod / workflows / VM
cron / tests), minus the candle pipeline, minus anything imported by a kept script.
Verified: 0 tests reference them, 0 dangling refs in lean pipeline / job_runner /
workflows.
- **KEPT** (candle infra — feeds Journey + IPO backtests): `kite-sync-candles.py`,
  `reconcile_missing_candles.py`, `compute_candle_returns.py`, `sync_candles_to_neon.py`,
  and the candle backfill/purge/reconcile-universe scripts.
- Removed 3 now-dangling `package.json` npm-scripts (`ml:multibagger`,
  `commentary:ingest`, `commentary:archive`) whose targets were archived.
- Also fixed a junk filename (`_scripts/python check_cols.py` → `_archive/…/check_cols.py`).
Gates: tsc 0 · full pytest 312 passed / 2 skipped · package.json valid.

## Deferred to a follow-up (noted, not silently dropped)
- 4 equity `.ts` engines in `_scripts/engines/` (multibagger miner/screener/
  similarity/indicator) + the `similarity:multibagger` npm-script — `.ts`, distinct
  from this Python archive pass. Candidate for a "Phase C-tail" PR.

## Deviations from the handover (evidence-logged)
- Phase B: `api/market/live` was NOT 0-ref — `lib/hooks/useMarketData.ts:51,62`
  fetched it; that hook is itself orphaned, so both were archived.

## Separate lanes (not counted here)
- Correctness (other chat): MID-gap ✅ PR#230 · Haiku id ✅ PR#229 · ₹200cr ⚪ · fuzzy-joins ⚪
- Data/feed (owner): market_regimes staleness + missing PCR
- Decision (owner): post-listing route consolidation ⏸ · 8→3 tabs ⏸
- CI blocker (owner): `security` job `npm audit --audit-level=high` red on `adm-zip`
  (no upstream fix) → `--audit-level=critical` (agent tokens lack `workflow` scope).
