# Architecture decisions

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

## ADR-005 — Cloudflare Free constraints

- **Decision:** Static payloads use KV. During the listing window, the existing Worker calls Kite directly and coalesces depth for 15 seconds in KV. The daily Kite token is copied to protected KV by snapshot publication. No Durable Object, queue, paid Worker, or Neon request is used for a UI poll.
- **Why:** This is the fewest-moving-parts design compatible with Cloudflare Free and preserves live broker prices.
- **Alternatives:** Browser-to-Kite would expose credentials and runs into browser/CORS constraints. Durable Objects add cost/complexity. Worker-to-Neon violates zero wake.
- **Tradeoffs:** Kite availability and Free-plan request quotas bound freshness. Forward history is captured independently every five minutes into `listing_observations`.
- **Owner:** Runtime architecture
- **Date:** 2026-08-04
