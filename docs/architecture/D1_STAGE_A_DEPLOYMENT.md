# Stage A Deployment — STAGING ONLY (STOP for review before running anything)

Status: **ARTIFACTS READY — NOT DEPLOYED**. Nothing on your Cloudflare account
is touched by anything in this branch until you personally run the commands
in §Deployment. The commands are provided so you can review them before
execution.

---

## Owner-imposed guardrails (all satisfied by these artifacts)

| # | Constraint | How Stage A honours it |
|---|---|---|
| 1 | Neon is not modified, deleted, or decommissioned | Zero references to `DATABASE_URL` / `NEON_*` in Stage A source. Migration file `0001_spine.sql` etc. run against D1 only. |
| 2 | Stage A uses a completely separate Cloudflare staging environment | `workers/ingest/wrangler.jsonc` defines only `env.staging`. D1 name `aacapital_core_staging`. Worker name `aacapital-ingest-staging`. No production KV, D1, Worker, or cron is created or edited. Root `wrangler.jsonc` is untouched. |
| 3 | No automatic deployment | Nothing in this repo can push to your CF account. The Emergent build environment holds no CF token. Commands below are for you to run manually after review. |
| 4 | Public web routes remain KV-only | No route in `app/**` is edited in Stage A. `lib/web-plane-db-contract.test.ts` is untouched. The ingest Worker is a separate binary in `workers/ingest/`; the public Next.js Worker never binds `DB_CORE`. |
| 5 | No paid APIs / new external services without approval | No new external services introduced. Workers Logs / `observability` is explicitly set to `false`. R2 unchanged. Anthropic / Kite unchanged. All costs = current CF Free-tier budget. |

---

## Artifact inventory (this PR)

```
d1/CONVENTIONS.md
d1/migrations/0001_spine.sql
d1/migrations/0002_market.sql
d1/migrations/0003_engine.sql
d1/migrations/0004_ops.sql
workers/ingest/wrangler.jsonc
workers/ingest/src/index.ts
workers/ingest/src/db.ts
workers/ingest/src/identity.ts
workers/ingest/src/schemas.ts
workers/ingest/src/source-facts.ts
workers/ingest/README.md
docs/architecture/D1_MIGRATION_PLAN.md              (Phase-0 audit; no code impact)
docs/architecture/D1_STAGE_A_DEPLOYMENT.md          (this file)
docs/architecture/D1_STAGE_A_CONSTRAINTS.md         (constraint acknowledgement)
```

Root `wrangler.jsonc`: **not modified** in Stage A.
`app/**`, `lib/**`, `components/**`, `pipeline/**`, `.github/workflows/**`,
`workers/kite-broker-proxy/**`: **not modified** in Stage A.

---

## STOP HERE for review

Please review the artifacts above and confirm:

1. Migration DDL matches your intent (see `d1/migrations/000{1..4}_*.sql` +
   `d1/CONVENTIONS.md`).
2. Ingest Worker semantics match your writer rules (`workers/ingest/README.md`
   +  `workers/ingest/src/*.ts`).
3. You accept the guardrails above.

Only then run the deployment commands in the next section — staging only.

---

## Deployment (STAGING ONLY, run manually after approval)

**Prerequisites (once):**

```bash
npx wrangler --version   # ≥ 3.60 required
npx wrangler whoami      # confirm the Cloudflare account you expect
```

### 1. Create the staging D1

```bash
npx wrangler d1 create aacapital_core_staging
```

Copy the printed `database_id` into `workers/ingest/wrangler.jsonc` →
`env.staging.d1_databases[0].database_id`, then:

```bash
git add workers/ingest/wrangler.jsonc
git commit -m "chore(d1): pin staging DB_CORE database_id"
```

### 2. Apply Stage A migrations to a LOCAL staging D1 first (offline)

```bash
npx wrangler d1 migrations apply DB_CORE --local --env staging \
  --config workers/ingest/wrangler.jsonc

npx wrangler d1 execute DB_CORE --local --env staging \
  --config workers/ingest/wrangler.jsonc \
  --command "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
```

Expected ≥ 24 tables plus SQLite/CF system tables. Sanity:

```bash
npx wrangler d1 execute DB_CORE --local --env staging \
  --config workers/ingest/wrangler.jsonc \
  --command "SELECT k, v FROM schema_state"
#  stage              | A
#  applied_migrations | 0001_spine,0002_market,0003_engine,0004_ops
```

If anything is off, edit the migration files and re-run — nothing has
touched your Cloudflare account yet.

### 3. Apply migrations to REMOTE staging D1

```bash
npx wrangler d1 migrations apply DB_CORE --env staging \
  --config workers/ingest/wrangler.jsonc
```

Wrangler will prompt for confirmation. Reply `y`.

### 4. Set the staging ingest secret

```bash
openssl rand -hex 32 | npx wrangler secret put INGEST_KEY --env staging \
  --config workers/ingest/wrangler.jsonc
```

DO NOT copy this into any production secret store yet. Stage D will introduce
an `INGEST_KEY_STAGING` GitHub Actions secret used only by the staging
dispatch of `pipeline/cron.py`; the production `pipeline.yml` continues to
write to Neon exactly as it does today.

Optional alert channel:

```bash
echo "$STAGING_NTFY_TOPIC_VALUE" | npx wrangler secret put NTFY_TOPIC --env staging \
  --config workers/ingest/wrangler.jsonc
```

### 5. Deploy the staging Worker

```bash
npx wrangler deploy --env staging --config workers/ingest/wrangler.jsonc
```

Deployment URL will be `https://aacapital-ingest-staging.<workers-subdomain>.workers.dev`.

> `wrangler deploy` (no `--env`) intentionally fails because no default env is
> defined in `workers/ingest/wrangler.jsonc`. There is no path from these
> artifacts to a production deploy.

### 6. Smoke tests (staging)

```bash
curl -s https://aacapital-ingest-staging.<sub>.workers.dev/health
#  {"ok":true,"service":"aacapital-ingest","d1_stage":"A","env":"staging"}

curl -s -X POST https://aacapital-ingest-staging.<sub>.workers.dev/ingest/ipo_issue \
  -H "content-type: application/json" -d '{"rows":[]}'
#  {"error":"unauthorized"}

curl -s -X POST https://aacapital-ingest-staging.<sub>.workers.dev/ingest/ipo_issue \
  -H "x-aac-ingest-key: <STAGING_INGEST_KEY>" \
  -H "content-type: application/json" \
  -d '{"mode":"coalesce_empty","source":"nse",
       "observed_at":"2026-06-17T03:30:00Z",
       "rows":[{"company_name":"Nova AgriTech Ltd",
                "isin":"INE0R2Q01034",
                "issue_price":"41.0000",
                "issue_size_cr":"143.8100"}]}'
#  {"ok":true,"inserted":1,"updated":0,"unchanged":0,"facts_appended":2,"errors":[]}
```

Inspect the staging DB:

```bash
npx wrangler d1 execute DB_CORE --env staging \
  --config workers/ingest/wrangler.jsonc \
  --command "SELECT id, company_name, isin, status FROM ipo"

npx wrangler d1 execute DB_CORE --env staging \
  --config workers/ingest/wrangler.jsonc \
  --command "SELECT field, source, mode, new_value FROM source_facts ORDER BY id DESC LIMIT 10"
```

### 7. Optional — add a staging custom domain

Cloudflare dashboard → **Workers & Pages** → `aacapital-ingest-staging` →
**Triggers** → **Custom Domains** → `ingest-staging.aacapitalprivatelimited.com`
(or similar staging subdomain). Skip this step if you prefer the
`*.workers.dev` URL for staging.

---

## Merge

```bash
git push -u origin d1/stage-a
gh pr create \
  --title "feat(d1,staging): stage A — schema + ingest worker (staging only)" \
  --body-file docs/architecture/D1_STAGE_A_CONSTRAINTS.md
```

Merging is safe because:
- Production `wrangler.jsonc` is not modified.
- Public app routes are not modified.
- Neon is not modified.
- The staging Worker only exists if you personally ran §5.

---

## Definition of Done for Stage A

- [ ] Owner reviewed and approved artifacts.
- [ ] `wrangler d1 execute DB_CORE --env staging --command "SELECT count(*) FROM sqlite_schema WHERE type='table'"` ≥ 24.
- [ ] `curl <staging-ingest>/health` returns `{"ok":true,"d1_stage":"A","env":"staging"}`.
- [ ] Dummy `POST /ingest/ipo_issue` succeeds and lands rows in `ipo`, `ipo_issue`, `source_facts`.
- [ ] Neon dashboard shows unchanged row counts (Stage A must not have touched it).
- [ ] Production Worker deployment history unchanged.
- [ ] PR merged to `main`.

---

## Rollback

- Public app: unaffected. Nothing to roll back on the read plane.
- Staging Worker: `npx wrangler rollback --env staging --config workers/ingest/wrangler.jsonc`
- Staging D1: contains no historical data; safest is drop-and-recreate via
  `npx wrangler d1 execute DB_CORE --env staging --command "DROP TABLE <name>"`
  or `npx wrangler d1 delete aacapital_core_staging` if you want a clean slate.
- Neon: untouched — rollback plane remains 100% intact.

---

## Next

**Stage B — historical copy Neon → staging D1.** Delivered as
`_scripts/migrate/neon_to_d1.py` + `_scripts/migrate/reconcile.py` +
`_migrate/reconciliation_report.md`. Requires a **read-only** Neon connection
string (existing `NEON_READONLY_DATABASE_URL` Actions secret). No write to
Neon, no writes to production D1 (which does not exist), no writes to public
KV. Owner approval required to start Stage B — not implied by merging
Stage A.
