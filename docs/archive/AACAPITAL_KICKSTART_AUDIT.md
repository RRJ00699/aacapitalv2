> **ARCHIVED DOCUMENT.** Historical evidence only. Current authority: `docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md`.

# AACapital kickstart audit — PR #291 corrections

Status: Accepted

Date: 2026-08-04. Status applies to this branch; no deployment or merge was performed.

## Producer ownership

| Route | KV key | Producer | Pipeline step | Refresh frequency | Consumer |
|---|---|---|---|---|---|
| `/api/ipo-command` | `ipo-command:v6` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run | IPO command/search UI |
| `/api/ipo/index` | `ipo:index:v3` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run | IPO universe search |
| `/api/ipo/journey` | `journey:isin:<ISIN>:v1` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run/EOD candle refresh | Journey pages served from per-IPO snapshots |
| `/api/ipo/live-preopen` | `ipo-live-preopen:v2` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run; live overlay intentionally BLOCKED | IPO Live |

There is one producer implementation and one automatic invocation. `POST /api/admin/snapshots` is a protected machine interface, not an operator workflow. It cannot publish without the pipeline-held key.

## Route audit: Current / Missing / Blocked / Deferred

| Route | Current | Missing | Blocked | Deferred |
|---|---|---|---|---|
| Command | KV-only v6 snapshot; active/previous validation; stable empty envelope on cold start | None for approved V2 contract | Deployment needs `CACHE`, publisher URL/key | Rich feeds without maintained V2 sources remain explicitly out of scope |
| Index | KV-only v3 snapshot; canonical identity payload | None | Same deployment configuration | ISIN display/search enrichment until canonical source coverage is complete |
| Journey | KV-only per-ISIN snapshot with active/previous fallback | None for approved V2 contract | Deployment needs `CACHE` and per-IPO snapshot publication | Streaming prices remain deferred |
| Live | KV static decision inputs plus honest `live_overlay: BLOCKED`, no Neon and no Kite call | Safe credential automation remains intentionally unresolved | Live overlay blocked by ADR-006 until owner-approved credential design | Durable Object/WebSocket only if a future approved design needs it |
| Forward capture | Manual-dispatch bounded capture into `listing_observations`; no schedule activated without owner approval | A first production dry-run must verify credentials and observation rows | GitHub scheduling awaits owner approval; service enforces the IST window itself | Denser tick capture if evidence shows five minutes is inadequate |

## Product capability: before / after

| Route | Old capability | New capability | Regression? | Replacement implemented? |
|---|---|---|---|---|
| Command | DB-build/cache-on-miss command envelope | Same envelope from pipeline snapshot with rollback | No | Pipeline publisher replaces request-time build |
| Index | Canonical IPO search index, DB on miss | Same `rows` contract, pipeline-published | No | Versioned v3 snapshot |
| Journey | Historical candles plus live broker quote | Per-ISIN snapshot candles with route-side active/previous fallback | Live quote intentionally removed pending safe credential design | Per-IPO Journey snapshot producer |
| Live | Static DB inputs, live Kite depth, attempted write to missing `ipo_preopen_book` | Snapshot inputs plus honest BLOCKED overlay; forward capture writes canonical `listing_observations` when manually run | Live overlay intentionally blocked by ADR-006 | Dedicated capture service and snapshot builder |

## Phase 286 `test_route_runtime` assertion classification

Line-by-line review classified the old cache-on-miss assertions as **removed because architecture changed**: command's first-call Neon query/twin-write, command stale-TTL behavior, live full-response decision-window bypass, index/journey DB query ceilings, and cache second-call mechanics are invalid under a strict KV-only consumer. Their behavioral intent is retained more strongly by tests that prohibit DB imports, publish and consume all four contracts, assert `HIT`, and corrupt active data to prove previous-pointer rollback. Auth gates and query ceilings for unrelated routes are not intentionally weakened. Any unrelated removed assertion would be accidental and must be restored; none is removed by this correction patch.

## Acceptance checklist

1. **Complete:** each listed KV snapshot has the single publisher above.
2. **Complete:** `cron.py` invokes it after DB computation.
3. **Complete:** no manual call is required.
4. **Complete:** static consumers have no DB import; CI checks this.
5. **Intentionally blocked:** IPO Live does not call Kite; the route reports `live_overlay: BLOCKED` per ADR-006.
6. **Complete:** Journey consumes per-ISIN snapshots and does not wake Neon from the user route.
7. **Complete in code:** `capture_preopen.py` writes canonical `listing_observations` independently of browser traffic.
8. **Complete:** simulated corrupt-active rollback test.
9. **Complete:** publish/consume/HIT contract tests for Command, Index, Journey, and Live.
10. **Complete:** envelope fields consumed by the existing UI are preserved.

## Operations and cost

- **Expected request runtime:** KV static reads are normally single-digit to low tens of milliseconds at the edge; Journey and Live do not add Neon or Kite calls in the approved architecture.
- **Expected Cloudflare cost:** $0 incremental on the Free plan at present traffic, subject to Cloudflare's published Free request/KV quotas. No Durable Object is used.
- **Expected GitHub Actions runtime:** normal pipeline adds roughly 5–120 seconds for snapshot building/publication. Each preopen capture job is expected to use roughly 1–2 runner minutes; schedule dispatch delay is outside execution time.
- **Remaining deployment blockers:** provision/verify the `CACHE` binding, `SNAPSHOT_PUBLISH_URL`, `SNAPSHOT_PUBLISH_KEY`, and broker secrets; run one listing-window capture and inspect `listing_observations`. These are deployment verification items, not missing producers. No deployment was attempted.


## Node/tsx runtime verification — 2026-08-04

- `pipeline/build/build_snapshots.ts` uses top-level await intentionally and is executed with `npx tsx`.
- Verified local runtime: Node `v24.15.0`; `npx tsx --version` reports `tsx v4.22.4` on Node `v24.15.0`.
- GitHub Actions compatibility: `.github/workflows/pipeline.yml` now installs Node 20 dependencies before the Python pipeline can invoke `warm_kv.py`; `tsx` is a dev dependency and supports TypeScript modules with top-level await on modern Node versions. CI already sets up Node 20/22 for typecheck/build/UAT jobs.
- CI compatibility: `npm run typecheck` and the DB-env-absent `npm run build` exercise TypeScript parsing/module compatibility without requiring Neon credentials.

## Final architecture audit — 2026-08-04

Verified findings only:

- Journey selection now has one reusable implementation in `pipeline/build/journey_universe.ts`; no duplicate Journey selection SQL remains in `pipeline/build/build_snapshots.ts`.
- Pipeline limits used by the TypeScript snapshot/publication path are centralized in `lib/config/pipeline.ts`; pre-open capture limits are centralized in `pipeline/config/__init__.py`.
- User-facing Journey and IPO Live routes continue to read snapshots and do not import Neon/database clients.
- The admin snapshot endpoint remains publication-only: it validates supplied JSON and writes KV, with no domain-builder or database imports.
- No production code import from `research/` was found in the touched production paths.
- The live overlay remains intentionally `BLOCKED` until credential automation is proven safe; no Kite token is written to normal KV.
