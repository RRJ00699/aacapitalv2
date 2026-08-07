# Architecture State

Status: Accepted
Date: 2026-08-04

## Current milestone

Final polish before merge for the zero-wake IPO snapshot architecture.

## Current PR

PR #292 on branch `codex/implement-required-corrections-for-pr-#291`.

## Current architecture score

9/10. User-facing IPO routes are KV snapshot consumers, the pipeline owns snapshot production, and Live overlay credential handling is intentionally blocked until a safe design is approved.

## Repository health

8/10. Focused typecheck, unit, integration, and DB-env-absent build checks pass locally. Remaining health work is remote CI verification after the branch can be pushed.

## Database health

No migration or schema change is part of this PR. Snapshot production reads Neon from the pipeline only; user routes must not wake Neon. Forward capture writes only to the existing `listing_observations` table when manually run with credentials.

## Cloudflare status

Publication uses the protected admin snapshot endpoint and Cloudflare KV. No Worker secret rotation, deployment API call, Durable Object, queue, or paid Cloudflare feature is introduced by this PR.

## Production readiness

Ready for owner review after remote CI. Production deployment still requires configured `CACHE`, `SNAPSHOT_PUBLISH_URL`, and `SNAPSHOT_PUBLISH_KEY`, plus one owner-approved listing-window capture dry-run.

## Outstanding blockers

- No safe automated Kite credential design is approved; IPO Live overlay remains intentionally `BLOCKED`.
- No pre-open capture schedule is activated without owner approval.
- This local environment has no `origin` remote configured, so the branch could not be pushed from here.
