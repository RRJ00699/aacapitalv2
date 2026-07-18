# AACapital — IPO-Focus Cleanup Progress

Ledger for the "IPO-only, no equity residue" cleanup lane (Phases A–E per the
2026-07-18 handover). Correctness fixes (MID-gap, Haiku id, ₹200cr, fuzzy-joins)
are a SEPARATE lane owned by the correctness chat — tracked at the bottom, not
counted here. Weights sum to 100 = this cleanup lane. Owner reviews at 25/50/75/100.

Status: ✅ DELIVERED (gate-passed, pending merge) · 🔵 IN PROGRESS · ⚪ TODO · ⏸ HOLD.

## Cleanup lane (my scope)

| Phase | Task | Weight | Status | Branch |
|-------|------|-------:|--------|--------|
| A | Remove 4 dead `/api` fetches (today-screen, cron-monitor) | 15 | ✅ | `claude/phase1-remove-dead-fetches` |
| B | Archive 4 orphan equity routes + orphaned hook | 20 | ✅ | `claude/phaseB-archive-orphan-routes` |
| C | Archive ~52 equity/MF scripts (candle pipeline KEPT) | 30 | ⚪ | — |
| D | Remove 3 dead pipeline steps (delivery/CIR/inst-deals) | 20 | ⚪ | — |
| E | Root hygiene (21 loose .py + stray artifacts) | 15 | ⚪ | — |

## Cumulative

| After | +w | Cumulative | Gate |
|-------|---:|-----------:|------|
| A | +15 | 15 / 100 | |
| **B (this MR)** | +20 | **35 / 100** | ← crosses your **25** review gate |
| C | +30 | 65 / 100 | ← crosses **50** |
| D | +20 | 85 / 100 | ← crosses **75** |
| E | +15 | 100 / 100 | ← **100** |

**Now: 35 / 100 delivered (A + B).**

## Phase B — what shipped (this MR)
Archived to `_archive/` (`.ts.txt`, repo convention, one `git revert` away):
`api/search`, `api/market/live`, `api/broker/holdings`, `api/broker/positions`,
and the orphaned `lib/hooks/useMarketData.ts` (its only fetch was the archived
market/live). KEPT per handover: `api/market/global`, `api/market/snapshot`,
`api/broker/quote`, `api/broker/status`, and **`api/market-regime`** (required
data input, spec §2C.10 — staleness is a separate feed fix, F1 below).
Pruned the now-dangling `search` + `market/live` entries from
`test_all_routes_contract.KNOWN_GAPS` and `test_route_runtime.HOT_ROUTES`.
Gates: tsc 0 · full pytest 312 passed / 2 skipped.

## Deviations from the handover (evidence-logged)
- Handover said the 4 routes have "0 UI references"; `api/market/live` was in
  fact fetched by `lib/hooks/useMarketData.ts:51,62`. Verified that hook is
  itself orphaned (imported nowhere) → archived both. No live screen affected.

## Separate lanes (not counted here)
- Correctness (other chat): MID-gap ✅ PR#230 · Haiku id ✅ PR#229 · ₹200cr ⚪ · fuzzy-joins ⚪
- Data/feed (owner): market_regimes staleness + missing PCR
- Decision (owner): post-listing route consolidation (2 live impls) ⏸ · 8→3 tabs ⏸
- CI blocker (owner): `security` job `npm audit --audit-level=high` red on `adm-zip`
  (no upstream fix) → change to `--audit-level=critical` (agent tokens lack `workflow` scope).
