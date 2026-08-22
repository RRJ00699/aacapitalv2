# Stage A Constraints — Explicit Acknowledgement

Owner directives applied to Stage A (2026-06):

1. **Do not modify, delete, or decommission Neon.** Neon remains the
   rollback / source-of-truth system until D1 migration reconciliation is
   complete.
2. **Stage A must use a completely separate Cloudflare staging environment.**
   Staging D1, staging KV (later stages), staging Worker, staging cron. No
   production resource is touched.
3. **No automatic deployment.** Artifacts, migrations, bindings,
   configuration, tests and exact deployment commands are produced; a human
   owner reviews and then decides whether to run them.
4. **Public web routes must remain KV-only.** D1 is pipeline / write-plane
   only. `lib/web-plane-db-contract.test.ts` remains the enforcement.
5. **No paid APIs or new external services** are introduced without
   reporting cost and getting approval first.

## Where each constraint is enforced in the Stage A code

| # | Constraint | File | Evidence |
|---|---|---|---|
| 1 | Neon untouched | (all Stage A files) | Grep `\bNEON_\|DATABASE_URL\|psycopg2\|@neondatabase` across added paths returns 0 hits |
| 2 | Staging isolation | `workers/ingest/wrangler.jsonc` | `env.staging` only; no top-level bindings; no `env.production` block |
| 2 | Staging isolation | `docs/architecture/D1_STAGE_A_DEPLOYMENT.md` | All commands use `--env staging`; staging D1 name `aacapital_core_staging`; staging Worker name `aacapital-ingest-staging` |
| 2 | Root config untouched | `wrangler.jsonc` (root) | No change in this PR |
| 2 | Public app untouched | `app/**`, `components/**`, `lib/**`, `pipeline/**`, `.github/workflows/**` | No change in this PR |
| 3 | No auto-deploy | Emergent build container | Holds no CF API token; cannot call `wrangler`. All commands live in the deployment doc for the human owner to run. |
| 3 | Failsafe against accidental prod deploy | `workers/ingest/wrangler.jsonc` | `wrangler deploy` with no `--env` flag fails; no default env defined; no `env.production` block defined |
| 4 | Public plane KV-only | `workers/ingest/wrangler.jsonc` | `DB_CORE` binding lives on the ingest Worker only. Public Next.js Worker (root `wrangler.jsonc`) has no D1 binding — unchanged |
| 4 | Public plane guard | `lib/web-plane-db-contract.test.ts` | Not modified in Stage A. Will be **extended** (not weakened) in Stage D to also ban imports of `@/lib/db-d1` from the public allowlist |
| 5 | No paid services | `workers/ingest/wrangler.jsonc` | `observability.enabled: false`. No new external SDKs. No Anthropic / Kite / R2 change |
| 5 | Cost budget | Estimated Cloudflare usage delta for Stage A | D1 free tier: unused rows, unused reads/writes. Workers free tier: 1 additional Worker (staging); requests limited to owner's smoke tests. Estimated added spend: **$0.00/month.** |

## Stage boundary

Stage A does not include:
- Historical copy of Neon data into D1 (Stage B).
- Reconciliation (Stage C).
- Any change to `pipeline/cron.py` or its GitHub Actions dispatches (Stage D).
- Any change to snapshot publishers or public app routes (Stages E/F).
- Any change to the JOB_FLAG/CACHE production namespace incident from
  2026-07-18. That fix will land in a separate, owner-approved PR after
  Stage A merges.
- Any change to production `wrangler.jsonc`.
- Any change to Neon.

## Owner sign-off checklist

Before merging Stage A the reviewer confirms:

- [ ] I have read `d1/CONVENTIONS.md`.
- [ ] I have read `d1/migrations/000{1..4}_*.sql`.
- [ ] I have read `workers/ingest/src/*.ts`.
- [ ] I understand no command in this PR runs automatically; the deploy
      playbook in `D1_STAGE_A_DEPLOYMENT.md` is optional.
- [ ] I understand Neon, production KV, production Worker, and production
      cron are all untouched.
- [ ] I approve staging-only deployment.
