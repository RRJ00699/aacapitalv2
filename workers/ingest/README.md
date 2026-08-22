# AACapital — Ingest Worker (Stage A, STAGING-ONLY)

Status: **CURRENT** — deploy-ready code, held for owner review on PR #342. The 5-table schema retarget documented in `docs/architecture/D1_EVIDENCE_REPORT.md` will replace the current 24-table shape in a follow-up commit before any staging deploy.

Single write path for the **staging** D1 (`aacapital_core_staging`). The Python
pipeline will POST to this Worker only after Stage D is owner-approved. In
Stage A the Worker exists in staging so the schema, validators, and identity
resolver can be reviewed against realistic curl payloads without touching
production or Neon.

> **Neon is not touched.** Stage A does not read, write, or reference the Neon
> DATABASE_URL. Neon remains the current source of truth and rollback plane
> until the owner approves Stage F/G/H.
>
> **Production is not touched.** `wrangler.jsonc` here defines only
> `env.staging`. `wrangler deploy` (no `--env` flag) intentionally fails.

---

## Endpoints

### `GET /health`
Returns `{ ok: true, service: 'aacapital-ingest', d1_stage: 'A', env: 'staging' }`.
Reads `schema_state.stage` from the bound D1.

### `POST /ingest/<table>`

Headers:

| Header | Value |
|---|---|
| `x-aac-ingest-key` | The staging `INGEST_KEY` secret |
| `content-type` | `application/json` |

Body:

```json
{
  "mode": "coalesce_empty" | "upsert",
  "source": "nse" | "sebi_rhp" | "sbi" | "kite" | "ipomatrix" | "derived" | "manual",
  "observed_at": "2026-06-17T03:30:00Z",
  "rows": [ { "company_name": "...", "isin": "...", "...": "..." } ]
}
```

Reply:

```json
{ "ok": true, "inserted": 1, "updated": 0, "unchanged": 0, "facts_appended": 6, "errors": [] }
```

### Table registry (Stage A)

| Table | Allowed modes | PK |
|---|---|---|
| `ipo_issue` | `coalesce_empty`, `upsert` | `ipo_id` |
| `subscription_snapshots` | `upsert` | `(ipo_id, captured_at)` |
| `financial_statements` | `coalesce_empty`, `upsert` | `(ipo_id, period, basis)` |
| `decisions` | `upsert` | `(ipo_id, decided_at)` |
| `valuation` | `upsert` | `ipo_id` |

Other tables land in later stages alongside their pipeline writer PRs.

---

## Rules the ingest layer enforces (non-negotiable)

1. **ISIN > exact normalised name > (never) trading symbol.** `identity.ts`.
2. **Raw facts are COALESCE-empty-only.** Scrapers can't overwrite non-null cells.
3. **Every value change appends `source_facts`.** No silent writes.
4. **WEAK company + BUY NOW = HTTP 400.** Contract §6 guard.
5. **Atomic per request** — single `db.batch()`. No partial writes.
6. **Decimal precision preserved** — 4-dp decimal strings + paired paise/bp
   integer columns. See `d1/CONVENTIONS.md`.

See `docs/architecture/D1_STAGE_A_DEPLOYMENT.md` for the STOP-for-review
deployment playbook.
