Status: CURRENT

# CLEANUP REPORT — 2026-07-20 (dead-code pass)

## Summary

**Changed:** archived 4 dead API routes, 7 orphaned UI files, and 19 equity-era
lib modules to `_archive/` (preserve-not-delete rule, one `git revert` away);
repointed two non-admin redirects from the retired `/dashboard/ipo` to
`/dashboard/ipo2`; removed `initDb()` (equity-table verifier whose only caller
was the archived `/api/db/init`); pruned 7 stale `KNOWN_GAPS` contract entries;
updated the hot-route cache ledger (2 routes CURED by Phase-2, 1 archived);
added `.env.example`; extended `test_archived_routes_stay_dead.py` so nothing
archived can silently return.

**Intentionally NOT changed:** `app/api/ipo/monitor`, `market-regime`,
`tracker`, `job-flag`, `health` (owner-KEPT list); `app/api/ipo/playbook`
(zero UI callers but not previously reviewed — see Unresolved); all score
formulas, thresholds, DB writes, pipelines, and deps; the `_scripts/` tree
layout (full pipelines/research/scripts reorg would break VM cron paths —
future PR with a migration plan).

**Production behavior impact:** none intended. Archived routes had zero
callers; the retired page was reachable only via the two repointed redirects;
`tsc --noEmit` clean and full test suite green before/after.

## File disposition

| File / directory | Previous role | Action | New location | Reason |
|---|---|---|---|---|
| `app/api/ipo/levels/route.ts` | API route | archived | `_archive/routes/api-ipo-levels-route.ts.txt` | zero callers; queries `ipo_daily_levels` (absent) |
| `app/api/ipo/intelligence/route.ts` | API route | archived | `_archive/routes/api-ipo-intelligence-route.ts.txt` | zero callers; `archetype`/`lqi_final` columns (rejected LQI era) |
| `app/api/pipeline/status/route.ts` | API route | archived | `_archive/routes/api-pipeline-status-route.ts.txt` | zero callers; queries archived `technical_signals`, `management_commentary` |
| `app/api/db/init/route.ts` | API route | archived | `_archive/routes/api-db-init-route.ts.txt` | zero callers; verified equity-era tables |
| `app/dashboard/ipo/` (page + `IPOCommandCenterClient.tsx`) | pre-cutover command center | archived | `_archive/pages/` | superseded by `/dashboard/ipo2`; only entry was non-admin redirects (repointed) |
| `components/ipo/{IpoSignalCard, PostListingDashboard, IpoCommandCenter, IpoCapitalProtectionPanel}.tsx` | old-page component chain | archived | `_archive/pages/` | imported only by the retired page/each other; IpoSignalCard carried rejected 10/30 gap bands |
| `components/features/ipo_play_selector.py` | stray Python in components/ | archived | `_archive/pages/` | not importable by Next; diverged sibling of `_scripts/ipo/ipo_play_selector.py` |
| `lib/ipoSignal.ts` | old-band signal helper | archived | `_archive/lib/` | only importer was IpoSignalCard; fallback used REJECTED 10/30 bands (contract §7) |
| `lib/intelligence/*` (6), `lib/providers/*` (5), `lib/constants/stocks.ts`, `lib/watchlist.ts`, `lib/workboard-config.ts`, `lib/scrapers/index.ts`, `lib/ai/index.ts`, `lib/design-tokens.ts`, `lib/design/tokens.ts` | equity-era ("200-stock"/AMFI/commentary) | archived | `_archive/lib/` | zero importers at HEAD (per-module grep; `watchlist`/`providers` hits were comments/string keys) |
| `lib/ipo/{tape,anchors,pipeline,gmp-disappointment,scoring}.ts` | unused IPO helpers | archived | `_archive/lib/` | zero importers (scoring imported only by dead gmp-disappointment) |
| `lib/db/schema.ts` `initDb()` | equity-table verifier | removed (in-file) | comment points to archive | only caller archived; `getDb()` kept (auth + market-regime) |
| `.env.example` | absent | created | repo root | enumerated from actual `process.env`/`os.environ` usage |

## Dead-code removals (evidence)

Every archive decision: repo-wide grep at `origin/main` (`bb35d9a`) across
`app/ components/ lib/ _scripts/ .github/` — zero references outside the
archived cluster itself; guarded forever by
`test_archived_routes_stay_dead.py` (now 100+ parametrized checks).
Replacements: `/dashboard/ipo` → `/dashboard/ipo2`; `lib/ipoSignal` semantics →
`gap_bucket` from `build_ipo_consolidated_v2.py` (validated bands); none needed
for the rest.

## Documentation conflicts resolved

Covered in PR #260 (`docs/AACAPITAL_PRODUCT_CONTRACT.md` is authoritative;
equity-era README archived). This pass removes the last *code* carrying the
rejected 10/30 gap bands and the LQI-era route.

## Cost & risk review

API/Worker/DB/storage/jobs: **no increases**. Archiving routes slightly
reduces Worker surface; `initDb` removal drops one potential Neon query path;
no polling changes, no new services, no migrations, no data deletions.
Rollback: every item is a `git revert` (archived, not deleted).

## Validation results

| Check | Command | Result |
|---|---|---|
| Typecheck | `npx tsc --noEmit` | clean (exit 0) |
| Python tests | `python -m pytest _scripts/tests/ -q` | see PR (all green; DB-gated skips) |
| Route-guard tests | `pytest test_archived_routes_stay_dead.py -q` | pass |
| Contract blocks | extractor count | 69 sql blocks (floor 40 intact) |
| Lint / build | run on PC (`npm run lint` / `npm run build`) | owner-verified pre-merge; clear stale `.next/` first |

## Unresolved (recorded, not guessed)

- `app/api/ipo/playbook` — zero UI callers but never owner-reviewed; keep or
  archive next pass (it is is_sme-filtered and harmless meanwhile).
- Root-level scripts (`link_brlm_scores.py`, `load_instrument_tokens.py`,
  `real_return_analysis.py` duplicate, `run_abcapital_fix.ps1`) and root CSV/
  XLSX outputs — purpose/liveness unconfirmed; candidates for `artifacts/` +
  `.gitignore` in the reorg PR.
- `_scripts/` → `pipelines|research|scripts` reorg — needs a VM cron + PS1
  path-migration plan; deliberately deferred.
- `_scripts/fill_listing_open_from_candles.py` vs `_scripts/ipo/` twin —
  pipeline calls the root one; consolidate next pass after confirming no VM
  job references the twin.
