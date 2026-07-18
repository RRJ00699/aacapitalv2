# Route archive decisions — Phase 1 (IPO-only cleanup)

Method: for every `app/api/**/route.ts`, count callers across **app, components,
_scripts, .github, docs** — not just the UI. "Zero UI references" is NOT evidence
of death: several routes are called by the VM, cron, or the auth framework.

## ARCHIVED (zero callers of any kind, provably dead)

| Route | Evidence |
|---|---|
| `/api/cron/premarket-brief` | The file **self-declares RETIRED**: "part of the abandoned early-vision engine… not wired into the pipeline or job_runner and is not called by the UI." |
| `/api/ipo/tape` | In-memory stub — its own comment says "per session — Phase 2 will use DB". Never finished, never called. |

Preserved verbatim in `_archive/routes/*.ts.txt`. Guarded by
`_scripts/tests/test_archived_routes_stay_dead.py`.

## KEPT — alive via non-UI callers (do NOT archive)

| Route | Real caller |
|---|---|
| `/api/admin/job-flag` | VM `job_runner.py` polls it every minute (the Neon-sleep design) |
| `/api/admin/kv-put` | VM ticker writes live snapshots |
| `/api/ipo-command?warm=1` | pipeline cache-warm after each run |
| `/api/auth/[...nextauth]`, `/api/auth/zerodha/callback` | NextAuth / OAuth redirect targets |
| `/api/health` | DB-free liveness probe (Guardrail B + E) |
| `/api/db/init` | one-shot setup |
| `/api/market-regime` | **REQUIRED** per IPO_BUSINESS_REQUIREMENTS §2C.10 (regime + VIX + PCR). Stale data is a feed bug, not a dead feature. |
| `/api/post-listing` **and** `/api/ipo/post-listing` | both live: `PostListingDashboard.tsx:56` and `IpoCommandCenter.tsx:232` |

## OWNER DECISIONS — RESOLVED 2026-07-18

These have no caller today, but they are IPO features that may be intentional
backend/admin endpoints or half-built work. **Not archived without your call.**

| Route | What it is | Question |
|---|---|---|
| `/api/ipo/listing-day` | "Live listing day signals from Kite — VWAP, volume, bid/ask, hold/exit verdict" (108 lines) | Superseded by `/api/ipo/live-preopen` (341 lines)? Or a second live surface? |
| `/api/ipo/memo` | POST, `maxDuration=30`, calls Anthropic | Superseded by the Sonnet RHP pipeline? |
| `/api/ipo/drhp` | POST, `maxDuration=60`, calls Anthropic | Same question — `rhp_sonnet.py` does this in the pipeline now |
| `/api/ipo/monitor` | GET — "IPOs that listed weak BUT have strong quality scores" | A screen that was never built? Useful idea. |
| `/api/ipo/gmp`, `/api/ipo/gmp-refresh` | GMP write/refresh | Pipeline does GMP via scripts — are these admin fallbacks? |
| `/api/ipo/scrape`, `/api/ipo/upload` | POST admin-style | Manual tools you use from the browser? |
| `/api/ipo/subscription` | creates its own table | Superseded by `ipo_consolidated` subscription fields? |

**Owner ruling 2026-07-18:**
- ARCHIVE: `listing-day` (superseded by live-preopen), `memo`, `drhp` (superseded
  by the rhp_sonnet pipeline), `gmp`, `gmp-refresh`, `scrape`, `upload`,
  `subscription` (browser-era admin fallbacks the pipeline now covers).
- **KEEP: `/api/ipo/monitor`** — "listed weak BUT strong quality" is a useful
  screen idea not yet surfaced. Guarded by `test_kept_routes_still_exist`.

Note found while archiving: `test_all_routes_contract.py` carried KNOWN_FAILURES
waivers for `ipo/gmp` ("column ipo_name of relation ipo_gmp does not exist") and
`ipo/listing-day` ("relation platform_config does not exist") — i.e. those routes
were already BROKEN, further evidence they were dead. The stale waivers are removed.

---
# Phase 2 — Pages & Components

## PAGES: no safe archive work exists (honest finding)

Every page that *looks* orphaned is actually alive, repurposed, or personal:

| Page | Refs | Finding |
|---|---|---|
| `/dashboard/journey` | 0 static | **LIVE — MUST KEEP.** Linked dynamically at `app/dashboard/ipo2/page.tsx:1074` (`onJourney` → `window.location.href`). It is one of the three core screens. A naive "0 references → archive" sweep would have deleted it. |
| `/today` | 1 (commented-out nav) | **Repurposed by #232** into a markets page. Still fetches 4 LIVE routes (`market/global`, `market/snapshot`, `ipo/playbook`, `broker/status`). Functional, just not in nav — owner deliberately commented the nav entry. **Owner decision, not dead.** |
| `/dashboard/tracker` | 0 | Backed by `app/api/tracker/route.ts` — "Private distraction/frustration tracker, admin-gated (only you)". A personal tool. **Owner decision.** |
| `/dashboard/ipo` | 2 | **FROZEN rollback surface** per `UI_REQUIREMENTS §3` — never restyle, never remove. |

**Conclusion: zero pages archived in Phase 2.** Manufacturing work here would have broken the Journey screen.

## COMPONENTS: 11 archived (the real Phase 2 value)

Unreferenced by **export name** (not just filename — a file can be imported under
a different name). All verified 0 references across `app/` and `components/`:

`Loader` · `Ring` · `IpoFeatureQuality` · `IpoSimilarList` · `IpoLiveTickPanel` ·
`IpoLevelPanel` · `GlobalMarketsStrip` · `IpoPlaybookScreen` · `SettingsTab` ·
`ZerodhaStatusBanner` · `SubTabs`

Preserved in `_archive/components/`. Guarded by `test_no_orphan_components.py`,
which scans export names and **found `Ring.tsx` that a filename-based scan
missed** — the test earned its place immediately.

Note: `IpoLiveTickPanel` and `IpoLevelPanel` are IPO-domain and may represent
unfinished live-screen work. They are archived, not deleted — one `git revert`
away if you want them wired up.
