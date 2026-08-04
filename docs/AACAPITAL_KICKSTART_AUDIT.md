# AACapital architecture kickstart audit

**Audit date:** 2026-08-04 UTC. **Scope:** repository evidence and the owner-supplied read-only coverage measurements for confirmed Neon branch `aacapitalpvtltd`. No database, KV, or production write was performed.

## Executive finding

The product has a substantial canonical V2 data layer and working screens, but the user-serving boundary is not structurally zero-wake. The shared cache explicitly builds from the database after a cold miss (`lib/kv-cache.ts:26-43`, `lib/kv-cache.ts:69-87`), CI conceals this coupling with a dummy database URL (`.github/workflows/ci.yml:17-20`), and several user routes directly import database clients. Authentication is functional and its password comparison is timing-hardened (`lib/credentials-auth.ts:8-52`), while pipeline automation is manual-only (`.github/workflows/pipeline.yml:3-25`) and has no step-run ledger integration.

The canonical identity requirement is only partially met: `ipo.isin` is present for 954/1,022 IPOs (93.3%). Several market routes accept symbols, which are aliases, and must resolve them only through a KV-published identity record; `buildIpoIndex` already publishes ISIN alongside symbol (`lib/v2/ipo-index.ts:5-13`).

## A. Current achievement

| Capability | Status | Achievement | Evidence and gap |
|---|---|---:|---|
| Identity spine | PARTIAL | 93% | 954/1,022 ISINs; symbol 911 and Kite token 528. Canonical index reads `ipo` but cold misses query Neon (`app/api/ipo/index/route.ts:11-17`). |
| RHP/document ingestion | PARTIAL | 37% | `rhp_findings` covers 375; `documents` only 4 IPOs. Cron downloads SEBI/SBI documents (`pipeline/cron.py:287-309`) and paid RHP extraction is capped. |
| Financial extraction | PARTIAL | 63% | 641 IPOs have financial statements. RHP writer and V2 fill own overlapping persistence responsibilities; no full coverage proof. |
| Subscription | PARTIAL | 98% issue rows | `ipo_issue` 1,018/1,022; issue price 999 and size 977, but lot size only 16. NSE fetch is the active incremental source. |
| Valuation | PARTIAL | 78% | 800 IPOs represented; 1,284 score rows, but zero populated fair-value rows. Multiple engine versions require latest-version selection. |
| Company verdict | PARTIAL | 78% | Decisions cover 800 IPOs; RHP evidence covers only 375. Missing research must not imply GOOD. |
| Command Center | PARTIAL | 75% | UI consumes `/api/ipo-command` (`app/dashboard/ipo2/page.tsx:943`); route joins canonical V2 tables but cold cache falls back to DB (`app/api/ipo-command/route.ts:31-51`). |
| Complete Details | PARTIAL | 55% | Command page exposes research/detail panels, but sparse documents, financials, lot size, insights (5 IPOs), and no fair values prevent completeness. |
| IPO Live | BLOCKED | 35% | Pre-open/live routes exist, but `listing_observations.buy_qty` and `sell_qty` are entirely empty. Candle volume cannot substitute for order quantity. |
| Journey/top-bottom | PARTIAL | 46% | Daily candles cover 474 IPOs; 15-minute candles cover 100. Journey reads Neon history on KV miss (`app/api/ipo/journey/route.ts:14-46`). |
| KV serving | PARTIAL | 40% | Warm/stale helpers exist, but total miss executes `build()` and writes mutable keys (`lib/kv-cache.ts:26-43`, `lib/kv-cache.ts:69-87`). |
| Authentication | COMPLETE with P1 gaps | 85% | Credentials remain alongside Google; bcrypt uses a 12-round dummy hash and fails closed (`lib/credentials-auth.ts:8-52`). API guards exist. Rate limiting is not applied to login and its generic helper fails open (`lib/security/ratelimit.ts:23-64`). |
| Pipeline automation | PARTIAL | 60% | One active `cron.py`, active-window limit 10, cap, isolated stages; GitHub workflow is manual-only and uploads artifacts every run (`.github/workflows/pipeline.yml:9-25`, `:91-100`). |
| Security | PARTIAL | 65% | Admin routes gate users/admins; secrets remain environment-backed. Some settings/access routes write/DDL during requests, and broker audit wakes Neon. |
| Observability | ABSENT | 10% | Supplied fact: `pipeline_step_runs` has 0 rows. Cron returns per-process states but does not persist a run ledger. Existing admin endpoints query different `pipeline_steps`/`pipeline_failures` tables. |
| Deployment | PARTIAL | 70% | OpenNext/Workers configuration and manual deploy workflow exist. CI currently builds with a dummy DB URL, so zero-DB build is not enforced. |

The three decision layers remain contractually separate for this phase: **company quality** (GOOD/WATCH/JUNK), **trade setup** (ATTRACTIVE/NEUTRAL/AVOID), and **live action** (BUY_NOW/WAIT/SKIP/EXIT_CAUTION/EXIT_CONFIRMED). A JUNK record must never receive BUY_NOW; absent source data is unavailable, not a synthetic substitute.

## B. Route data map (pre-change)

Query counts are static estimates per cache miss based on visible SQL calls; external requests are stated separately. “UI caller” includes direct pages and operational clients.

| Route | UI caller | Source / KV key / TTL | Miss and stale behavior | Est. work | Class |
|---|---|---|---|---:|---|
| `/api/ipo-command` | `dashboard/ipo2` | ipo, ipo_issue, subscription_snapshots, valuation, decisions, listing_outcomes, rhp_findings, source_facts, insights, market_candles; `ipo-command:v5`, 12h + 7d stale | primary → stale → **Neon build** | ~4 compound SQL | USER_DB_WAKE_RISK |
| `/api/ipo/index` | `dashboard/ipo2` search | ipo; `ipo:index:v2`, 6h | hit → **Neon build**; no stale | 1 | USER_DB_WAKE_RISK |
| `/api/ipo/journey` | journey and ipo2 | ipo + market_candles; `journey:v2:{symbol}:{IST-day}`, effectively daily | miss queries Neon; optional internal broker quote | 2 + 1 external | USER_DB_WAKE_RISK |
| `/api/ipo/live-preopen` | ipo2 | ipo/issue/subscription/valuation/decision + broker pre-open; `ipo:preopen:v4`, 60s | bypass in IST window; DB research plus live broker | several + broker | USER_DB_WAKE_RISK |
| `/api/ipo/cum-volume` | ipo2 | listing observations/candles and broker; symbol KV key, conditional TTL | KV miss queries DB and/or external | 1-2 | USER_DB_WAKE_RISK |
| `/api/ipo/tick-feed` | ipo2 (`live=1`) | live KV; history from tick table | `live=1` miss returns empty; default miss queries Neon | 1 | USER_DB_WAKE_RISK (historical); KV_ONLY (`live=1`) |
| `/api/market/global` | no direct TSX caller found | Yahoo + broker + canonical market data; shared cache, 5m | helper miss builds and includes Neon | multiple external + DB | USER_DB_WAKE_RISK |
| `/api/market/snapshot` | no direct TSX caller found | Yahoo indices + DB portfolio/market facts; `market:snapshot:v2` | miss queries Neon and Yahoo | ~2 + 3 external | USER_DB_WAKE_RISK |
| `/api/broker/quote` | journey route | Zerodha server-side; short live KV | miss calls broker; does not expose reusable token | 1 external | LIVE_EXTERNAL |
| `/api/broker/status` | no direct TSX caller found | broker server-side | direct external status | 1 external | LIVE_EXTERNAL |
| `/api/ipo/monitor` | no direct TSX caller found | repository historical constant | no KV/DB | 0 | DEAD_ROUTE pending caller proof |
| `/api/health` | operations | process/config presence | no KV/DB | 0 | KV_ONLY |
| `/api/access-note` | login | access_requests + optional ntfy | direct unauthenticated write | 1-2 DB + external | AUTH_DB_ALLOWED (P1 abuse risk) |
| `/api/auth/[...nextauth]` | login/session | allowed_users/access_requests/platform_config | auth-required DB access | 1-3 | AUTH_DB_ALLOWED |
| `/api/auth/zerodha*` | settings/operator | kite_session + broker OAuth | DB token storage; server-only secret exchange | 1-2 | ADMIN_DB_ALLOWED (admin gate review required) |
| `/api/admin/access` | dashboard/access | allowed_users/access_requests | authenticated admin DB read/write | 1-2 | ADMIN_DB_ALLOWED |
| `/api/admin/{jobs,diagnostics,pipeline-failures,pipeline-steps,secrets}` | admin/settings | operational tables/config | authenticated admin DB access | 1-3 | ADMIN_DB_ALLOWED |
| `/api/admin/{job-flag,kv-put}` | VM/pipeline machine caller | KV only | controlled KV error | 0 | ADMIN_DB_ALLOWED |
| `/api/admin/check` | admin UI | session/admin env | no product DB | 0 | ADMIN_DB_ALLOWED |
| `/api/pipeline/trigger` | admin | GitHub workflow API | authenticated external trigger | 1 external | ADMIN_DB_ALLOWED |
| `/api/settings` | no active caller (UI uses admin/secrets) | platform_config | direct DB reads/writes, no visible guard | 1 | DEAD_ROUTE / security review |
| `/api/tracker` | tracker admin page | management commentary table | admin-gated DB CRUD | 1 | ADMIN_DB_ALLOWED |

No route may be reclassified LIVE_EXTERNAL merely to preserve research/history DB reads. Static identity/research belongs in KV; broker calls stay server-side; history needs a separately reviewed endpoint/snapshot.

## C. Pipeline writer map

`pipeline/cron.py` is the sole production orchestrator (`pipeline/cron.py:1-19`). Its normal scope is mainboard, issue-size ≥150 crore, upcoming/recent (90-day) IPOs with default limit 10 (`pipeline/cron.py:57-105`, `:256-283`). Runtime ranges are operational estimates, not measured in this audit.

| Active step / entry | Source → destination | Identity | Dry-run / idempotency | Cost / normal runtime / tests | Duplicate |
|---|---|---|---|---|---|
| `refresh_kite_token.py` | Zerodha auth → platform config/session | account | Cron skips execution in dry-run; overwrite/upsert | free; <5m; script-level checks | other token update scripts under `_scripts`, operational only |
| `download_sebi_rhps_playwright.py` | SEBI → local/R2 documents | ISIN mapping required | cron dry-run does not execute; content address | free; 5-20m; downloader tests limited | `rhp_link.py` / map builder complement, not writer replacement |
| `download_sbi_notes.py` | SBI → retained notes/R2 | mapped IPO/ISIN | cron dry-run does not execute; file existence/hash | free; 5-10m | old regex parser is retired/research-only |
| `nse_fetch.py` | NSE issue/subscription → `ipo_issue`, `subscription_snapshots` | IPO selected from ISIN-backed canonical row; symbol is source alias | explicit `--dry-run`/`--write`; conflict keys and latest capture | free; 1-10m for ≤10; tests present | older fill scripts overlap persistence |
| `drive.py --rhp` / `rhp_sonnet.py` | RHP/SBI documents + Anthropic → `documents`, `rhp_findings`, financial facts, insights | ISIN/ipo_id | explicit dry-run and paid cap; hash/prompt version | **paid**, bounded by remaining daily cap; up to 30m; selftests | `rhp_writer.py`, `fill_v2.py` overlap writers |
| `kite_fetch.py` | Zerodha candles → `market_candles`, `market_candles_15m`, listing outcomes/observations | canonical ipo_id resolved to Kite token; symbol alias | `--dry-run`/`--write`; `(ipo_id,date/ts)` conflicts | broker/free plan; 1-15m; documented dry-run | historical scripts under `_scripts` overlap research/backfill |
| score engine | financial/source facts → `valuation` | ipo_id (must originate from ISIN) | cron dry-run skips; engine-version idempotency | free; <5m; score tests | scoring also invoked within drive and standalone |
| verdict engine | valuation/RHP/subscription → `decisions` | ipo_id | cron dry-run skips; version/latest semantics | free; <5m; selftests | drive orchestration plus standalone engine |
| completeness/notify | canonical tables → report/ntfy | ipo_id | read-only except notification | free; <5m; completeness tests | diagnostics endpoints overlap reporting |
| document cleanup | filesystem/R2 objects | ipo_id/document URL | dry-run supported | free; variable | **disabled by default and forbidden for this phase**; current proof gate is insufficient after incident |

Writer hardening requirement: every active writer must report unresolved ISINs, support explicit apply plus small limit, and persist no ledger event in dry-run. Duplicate writers remain untouched until caller, row-count, and replacement coverage proof exists.

## D. Donor ledger

| Classification | Code | Reason |
|---|---|---|
| KEEP_AS_IS | `pipeline/cron.py` orchestration and active-window selector; credentials bcrypt verifier; broker server-side token exchange | Proven active responsibility; preserve behavior. |
| KEEP_AND_HARDEN | `lib/kv-cache.ts`, eight audited user routes, `pipeline/cron.py`, auth/admin gates, CI | Remove cold DB fallback, add version/pointers and ledger, enforce import boundary. |
| MERGE_DUPLICATES | V2 persistence spread across `fill_v2.py`, `rhp_writer.py`, score/verdict invocation in drive and standalone scripts; token refresh/update helpers | Identify one active owner later; do not delete now. |
| RESEARCH_ONLY | historical/backfill scripts, `ipomatrix_fallback.py`, old SBI regex parser, `_archive/**` | Not part of normal incremental collection. Historical/paid sweeps prohibited. |
| DEAD_PENDING_PROOF | `/api/ipo/monitor`, `/api/settings`, unused market callers, legacy fill/verify scripts | No active UI caller found, but deletion requires runtime telemetry, reference search, current reader/writer, row count, and replacement coverage. |

## E. Data sufficiency matrix

| Product | Required fields | Current source / measured coverage | Assessment | Next required capture |
|---|---|---|---|---|
| Command Center | ISIN/name/dates/issue terms, subscription, valuation, company verdict, outcome | ipo 1,022; ISIN 954; issue 1,018; price 999; size 977; subscription present but unmeasured; valuation/decision 800; outcomes not supplied | Usable now for covered IPOs; incomplete identity, lot (16), valuation/verdict; no fair value | resolve missing ISIN first; issue lot source; validated fair-value engine; publish completeness/provenance |
| Complete Details | above + page-cited documents, financial series, governance findings, insights | financials 641; RHP findings 375; documents 4; insights 5 | Structurally blocked for provenance-rich details at scale | preserve raw artifact and page citations; validate extraction before scoring |
| IPO Live | canonical identity, issue price, live IEP/order book, bid/ask quantities, live ticks/action | listing observations 340/123,078; buy_qty and sell_qty 0; 15m candles 100/386,057 | Static context usable; manipulation/action evidence structurally blocked | forward capture real NSE pre-open/IEP/order-book fields; never substitute candle/subscription volume |
| Journey | identity, issue/listing values, daily and 15m history, live external quote | daily 474; 15m 100; listing observations 340 | Usable for covered history; incomplete universe; user route currently DB-coupled | publish per-ISIN history snapshots or approved history service; capture only active IPOs incrementally |

## F. Blockers

* **Code:** mutable cache/build-on-miss; direct DB imports in user routes; combined static/live/history handlers; no structural import test; ledger absent from cron.
* **Data:** 68 missing ISINs; financials 381 IPOs short; findings 647 short; documents and insights nearly absent; lot size only 16; fair-value population zero.
* **Source:** real pre-open order-book buy/sell quantities have not been captured; IPOMatrix source/table is gone; runner-side SEBI download reliability is unproven.
* **Validation:** no forward validation for IPO Live manipulation/action; duplicate writers lack owner/coverage proof; source freshness and schema validation absent from snapshots.
* **Cost:** RHP extraction is paid and bounded by $2/day default; no paid work is required or authorized in this phase.
* **Operational:** pipeline workflow is manual-only; no `pipeline_step_runs` evidence; artifact upload on every run consumes resources; production snapshot publisher/binding behavior is not verified here. Cloudflare connected-resource state was not available through an enabled repository-specific integration, so **I cannot verify this yet.**

## G. Immediate actions

### P0

1. Replace cold build fallback for pipeline-derived routes with primary → stale → controlled 503 and enforce the no-DB import boundary in CI.
2. Publish immutable, checksummed Command Center and identity index snapshots with active/previous pointers and read-back verification.
3. Add a tested cron step ledger adapter using the real `pipeline_step_runs` schema if compatible; otherwise document the smallest additive migration without applying it.
4. Record the 2026-08 loss incident and impose a permanent no-destructive-cleanup proof gate.

### P1

1. Split Journey and IPO Live into KV static context, server-side live external calls, and independently reviewed historical snapshots.
2. Resolve the 68 missing ISINs before further alias enrichment; capture true pre-open book quantities forward.
3. Add a low-frequency schedule proposal (not activation), active IPOs only, default limit 3, concurrency lock, cap preservation, and failure-only/no artifacts.
4. Harden authentication rate limiting/audit logging without replacing credentials auth; separately review unauthenticated access-note and Zerodha admin gating.

### P2

1. Prove one owner for each duplicate writer and retire only after lineage/replacement evidence.
2. Expand safe snapshot publication only after the two initial snapshots operate successfully.
3. Validate fair-value methodology and document/RHP provenance before filling Complete Details.

## Schema evidence limitation and migration posture

The repository contains `pipeline_steps` and `pipeline_failures` DDL references, but no checked-in definition for the owner-reported `pipeline_step_runs` table. The supplied row count is zero, but a live read-only `\d+`/information-schema result was not available through the enabled tools. Therefore **I cannot verify the live column definition yet.** Implementation must use a schema-tolerant adapter and include, but not apply, a minimal additive migration proposal for the desired fields.

## Pipeline schedule proposal (not activated)

Keep `workflow_dispatch`. After owner approval only, add a single weekday schedule after Indian market EOD (for example `13:30 UTC`, explicitly **19:00 IST** and **08:30 CST / 09:30 CDT** depending on daylight saving), default `--limit 3`, no `--backfill`, active selector only, existing `aacapital-pipeline` concurrency group, existing DB-backed daily spend cap, `--skip-download` until runner scraping is proven, and artifact upload only on failure. Expected normal scope: ≤3 IPOs, ≤30 minutes, ≤the configured daily paid cap, and only idempotent incremental rows.

## Implemented after-map

The audit above preserves the verified pre-change state. The P0 implementation subsequently made all eight named routes structurally zero-wake: Command and identity use versioned active/previous snapshots with legacy strict-stale compatibility; Journey, cumulative volume, tick history, live-preopen, global market, and market snapshot use read-only KV contracts and return controlled 503 responses on total misses. None imports a database client. Genuine broker quotes remain isolated at `/api/broker/quote`; historical/live capture publication remains pipeline/admin work rather than a user-request fallback.

| Route | After classification | Total-miss behavior | DB queries |
|---|---|---|---:|
| `/api/ipo-command` | KV_ONLY | 503 `snapshot_unavailable` | 0 |
| `/api/ipo/index` | KV_ONLY | 503 `snapshot_unavailable` | 0 |
| `/api/ipo/journey` | KV_ONLY static/history + separately called LIVE_EXTERNAL quote | 503 `historical_snapshot_unavailable` | 0 |
| `/api/ipo/live-preopen` | KV_ONLY until a dedicated server-side live feed is separately validated | 503 `live_snapshot_unavailable` | 0 |
| `/api/ipo/cum-volume` | KV_ONLY | 503 `volume_snapshot_unavailable` | 0 |
| `/api/ipo/tick-feed` | KV_ONLY | live mode returns controlled empty; history returns 503 | 0 |
| `/api/market/global` | KV_ONLY | 503 `snapshot_unavailable` | 0 |
| `/api/market/snapshot` | KV_ONLY | 503 `snapshot_unavailable` | 0 |
