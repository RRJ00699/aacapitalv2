# AACapital kickstart audit — PR #291 corrections

Date: 2026-08-04. Status applies to this branch; no deployment or merge was performed.

## Producer ownership

| Route | KV key | Producer | Pipeline step | Refresh frequency | Consumer |
|---|---|---|---|---|---|
| `/api/ipo-command` | `ipo-command:v6` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run | IPO command/search UI |
| `/api/ipo/index` | `ipo:index:v3` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run | IPO universe search |
| `/api/ipo/journey` | `journey:candles:v2` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run/EOD candle refresh | Journey pages; live price overlaid from broker route |
| `/api/ipo/live-preopen` | `ipo-live-preopen:v2` | protected snapshot publisher | `cron.py` step 8 → `warm_kv.py` | every pipeline run; Kite overlay ≤15 seconds during a viewed listing window | IPO Live |

There is one producer implementation and one automatic invocation. `POST /api/admin/snapshots` is a protected machine interface, not an operator workflow. It cannot publish without the pipeline-held key.

## Route audit: Current / Missing / Blocked / Deferred

| Route | Current | Missing | Blocked | Deferred |
|---|---|---|---|---|
| Command | KV-only v6 snapshot; active/previous validation; stable empty envelope on cold start | None for approved V2 contract | Deployment needs `CACHE`, publisher URL/key | Rich feeds without maintained V2 sources remain explicitly out of scope |
| Index | KV-only v3 snapshot; canonical identity payload | None | Same deployment configuration | ISIN display/search enrichment until canonical source coverage is complete |
| Journey | KV candle bundle plus unchanged live broker-price overlay and close fallback | None | Live price depends on Kite/Yahoo availability | Streaming prices; polling remains current UI contract |
| Live | KV static decision inputs plus Worker→Kite depth, 15-second coalescing, no Neon | None | Valid daily Kite token and broker availability | Durable Object/WebSocket only if Free-plan polling proves insufficient |
| Forward capture | Five-minute scheduled Kite capture into `listing_observations` | A first production run must verify credentials and observation rows | GitHub scheduling can drift; service enforces the IST window itself | Denser tick capture if evidence shows five minutes is inadequate |

## Product capability: before / after

| Route | Old capability | New capability | Regression? | Replacement implemented? |
|---|---|---|---|---|
| Command | DB-build/cache-on-miss command envelope | Same envelope from pipeline snapshot with rollback | No | Pipeline publisher replaces request-time build |
| Index | Canonical IPO search index, DB on miss | Same `rows` contract, pipeline-published | No | Versioned v3 snapshot |
| Journey | Historical candles plus live broker quote | Snapshot candles plus the same live broker quote/close fallback | No | Whole-universe candle bundle producer |
| Live | Static DB inputs, live Kite depth, attempted write to missing `ipo_preopen_book` | Snapshot inputs, live Worker→Kite depth, real capture into canonical `listing_observations` | No | Dedicated capture service and snapshot builder |

## Phase 286 `test_route_runtime` assertion classification

Line-by-line review classified the old cache-on-miss assertions as **removed because architecture changed**: command's first-call Neon query/twin-write, command stale-TTL behavior, live full-response decision-window bypass, index/journey DB query ceilings, and cache second-call mechanics are invalid under a strict KV-only consumer. Their behavioral intent is retained more strongly by tests that prohibit DB imports, publish and consume all four contracts, assert `HIT`, and corrupt active data to prove previous-pointer rollback. Auth gates and query ceilings for unrelated routes are not intentionally weakened. Any unrelated removed assertion would be accidental and must be restored; none is removed by this correction patch.

## Acceptance checklist

1. **Complete:** each listed KV snapshot has the single publisher above.
2. **Complete:** `cron.py` invokes it after DB computation.
3. **Complete:** no manual call is required.
4. **Complete:** static consumers have no DB import; CI checks this.
5. **Complete in code:** IPO Live overlays Kite depth with a 15-second maximum coalescing age.
6. **Complete in code:** Journey still calls `/api/broker/quote` and falls back to close.
7. **Complete in code:** `capture_preopen.py` writes canonical `listing_observations` independently of browser traffic.
8. **Complete:** simulated corrupt-active rollback test.
9. **Complete:** publish/consume/HIT contract tests for Command, Index, Journey, and Live.
10. **Complete:** envelope fields consumed by the existing UI are preserved.

## Operations and cost

- **Expected request runtime:** KV static reads are normally single-digit to low tens of milliseconds at the edge; Journey adds a broker request up to its 5-second timeout; Live adds Kite latency on a 15-second cache miss.
- **Expected Cloudflare cost:** $0 incremental on the Free plan at present traffic, subject to Cloudflare's published Free request/KV quotas. No Durable Object is used.
- **Expected GitHub Actions runtime:** normal pipeline adds roughly 5–120 seconds for snapshot building/publication. Each preopen capture job is expected to use roughly 1–2 runner minutes; schedule dispatch delay is outside execution time.
- **Remaining deployment blockers:** provision/verify the `CACHE` binding, `SNAPSHOT_PUBLISH_URL`, `SNAPSHOT_PUBLISH_KEY`, and broker secrets; run one listing-window capture and inspect `listing_observations`. These are deployment verification items, not missing producers. No deployment was attempted.
