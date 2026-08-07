# Architecture decisions

Status: Accepted

Permanent decisions are append-only. Supersede an ADR with a later ADR; do not silently rewrite it.

## ADR-001 — Zero wake

- **Decision:** User-facing static IPO routes may import KV/snapshot and pure calculation modules, but never a database client. A missing snapshot returns an explicit, backward-compatible empty/degraded payload.
- **Why:** A page view must not wake Neon or make availability depend on database cold starts.
- **Alternatives:** Query-on-miss and stale-while-revalidate were rejected because both eventually wake Neon from a request.
- **Tradeoffs:** Pipeline publication becomes a hard availability dependency; versioned previous-pointer rollback limits that risk.
- **Owner:** Web architecture
- **Date:** 2026-08-04

## ADR-002 — ISIN identity

- **Decision:** ISIN is the durable security identity. Exchange symbols are mutable display/routing aliases; IPO relations remain keyed by canonical `ipo.id` resolved from ISIN where upstream data supplies it.
- **Why:** Renames, exchange differences, and reused/changed symbols must not split history.
- **Alternatives:** Symbol-only identity was rejected; fuzzy company-name matching is permitted only for reviewed ingestion reconciliation.
- **Tradeoffs:** Sources without ISIN need an explicit resolution/provenance step.
- **Owner:** Data architecture
- **Date:** 2026-08-04

## ADR-003 — Three verdict model

- **Decision:** Product verdicts are exactly `GOOD`, `WATCH`, or `JUNK`; unavailable evidence is represented separately as incomplete/confidence metadata, never a fourth verdict.
- **Why:** The product needs one stable decision vocabulary while remaining honest about evidence coverage.
- **Alternatives:** Binary accept/reject loses watch-list nuance; `UNKNOWN` as a verdict confuses evidence state with judgment.
- **Tradeoffs:** Consumers must show both verdict and completeness.
- **Owner:** Product and scoring
- **Date:** 2026-08-04

## ADR-004 — Pipeline owns snapshots

- **Decision:** `pipeline/cron.py` invokes `warm_kv.py` once after canonical writes. That protected publisher is the sole production producer of all four versioned route snapshots. Operators do not publish snapshots as an operational step.
- **Why:** Publication must follow data dependencies automatically, have one accountable owner, and make an incomplete pipeline fail visibly.
- **Alternatives:** Manual admin calls and per-route query-on-miss were rejected. Independent route crons were rejected because they create competing producers.
- **Tradeoffs:** The Worker publisher URL/key are required pipeline configuration. Immutable values occupy up to seven days of KV before expiry.
- **Owner:** Pipeline
- **Date:** 2026-08-04

## ADR-005 — Cloudflare Free constraints (superseded by ADR-006 for Kite token/live overlay)

- **Decision:** Static payloads use KV. No Durable Object, queue, paid Worker, or Neon request is used for a UI poll. Kite token storage and live overlay behavior are superseded by ADR-006.
- **Why:** This is the fewest-moving-parts design compatible with Cloudflare Free and preserves live broker prices.
- **Alternatives:** Browser-to-Kite would expose credentials and runs into browser/CORS constraints. Durable Objects add cost/complexity. Worker-to-Neon violates zero wake.
- **Tradeoffs:** Kite availability and Free-plan request quotas bound freshness. Forward history is captured independently every five minutes into `listing_observations`.
- **Owner:** Runtime architecture
- **Date:** 2026-08-04

## ADR-006 — Kite credential and live overlay (supersedes ADR-005 token storage)

- **Investigation:** Wrangler/API secret replacement uses a Worker secret version and may create/deploy a new Worker version; the repository workflow has no scoped Cloudflare token, deployment permission, rollback transaction, or proven Free-plan call budget. Daily rotation is therefore not proven safe.
- **A — Worker secret rotation:** secret stays protected, but implies daily Cloudflare API mutation/version lifecycle and a failure can leave the prior expired token. Rejected until version/deployment and rollback behavior are proven in a non-production account.
- **B — Server-only encrypted short-lived storage:** needs a continuously available trusted server and key-management lifecycle; none exists here. Rejected.
- **C — Protected broker proxy:** best future design if the pipeline/runtime gains an owned, authenticated always-on service, but adds operational surface today. Deferred.
- **D — Temporarily blocked:** selected. Static IPO Live snapshots and captured observations remain available; the UI truthfully reports `live_overlay: BLOCKED`, and the user route makes no Kite request. The BLOCKED live overlay is an intentional architectural decision, not a missing implementation.
- **Decision:** Never store a Kite token in normal KV and do not rotate secrets daily. No daily deployment is required. Re-enable the overlay only after an owner-approved credential threat model, least-privilege permission test, quota calculation, and rollback drill.
- **Cost:** $0 paid API usage for this change.

## ADR-007 — Snapshot producer resource contract

- **Builder:** `pipeline/build/build_snapshots.ts` uses TypeScript to call canonical domain builders directly. Cold Node/tsx startup is expected to be 1–3 seconds.
- **Scope:** mainboard IPOs with ISIN that are upcoming/open, listing today, or within the Journey monitoring window configured in `PIPELINE_LIMITS.JOURNEY_MONITORING_DAYS`; selected-count and concurrency bounds are the documented constants in `lib/config/pipeline.ts`. There is no full-history default.
- **Queries:** exactly `PIPELINE_LIMITS.SNAPSHOT_FIXED_NEON_QUERIES + N` for `N` selected IPOs: Command, index, selection, per-IPO Journey, and IPO Live input reads. Default worst case follows the configured default selected-count constant.
- **KV:** `3 + N` logical snapshots; versioned publication normally performs four KV writes per snapshot when an active version exists and one read, while routes use 2–4 reads depending on active/previous fallback. Payload size is printed before publication.
- **Runtime/cost estimate:** normally 5–20 seconds plus Neon cold start; one manually dispatched pipeline run consumes under one Actions minute for snapshot work, ordinary Cloudflare Worker/KV Free-plan usage, no paid APIs, and expected monetary cost $0.

## ADR-008 — Forward pre-open capture contract

- **Existing schema only:** writes `listing_observations(ipo_id, observed_at, obs_type, ltp, buy_qty, sell_qty, payload)` with `obs_type='preopen'`. Payload is `{isin,symbol,discovery_price,depth}`. `ON CONFLICT (ipo_id,obs_type,observed_at) DO NOTHING` provides minute-bucket idempotency.
- **Bounds:** IST-today mainboard listings are resolved by ISIN first, count/retry limits are the documented constants in `pipeline/config/__init__.py`, and one Kite quote call is made per selected listing per five-minute session. Dry-run prints IPO name, ISIN, symbol, listing date, reason selected, and the write contract. Expected rows/session are bounded by the configured default limit.
- **Schedule:** enabled for weekdays only at 03:25–04:35 UTC, which is 08:55–10:05 IST. This intentionally covers the 09:00–09:40 IST decision window, remains bounded at 75 maximum scheduled checks/week, and fast-exits when no eligible IPO lists that day. It is not broadened to 24/7.
- **Kite credential design selected for future implementation:** Cloudflare Worker Secret rotation using `wrangler versions secret put` → verification → explicit `wrangler versions deploy`. Future implementation requires a scoped Workers Scripts Write/Edit token, no Kite token in KV, no token in logs/artifacts/responses, rotation before the market window, deployment verification, ntfy alert on rotation or verification failure, and static snapshot fallback when unavailable. This PR records the owner decision only; it does not implement or deploy secret rotation.


## ADR-009 — Research Separation

- **Decision:** Production code must never import from `research/`. Research outputs must graduate through validation before entering `pipeline/` or any user/runtime path.
- **Why:** Experimental work must not become a production dependency by accident; validated promotion keeps data lineage, owner review, and cleanup boundaries explicit.
- **Alternatives:** Direct imports from `research/` were rejected because they blur exploratory scripts with supported runtime code.
- **Tradeoffs:** Promotion requires a small validation step, but production dependencies remain auditable and stable.
- **Owner:** Repository architecture
- **Date:** 2026-08-04
