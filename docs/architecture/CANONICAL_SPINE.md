# AACapital canonical production spine

**Status: current.** This is the single architectural orientation document. Detailed
contracts and runbooks remain authoritative for their narrow subjects.

## Product boundary

| Product | Route | Data owner |
|---|---|---|
| Command Center | `/dashboard/ipo2` (`/ipo` redirects) | versioned `ipo-command:v6` KV snapshot |
| Complete Details | `/dashboard/ipo2/details/[isin]` | versioned `ipo-details:isin:*:v1` KV snapshot |
| Listing Day Live | Command Center live state and operational IPO APIs | KV snapshots / Kite proxy |
| Journey | `/dashboard/journey` | versioned `journey:isin:*:v1` KV snapshot |
| Admin | `/dashboard/admin` | authenticated operational APIs; Neon only for explicit operations |

Authentication/access, `/api/health`, snapshot publication, and the broker/IPO
operational APIs are supporting surfaces, not additional products. Settings and access
pages are Admin sub-surfaces. The retired distraction tracker is archived.

## Data flow and ownership

`SEBI / NSE / SBI / Kite → canonical IPO identity (ipo) → canonical facts
(ipo_issue, subscription_snapshots, source operational records) → immutable R2 objects
+ documents ledger → verified extraction (rhp_findings) → insights / valuation /
listing observations / market candles → versioned snapshots in CACHE → Command /
Details / Live / Journey.` Admin enqueues and repairs this lifecycle.

Production writers use `DATABASE_URL`. Explicit schema/read-only smoke tools use
`NEON_READONLY_DATABASE_URL`. `NEON_DATABASE_URL` is legacy-only and must not be a
production fallback. Public product pages and their snapshot APIs do not import a DB
client. Schema changes live under explicit migration tooling, never request handlers.

## Documents

`pipeline.document_ledger` is the only production document-write owner. It writes the
immutable R2 object first and then records `documents.object_key`, hash, size, content
type, and contract version. `pipeline.drive` performs exact-key verified reads.
Rows without `object_key` are legacy compatibility data; they are reported as missing
rather than silently fetched through an alternate production owner.

## Lifecycle

The manual pipeline workflow invokes `pipeline/cron.py`; the VM/Admin compatibility
catalog invokes the lean pipeline and bounded repair jobs. Builders read canonical
facts offline and publish immutable KV versions plus active/previous pointers. Public
consumers read KV and therefore cannot wake Neon. See `docs/runbooks/PRODUCTION_JOBS.md`
for callers and side effects.

## Cloudflare bindings

`CACHE` and `JOB_FLAG` currently share namespace id
`71fc0e8060ce4cad919b58d35b9681e2`. This is retained intentionally pending an owner
change: snapshot keys use product prefixes (`ipo-`, `journey:` and pointer suffixes),
while the runner flag is `admin:jobs-pending`. No overlap was found. Sharing has low
collision risk but couples quota, access, and blast radius; a future split is an
operational hardening task, not a cleanup requirement. R2 credentials remain pipeline
only.
