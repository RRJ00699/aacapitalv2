# AACapital — Project Control Plan

**Status: CODE COMPLETE → OWNER CHECK.** Journey / dev-closeout cycle. The daily
pipeline remains **OWNER CHECK** (not VERIFIED DONE) until the owner's post-#333
Windows A1/A2 evidence is pasted — the 08-16 run was green but still carried
5/10 unresolved Kite tokens and a 1,025-document RHP backlog. See §0 for the
full status vocabulary.

> Repo-native control surface. Single source of truth for program state,
> two-agent ownership, seams, and the exact producer fields the UI is waiting
> on. Refresh from evidence each cycle — never from memory.

- **Current main:** `74eb38a` (merge of #333)
- **Last refreshed:** 2026-08-17
- **Refreshed by:** Claude (journey / dev-closeout cycle) — reconciled against the GitHub API and the owner's 08-16 run

---

## 0. Status vocabulary — keep these distinct

These three are **not** the same and must never be collapsed:

| State | Meaning |
| --- | --- |
| **CODE COMPLETE** | The change is written and merged. Typecheck/build/tests green in CI. Nothing about real-world correctness is claimed. |
| **OWNER CHECK** | Code is complete but a human owner must verify behaviour against reality (screenshots, a live run, a data spot-check). Falsely-green automation counts as *not yet verified*. |
| **VERIFIED DONE** | An owner has checked it against reality and signed off. Only this state closes a capability row. |

A daily pipeline that reports green while Kite/candle/TOP states are actually
stale is **OWNER CHECK**, not VERIFIED DONE — automation agreeing with itself is
not verification.

---

## 1. Program state (this refresh)

Reconciled 2026-08-17 against the GitHub API and the owner's 08-16 cron run —
**evidence, not memory**. Where the brief and the API disagree, the API wins and
the discrepancy is recorded rather than silently corrected.

### Merges / PRs (GitHub API, 2026-08-17)

| PR | Title (abbrev.) | Evidence | State |
| --- | --- | --- | --- |
| #327 | Windows-safe daily pipeline | `merged_at` 2026-08-12T02:23:06Z | **MERGED** |
| #330 | Lean-pipeline retirement / 15m / TOP | closed, `merged_at` null | **CLOSED — SUPERSEDED (never merged)** |
| #331 | Short-lived DB connections, recovery tests | `merged_at` 2026-08-13T01:25:01Z | **MERGED** |
| #332 | Schedule + ISIN fix + verdict-v2 + DB retry | `merged_at` 2026-08-13T02:03:16Z | **MERGED** |
| #333 | Honest owner-run outcomes (Kite/15m/TOP gating, SEBI summary, canonical universe) | `merged: true`, `merged_at` 2026-08-16T23:53:07Z, merged_by RRJ00699 | **MERGED** |
| #334 | UI foundation (theme, screen states, truthfulness, admin) | `merged_at` 2026-08-13T17:06:15Z | **MERGED** |
| #335 | Complete Details record screen | `merged_at` 2026-08-16T17:13:10Z | **MERGED** |
| #336 | NSE identity-backfill deadlines/timeouts (Codex) | open, created 2026-08-17T00:26:52Z | **OPEN — Codex** |

**Discrepancy recorded (do not paper over):** the closeout brief for this PR
described #333 as *open, awaiting two Codex fixes*. The API says it **merged**
at 2026-08-16T23:53:07Z and is in `main` (`74eb38a`). If two follow-up fixes
were intended, they are **not** tracked by #333 any more — a merged PR cannot
carry new work. They need their own issue/PR; #336 is the only Codex PR open
today and it is a different subject (NSE identity backfill).

- Do not resurrect #330's branch; any follow-up there is a fresh change.
- Claude does not touch the Codex pipeline PRs.

### Daily pipeline — owner cron run, 2026-08-16 (owner-reported)

| Signal | Value |
| --- | --- |
| Overall | run completed OK |
| Spend | **$0** |
| 15-minute bars | **2,044 inserted across 4 IPOs** (`market_candles_15m`) |
| TOP observations | **4 written** (`listing_observations`, `obs_type='level'`) |
| Hexagon | **TIER1_REJECTION**, invalidated by a later high — expected detector semantics, not a fault |
| Kite tokens | **5 of 10 unresolved** |
| RHP backlog | **1,025 pending** |

- **State: OWNER CHECK.** #333 landed the honesty fixes (Kite/15m/TOP gating,
  `STALE_INPUT` for stale detector input, SEBI partial summary), so a green run
  now means more than it did. It is still **not VERIFIED DONE**: the same run
  carries 5/10 unresolved Kite tokens and a 1,025-document RHP backlog, and no
  owner sign-off against reality is recorded yet.
- The 2,044 15-minute bars are real and in Postgres — and still **not in KV**,
  so no consumer can render them (backlog **B-3**).

### Workstreams
| Workstream | State | Note |
| --- | --- | --- |
| UI program | **PARTIAL** | Foundation (#334) + Complete Details (#335) merged; Listing Review / journey (LR1) lands this cycle. Remaining surfaces: Admin live-lane health (needs B-2) and anything gated on B-1/B-3. |
| Web-plane zero-wake | **PARTIAL** | `components/**` is DB-free and guarded. 14 `app/**` files still hold a DB client; each is allowlisted with its contract (§4c). |
| Migration | **IN PROGRESS** | Schema/data migration ongoing (Codex). |
| BOTTOM | **NOT STARTED** | Out of scope by design — the detector ships TOP only (`pipeline/topout_online.py`). |
| Anchor | **BLOCKED** | Waiting on the official forward-subscription payload; no UI consumption until the producer contract exists. |
| Rules producer | **BLOCKED** | Waiting on an owner decision on the quarantined `rule_validation_results` producer. |

---

## 2. Two-agent ownership

Two agents, one repo. Ownership is by path and by responsibility, not by
convenience. When in doubt, do not cross the line — record the need instead.

### Codex owns
- `pipeline/**`
- `_scripts/**`
- Database / schema writers (DDL, migrations, `requirements.txt`)
- Backend **Python** tests
- Backend producers that build payloads / run DB queries (e.g. `lib/v2/*` SQL fetchers)

### Claude owns
- `app/**`
- `components/**`
- Presentation-oriented `lib/**` (no DB access, no new queries)
- `docs/**`
- `.github/workflows/**` — **for UI/CI/UAT validation only**
- Frontend dependencies (`package.json` / `package-lock.json`) **only** when an evidenced frontend test dependency is required
- UI / TypeScript tests and UAT (`uat/**`)
- `app/globals.css` and theme / design-token files

### Hard "do nots" for the UI agent
- No backend producer changes.
- No new DB queries.
- No public `DATABASE_URL` fallback.
- No fabricated API fields. If a needed field does not exist, render an honest
  unavailable/pending state and record the exact requested field in §4 below.

---

## 3. Explicit seams

Some files sit on the boundary. They are called out so neither agent edits the
other's side by accident.

- **`pipeline/cron.py` — Codex-owned.** UI never edits it.
- **`pipeline/build/build_snapshots.ts` — Codex-owned.** It is TypeScript, but it
  is a **producer** (it writes the KV snapshots the UI reads). The UI consumes
  its output; it never edits the builder.
- **Payload changes require a small producer contract first.** Before the UI
  consumes a new field, Codex adds the field to the producer with a one-line
  contract (name, type, meaning). The UI then binds to it. No UI feature may
  assume a field that isn't in the shipped payload — it renders pending until
  the contract lands.

---

## 4. Payload fields the UI is waiting on (`payload_fields_unavailable`)

These are surfaced in the UI today as honest "Not available from current
payload" states (Admin Operations) or "pending" (Command Center). Each names the
exact producer field requested. **No number is fabricated in their place.**

### 4a. Producer contract to build next (Codex) — `pipeline-health:v1` (KV)

The Admin overview is **zero-wake**: it reads only KV, never Neon. Live pipeline
lane health therefore needs the pipeline to **publish run health to a KV
snapshot** (the same way `ipo-command:v6` is published) so the web app can read
it without a Neon query. The consumer is ready (`lib/admin/lane-status.ts`,
fully unit-tested); the producer is a **separate Codex task** — it must NOT be
built in this UI PR and must not modify `pipeline/build/build_snapshots.ts` here.

Proposed contract (Codex to confirm/adjust):

```
snapshot name: pipeline-health:v1  (KV, published by the pipeline like ipo-command:v6)
{
  run_complete: boolean,            // authoritative; else consumer infers from ran_at (15-min window)
  last_run_at:  string|null,        // ISO
  steps:    [{ step, ok, ran_at, duration_ms?, config_required?, error? }],
  expected: [{ step, weekly? }],    // = EXPECTED_LEAN_STEPS
  failures: [{ step, stderr_tail, failed_at }]
}
```

### 4b. Fields consumed as honest "unavailable" until a payload carries them

| Consumer surface | Requested field | Purpose |
| --- | --- | --- |
| Admin · Operations | `pipeline-health:v1` (KV) | Last run, per-lane status, first failing lane + traceback. Rendered as configuration-required until published. |
| Admin · Operations | `pipeline-health:v1: steps[].duration_ms` | Per-lane duration (no timing captured today) |
| Admin · Operations | `pipeline-health:v1: steps[].config_required` | Flag lanes that need configuration |
| Admin · Operations | `pipeline-health:v1: failures[].stderr_tail` | Failed-step traceback tail |
| Admin · Operations | `admin.owner_action_queue[]` | Owner-action queue |
| Admin · Operations | `rhp.retry_pending_count` | Retry / pending document count |
| Admin · Operations | `admin.paid_call_status{used,cap}` | Paid-call status/cap (no secret values) |
| Command Center | `strategy_backtest{cohort,win_rate,n,median}` | Validated cohort win-rates for the playbook. Until this ships, **no win-rate / "edge" percentage renders** — the UI shows qualitative setup descriptions only. |
| Command Center · Live | `rules_static[] / rules_live[] / rules_passed / rules_total` | Live rule evaluation. Rule counts render **only** when present in the payload. |
| Command Center · Anchor | official forward-subscription payload | Anchor workstream is BLOCKED until this producer contract exists. |

Contextual themes (market-session, verdict-driven, time-of-day) are **out of
scope** and remain an owner decision — not built in the theme v1.

### 4c. Deferred producer contracts (backlog — Codex owns, Claude consumes)

These are removals recorded as **deferred contracts, not silent deletions**: the
data returns to the UI the moment there is an evidenced producer behind it.

| # | Backlog item | Owner → Consumer | State |
| --- | --- | --- | --- |
| B-1 | **Codex producer: publish `strategy_backtest{cohort, win_rate, n, median}`** as a contracted, evidenced field so quantitative performance can return to the UI. Until then, `playbook_verdict` / `house_stack_stat` historical percentages must **not** render. UI (Claude) consumes `strategy_backtest` only after it ships. | Codex → Claude | NOT STARTED |
| B-2 | **Codex producer: publish `pipeline-health:v1`** (KV snapshot, §4a) so the Admin overview can show live per-lane health without a Neon web query. UI classifier (`lib/admin/lane-status.ts`) is ready and unit-tested. | Codex → Claude | NOT STARTED |
| B-3 | **Codex producer: publish intraday bars + per-bar volume to KV.** `market_candles_15m` now holds real 15-minute bars in Postgres (2,044 rows inserted on the 2026-08-16 run) and is what the top detector runs on, but **nothing publishes it to KV**. Separately, `journey:isin:<ISIN>:v1` *does* carry per-bar `open`/`volume`, and `computeJourney()` (`lib/v2/journey.ts:52`) drops both from `series` before the route answers — so the consumer can reach neither. Until a producer/domain change ships, Listing Review renders a **daily** price-only tape and says so. Claude consumes 15-minute bars and volume only once they are in the KV contract. | Codex → Claude | NOT STARTED |
| B-4 | **Codex producer: publish the listing-day cumulative-volume window to KV.** `/api/ipo/cum-volume` fills its own KV key from `ipo_tick_feed`, so the web plane still holds a DB client for it. A published `cumvol` snapshot makes the tile a pure consumer. Allowlisted in `lib/web-plane-db-contract.test.ts` until then. | Codex → Claude | NOT STARTED |
| B-5 | **Codex producer: publish the listing-day tick series to KV.** `/api/ipo/tick-feed` already serves the latest tick from KV; only the expanded chart's history reads `ipo_tick_feed`. A published series retires the last DB path on that route. | Codex → Claude | NOT STARTED |
| B-6 | **Codex producer: publish `market-india:v1` (KV)** — India snapshot (regime, breadth, PCR, deploy band), FII/DII flows and the after-hours global cache, so `/api/market/global` and `/api/market/snapshot` stop reading (and writing) Neon from the web plane. Yahoo + Zerodha already cover the live prices with no DB at all. **The `_scripts` query pins must move in the same change** (see below). | Codex → Claude | NOT STARTED |

**C2 zero-wake closeout — what actually blocked it (2026-08-17).** The web plane
still holds a DB client in 14 files. `components/**` is clean (zero, guarded with
no allowlist). Of the routes:

- **Writes / auth — no consumer form exists:** `access-note`, `admin/access`,
  `admin/jobs`, `admin/secrets`, `admin/diagnostics`, `auth/zerodha/callback`,
  `auth/zerodha/status`, `settings`. Converting these deletes working behaviour
  and replaces it with nothing.
- **Bounded, owner-approved zero-idle designs awaiting a producer:**
  `ipo/cum-volume` (B-4), `ipo/tick-feed` (B-5).
- **Blocked by Codex-owned test pins** — `_scripts/tests/test_route_runtime.py`
  asserts these routes DO query, so converting them fails CI unless the pins move
  in the same change, and `_scripts/**` is out of scope for a UI PR:
  `QUERY_CEILING`'s `assert q == ceiling or q > 0` pins `market/global` (5),
  `market/snapshot` (2), `settings` (2), `admin/pipeline-steps` (1) and
  `admin/pipeline-failures` (1); `test_A2_market_snapshot_second_call_zero_queries`
  additionally asserts the first `market/snapshot` call queries.

The boundary is now frozen by `lib/web-plane-db-contract.test.ts`: a **new** DB
import anywhere under `app/` or `components/` fails CI, every allowlisted file
names the contract that would free it, and the six KV-only snapshot routes may
never regain a DB client.

**B-1 producer render paths to clean (Codex-owned — NOT fixable in the UI PR).**
These emit the same uncontracted-backtest strings from the producer side and must
be gated on `strategy_backtest` when B-1 ships:

- `lib/v2/live-preopen.ts:99` — pre-open stack tile detail: "72.7% win, +17.2% med (D30, n=55)".
- `lib/v2/ipo-command.ts:173–174` — `playbook_verdict`: "…85% historically" / "…92% historically" (and the related `house_stack_stat` "72.7% win · +17.2% median" at `ipo-command.ts:184`).

The consumer side is already clean: the Command Center no longer renders these
strings (engine strip, score dial, and the house_stack tooltip were all removed),
and `uat/tests/command-center.spec.ts` fails on them — including an attribute/HTML
scan that catches a `house_stack_stat` tooltip regression. But the strings still
originate in the producer above; only Codex can stop them at the source.

Rationale: the "77%-edge"-class percentages were removed from the Command Center
this cycle because nothing evidenced backed them at the consumer. B-1 is the path
for those numbers to come back — owned by Codex (the producer), consumed by Claude
(the UI) only once the contract exists.

---

## 4d. Owner nine-point contract — refreshed 2026-08-17

The original checklist (PR #328) lives in
`docs/specifications/OWNER_9_POINT_CONTRACT.md` and stays as that PR's record.
This is the current state, reconciled against merged PRs, the owner's 08-16 run,
and what the UI can actually consume today.

| # | Point | Producer | Consumer | State | Blocker | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | IPO discovery (open / upcoming / current) + completeness retry | `nse_lifecycle.py`, completeness plan | Command Center (`ipo-command:v6`, `ipo:index:v3`) | **CODE COMPLETE → OWNER CHECK** | Identity-backfill timing/timeouts still in flight | Land #336 (Codex), then an owner run |
| 2 | RHP / SBI / official NSE forward anchor allocation | downloads + SBI ingest + NSE lifecycle | Complete Details | **BLOCKED (anchor)** · RHP lane running with a **1,025-document backlog** (08-16) | Official forward-allocation shape unproven; no aggregator may be scraped | Owner runs the NSE forward probe; drain the RHP backlog before completeness is claimed |
| 3 | R2 storage / ledger / SHA | `document_ledger.store_document` | Complete Details evidence | **CODE COMPLETE → OWNER CHECK** | Production handshake never observed by an owner | Owner attaches one real store + fetch round trip |
| 4 | Kite → daily / 15-minute / TOP levels | Kite refresh, daily candles, `kite_fetch_15m`, `topout_online` | Journey / Listing Review | **CODE COMPLETE → OWNER CHECK** — the 08-16 run inserted **2,044 15-minute bars across 4 IPOs** and wrote **4 TOP observations**, $0 spend | **5 of 10 Kite tokens unresolved**; the 15-minute bars are in Postgres but **not published to KV**, so no consumer can render them | Resolve the 5 tokens; ship **B-3** |
| 5 | Listing pre-open capture | `capture_preopen.py` | Command Center · Live | **CODE COMPLETE → OWNER CHECK** | Live overlay deliberately BLOCKED (Kite credential automation unproven) | Owner decision on credential automation |
| 6 | Complete Details record | snapshot builder → `ipo-details:isin:*:v1` | Complete Details (CD1, #335) | **CODE COMPLETE → OWNER CHECK** | Owner mobile UAT not signed off | Owner walks one populated and one pending ISIN |
| 7 | Junk filtering / decision engine | decision engine → `decisions` | Command Center verdicts | **CODE COMPLETE → OWNER CHECK** | Live verdict distribution never checked against production | Owner spot-checks the current distribution |
| 8 | Listing rules | quarantined `rule_validation_results` producer | none today | **BLOCKED** | Needs an **owner ruling** on whether the quarantined producer is adopted | Owner decides; until then no rules count renders anywhere |
| 9 | Journey TOP / watch state (no bottom, no entry interpretation) | `topout_online` → `listing_observations(level)` → `journey:isin:*:v1` | **Listing Review (LR1, this PR)** | **CODE COMPLETE → OWNER CHECK** | Consumer renders `state` / `watch_kind` / `fire_path` / `trigger` as DISCOVERY; the 15-minute tape behind it needs **B-3** | Owner checks one listed IPO with a fired TOP; `STALE_INPUT` (added by #333) renders as NOT EVALUATED |

**Hexagon, 08-16:** `TIER1_REJECTION`, invalidated by a later high. Recorded as
**expected detector semantics**, not a defect — the detector invalidates a watch
when a new high forms.

**Explicitly out of scope this cycle (recorded, not built):** Admin live-lane
health (needs **B-2**), a 15-minute tape (needs **B-3**), quantitative
performance statistics (needs **B-1**), and the listing-day rules count (needs
the owner's ruling on the quarantined `rule_validation_results` producer).

---

## 5. Capability rows

Advanced this cycle: **D1, D2, D3, D7, A3.**

| Row | Capability | State |
| --- | --- | --- |
| D1 | Theme system (system/light/dark, no hydration flash, semantic tokens) | CODE COMPLETE → OWNER CHECK (screenshots) |
| D2 | Shared screen states (loading/empty/pending/stale/config-required/failed+retry) | CODE COMPLETE → OWNER CHECK |
| D3 | Command Center simplification + truthfulness (no fabricated edge %, REIT/InvIT visibly excluded, three-verdict preserved) | CODE COMPLETE → OWNER CHECK |
| D7 | Mobile-first Command Center at 380px | CODE COMPLETE → OWNER CHECK (screenshots) |
| A3 | Admin Operations dashboard — **zero-wake** (KV-only, no Neon web polling); active-IPO + completeness from KV with UNKNOWN on degraded; lane health awaits the `pipeline-health:v1` producer | CODE COMPLETE → OWNER CHECK |
| LR1 | Listing Review / journey screen — per listed IPO: listing-day outcome (`listing_open`, `gap_pct`, `d1_close`, best/worst close, `ceiling_20` with its shipped non-executable label) rendered through the SAME `fieldDisplay` state renderer as Complete Details; a first-five-session **daily** price tape from the journey snapshot with one honest line about what KV does not carry; top-structure DISCOVERY observations mirroring the detector's own label; no win-rate/backtest percentage anywhere. KV-only consumer of two existing routes (`/api/ipo/journey` → ISIN → `/api/ipo/details/<ISIN>`). | CODE COMPLETE → OWNER CHECK (owner mobile UAT) |
| CD1 | Complete Details record screen — full `ipo-details-v1` record: identity/timeline, issue overview (+ derived market cap / lot value, labeled pro-forma), canonical financials & pro-forma (VERIFIED FACT vs DETERMINISTIC PRO-FORMA), valuation & fair value (house + canonical, no performance %), RHP & SBI verbatim evidence split by `source_type`, governance/risk, persisted decision, listing outcome, and a consolidated missing-data register. KV-only consumer; every leaf driven off `DetailField.state`; no `JSON.stringify`/`[object Object]` reaches the DOM. | CODE COMPLETE → OWNER CHECK (owner mobile UAT) |

All prior five (D1/D2/D3/D7/A3) plus **CD1** and **LR1** are **CODE COMPLETE** and
awaiting **OWNER CHECK** (UI screenshots + manual UAT). None is VERIFIED DONE until
the owner signs off.

### 5a. Complete Details (CD1) — build notes & flags

- **Scope honoured:** consumer-only. `pipeline_files_changed = 0`,
  `producer/schema_changes = 0`, no new API route, no SQL, no `DATABASE_URL`
  import, no payload fallback. Edits limited to
  `app/dashboard/ipo2/details/[isin]/page.tsx` (unchanged this cycle),
  `components/ipo/CompleteDetails.tsx`, new `lib/ui/details-format.ts`
  (+ unit tests), and new UAT `uat/tests/complete-details-populated.spec.ts`.
- **Violation fixed:** the previous `CompleteDetails.show()` did
  `JSON.stringify` on objects, leaking raw blobs for `ai_analysis.findings`,
  `decision.evidence`, and `inputs_used`. Replaced with a shared `ValueNode`
  renderer (arrays → lists, objects → labeled rows); a UAT test now fails if a
  serialized object reaches the record DOM.
- **§8 doctrine flag (display-only, NOT relabeled in the UI):** the current
  doctrine is *missing-financials → WATCH-pending, never JUNK*. `ipo-details-v1`
  passes through whatever `decisions.fundamental_verdict` was persisted and does
  **not** enforce this remap. The UI **displays the stored verdict verbatim**
  and must not relabel it. If a persisted `JUNK` verdict is actually a
  missing-financials case, that is a **producer/decision-writer** correction
  (Codex), not a UI change — recorded here rather than fabricated on screen.
- **Always-empty profile collections folded into the register (not shown as
  permanent empty cards):** promoters, business, objects, expenses,
  selling_shareholders, shareholding, reservation, anchor, subscriptions, peers,
  listing, market, economic_transformations, and the inert `sbi_analysis`
  (structured SBI stance is ABSENT; only verbatim SBI *excerpts* render, via
  `verified_evidence[].source_type === "SBI"`).
- **No performance percentages:** consistent with §4c/B-1 — the verdict band is a
  qualitative label only; no win-rate/edge/backtest % renders from any source.

### 5b. Listing Review (LR1) — build notes & flags

- **Scope honoured:** consumer-only. `pipeline_files_changed = 0`,
  `producer/schema_changes = 0`, no new API route, no SQL, no `DATABASE_URL`
  import, no `lib/v2` edit, no payload fallback. Edits limited to
  `components/ipo/ListingReview.tsx`, new `lib/ui/listing-review-format.ts`
  (+ unit tests), new UAT `uat/tests/listing-review-journey.spec.ts`, and this
  runbook. `app/dashboard/ipo2/page.tsx` is unchanged — the screen resolves its
  own identity, so the existing mount still works.
- **Violation fixed:** the previous `ListingReview` read `c.candles_json` off a
  command-snapshot row. That field appears in **no** TS/TSX payload — the golden
  object's `candles_json` is a DB column, never shipped in `ipo-command:v6` — so
  the tape and every observation were permanently dead. The screen is now a KV
  consumer of `journey:isin:<ISIN>:v1` (via `/api/ipo/journey`, which also
  resolves `sym → ISIN`) and `ipo-details:isin:<ISIN>:v1` (via
  `/api/ipo/details/<ISIN>`), which is where the data actually lives.
- **Shared state renderer, not a copy:** every listing-outcome leaf goes through
  `fieldDisplay` / `toValueNode` from `lib/ui/details-format.ts`. AVAILABLE
  renders the value; PENDING/MISSING renders the producer's own reason. Nothing
  reaches the DOM except via `ValueNode`, so `JSON.stringify` and
  `[object Object]` cannot leak (UAT asserts it on the rendered record).
- **Honest tape, limitation stated not worked around:** the tape is **daily**
  (`market_candles`, floored at `listing_date`), and `computeJourney().series`
  carries only `date/high/low/close`. Per-bar `open`/`volume` exist in the
  snapshot but are dropped at the route boundary, and 15-minute bars are not in
  KV at all. The screen says exactly that in one line and renders no volume
  column. Reaching either would require editing `lib/v2/journey.ts` — forbidden
  for this cycle and recorded as **B-3** (§4c) instead.
- **DISCOVERY labeling mirrors the producer:** `level_observation.payload`
  already stamps `"label":"DISCOVERY"` (`pipeline/topout_online.py:222`); the UI
  echoes that literal rather than inventing it, renders `state` /
  `watch_kind` / `fire_path` / `trigger` as labeled rows, and states that these
  are not executable signals. **"Top observations", never "top/bottom"** — the
  bottom mirror is deliberately out of production scope
  (`pipeline/topout_online.py:181`), and the screen says so.
- **No performance percentages:** `pool`, `winner_35` and
  `hold_positive_vs_open` ship in `listing_outcome` but are cohort /
  backtest-flavoured, so they are **excluded by name** from this screen (pinned
  by both the unit tests and the UAT spec). Consistent with §4c/B-1.
- **Honest-gap paths proven, not assumed:** the UAT spec drives a data-rich
  listed IPO (five sessions + computed outcome + a fired `TOP` observation) AND
  the empty/pending one (no candles, PENDING/MISSING outcome, no observation,
  and a 404 details snapshot), at desktop and 380px.

---

## 6. Guardrails honoured this cycle

**Journey / dev-closeout cycle (2026-08-17):** `pipeline_files_changed = 0`,
`scripts_files_changed = 0`, `lib/v2_files_changed = 0`, `schema_changes = 0`,
`.github_files_changed = 0`, new API routes = 0, new SQL = 0, `DATABASE_URL`
imports added = 0, producer fields invented = 0. Four commits: LR1 (journey
screen), the web-plane DB boundary guard, the dead-field sweep, and this
reconciliation. Nothing is marked VERIFIED.

- `pipeline_files_changed = 0`
- `scripts_files_changed = 0`
- `shared_seams_touched = NONE`
- `production_calls = 0`, `production_writes = 0`, `deployments = 0`
- No `DATABASE_URL` fallback added; no new DB query; no fabricated field.
- npm audit thresholds and advisory allowlist unchanged; Python install/execution unchanged; production pipeline schedules unchanged.
