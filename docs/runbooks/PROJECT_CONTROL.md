# AACapital — Project Control Plan

**Status: CODE COMPLETE → OWNER CHECK.** Consumer-honesty cycle. The daily
pipeline remains **OWNER CHECK** (not VERIFIED DONE): #340 landed the D1–D7
defect closeout but its own acceptance is an owner Windows A1/A2 rerun that has
not been pasted, and the 08-16 run still carried 5/10 unresolved Kite tokens and
a 1,025-document RHP backlog. The SBI lane's owner pilot (08-19) ran two
documents and dropped 9 of 10 claims on the very ceiling D7 removes, so the full
~193-document run is **pending a clean re-pilot**. See §0 for the full status
vocabulary. **Nothing in this refresh is marked VERIFIED.**

> Repo-native control surface. Single source of truth for program state,
> two-agent ownership, seams, and the exact producer fields the UI is waiting
> on. Refresh from evidence each cycle — never from memory.

- **Current main:** `8b05a27` (merge of #340)
- **Last refreshed:** 2026-08-19
- **Refreshed by:** Claude (consumer-honesty cycle) — reconciled against the GitHub API, the repository at `8b05a27`, and the owner's 08-16 cron run + 08-19 SBI pilot

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

Reconciled 2026-08-19 against the GitHub API, the repository at `8b05a27`, and
the owner's 08-16 cron run and 08-19 SBI pilot — **evidence, not memory**. Where
a brief and the API disagree, the API wins and the discrepancy is recorded
rather than silently corrected.

### Merges / PRs (GitHub API, 2026-08-19)

| PR | Title (abbrev.) | Evidence | State |
| --- | --- | --- | --- |
| #330 | Lean-pipeline retirement / 15m / TOP | closed, `merged_at` null | **CLOSED — SUPERSEDED (never merged)** |
| #333 | Honest owner-run outcomes (Kite/15m/TOP gating, SEBI summary, canonical universe) | `merged_at` 2026-08-16T23:53:07Z | **MERGED** |
| #334 | UI foundation (theme, screen states, truthfulness, admin) | `merged_at` 2026-08-13T17:06:15Z | **MERGED** |
| #335 | Complete Details record screen | `merged_at` 2026-08-16T17:13:10Z | **MERGED** |
| #336 | NSE identity-backfill deadlines / timeouts / pluggable prime (Codex) | `merged: true`, `merged_at` 2026-08-19T00:18:48Z, merged_by RRJ00699 | **MERGED** |
| #338 | Consolidated cleanup — artifacts, VM installer retirement, quarantine audit, docs | `merged_at` 2026-08-19T00:19:19Z | **MERGED** |
| #339 | Pipeline & KV producer closeout — Cube InvIT repair, NSE 403, bounded producer snapshots (Codex) | open, `mergeable_state: dirty`, head `6a3e98d`, base `25f352a`, updated 2026-08-19T02:10:02Z | **OPEN — Codex, REBASING** (its base predates #340) |
| #340 | Pipeline defect closeout — D1–D7 | `merged: true`, `merged_at` 2026-08-19T02:09:20Z, merged_by RRJ00699, 23 files, +1753/−83 | **MERGED** |

**#340, what actually landed** (per-commit, all seven gate-green before merge):

| Commit | Defect | What it closed |
| --- | --- | --- |
| `21abfde` | D1 | REIT/InvIT excluded from the canonical universe on a **structured** `source_facts.security_kind` fact derived from NSE's own `series` code — never on a name regex. An unrecognised series classifies nothing. |
| `f6222ae` | D2 | Kite token written with `UPDATE ipo SET kite_token=COALESCE(...) WHERE id=%s` — by id, so the token can no longer land on a duplicate spine row. |
| `97f53a9` | D3 | `completeness_pct` scored on what is **DUE** (`present / (present + missing)`), pending held out and reported as `required_pending`, so a stage advance cannot regress the score. |
| `7825343` | D4 | `refresh_kite_token.py` no longer reads `.env` under `KITE_REFRESH_TEST_MODE` — the test suite had been attempting a real Cloudflare rotation and a live broker verification. |
| `df56a2c` | D5 | The snapshot step's exit code reflects publication reality: UTF-8 `errors="replace"` decode on both hops, embedded-object JSON parse, and a ledger that records phase + snapshots actually published. |
| `bc62185` | D6 | **A V2 rule-validation producer** (`pipeline/rule_validation.py`, `ENGINE_VERSION = "v2-rules-1"`): one row per declared rule, `NOT_EVALUABLE` with the absent input named instead of silence, `CANONICAL` deliberately empty, every mined rule labelled `DISCOVERY`. |
| `d045a0c` | D7 | Resolved SBI excerpts are no longer held to a 15-word paraphrase budget (1200-char cap instead); `PROMPT_VERSION` `sbi-v1.5`, with `sbi-v1.4` kept in the completion identities so nothing is re-extracted or re-paid for. |

**#340 is MERGED but not VERIFIED.** Its own PR body states owner acceptance is
a Windows A1/A2 rerun, listing four checks (no InvIT in any TOP/candle line;
CSM 493 carrying `kite_token=195520769` with no second row on its `name_norm`;
a non-regressing `before=…% after=…%` completeness line; snapshot step exit 0).
None of those four is recorded here yet.

**#339 is open and conflicted.** Its base is `25f352a`, which predates #340, and
`mergeable_state` is `dirty`; it also edits `pipeline/build/build_snapshots.ts`,
which #340 did not touch but which #339 rewrites substantially. It is **Codex's
to rebase** — Claude does not touch the Codex pipeline PRs. Its proposed
payloads matter to this runbook because they would answer B-2/B-3/B-4/B-5/B-6
(see §4c) — but an open, conflicted PR is evidence of intent, not of shipment,
so those rows stay NOT STARTED.

**Prior-cycle discrepancy, kept on the record:** the 2026-08-17 closeout brief
described #333 as *open, awaiting two Codex fixes*; the API showed it merged at
2026-08-16T23:53:07Z. A merged PR cannot carry new work. Those fixes landed
instead as #336 and #340.

- Do not resurrect #330's branch; any follow-up there is a fresh change.
- Claude does not touch the Codex pipeline PRs (#339 today).

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
  `STALE_INPUT` for stale detector input, SEBI partial summary) and #340 landed
  D1–D7, so a green run now means more than it did. It is still **not VERIFIED
  DONE**: this run predates #340, carries 5/10 unresolved Kite tokens and a
  1,025-document RHP backlog, and no owner sign-off against reality is recorded.
- The 2,044 15-minute bars are real and in Postgres — and still **not in KV**,
  so no consumer can render them (backlog **B-3**).
- **No post-#340 cron run is recorded.** The four acceptance checks in #340's
  body are the next evidence this table needs.

### SBI lane — owner pilot, 2026-08-19 (owner-reported)

| Signal | Value |
| --- | --- |
| Scope | **2 documents** (pilot, not the full run) |
| Spend | **$0.083** |
| Outcome | 1 × `EVIDENCE_REJECTED`, 1 × `EXTRACTED_WITH_DROPS` |
| Drops on the second | **9 of 10 claims**, every one "excerpt exceeds 15 words" |
| Worker record | `worker-20260819-004022.json` |

- That is the defect **D7 fixes** (`d045a0c`, merged in #340): the 15-word
  ceiling was written to stop the model paraphrasing, but it was also being
  applied to excerpts Python had lifted byte-true from the page after resolving
  up to three source-line refs. Three joined lines of a research note routinely
  exceed fifteen words, so the ceiling was rejecting honest evidence for being
  honest. Resolved excerpts now face a 1200-character size cap instead, and the
  word ceiling is **kept** on the model-authored `parse_extraction` path.
- **The full ~193-document run is NOT started and must not be.** The pilot's
  result is pre-fix. The next step is a **clean re-pilot on `sbi-v1.5`** —
  a fresh small batch, its drop reasons read, and only then the full run.
  Documents already extracted under `sbi-v1.4` stay complete and are not
  re-extracted or re-paid for.
- **State: OWNER CHECK.** No post-D7 pilot output is recorded here.

### Workstreams
| Workstream | State | Note |
| --- | --- | --- |
| UI program | **PARTIAL** | Foundation (#334) + Complete Details (#335) merged; Listing Review / journey (LR1) and the pending-vs-missing honesty pass (CH1) are CODE COMPLETE awaiting owner check. Remaining surfaces: Admin live-lane health (needs B-2), the rules card (needs **B-7**), and anything gated on B-1/B-3. |
| Web-plane zero-wake | **PARTIAL** | `components/**` is DB-free and guarded. 14 `app/**` files still hold a DB client; each is allowlisted with its contract (§4c). |
| Migration | **IN PROGRESS** | Schema/data migration ongoing (Codex). |
| BOTTOM | **NOT STARTED** | Out of scope by design — the detector ships TOP only (`pipeline/topout_online.py`). |
| Anchor | **BLOCKED** | Waiting on the official forward-subscription payload; no UI consumption until the producer contract exists. |
| Rules producer | **CODE COMPLETE (producer) → BLOCKED (consumer)** | #340 (`bc62185`) shipped the V2 producer `pipeline/rule_validation.py`; the V1 `compatibility/scripts/rule_validation.py` stays quarantined. The rows land in Postgres only — **no KV snapshot carries them**, so no consumer can read them (backlog **B-7**). Writes are additionally owner-gated on `RULE_VALIDATION_OWNER_APPROVED=1`. |

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
| Listing · Rules card | `ipo-rules:isin:<ISIN>:v1` (KV) — see **B-7** | Per-rule `PASS` / `FAIL` / `NOT_EVALUABLE` with the missing input named, in two layers. The V2 producer exists (#340); no snapshot carries its rows, so **no rules card and no rule count renders anywhere** today. |
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
| B-7 | **Codex producer: publish the rule-validation rows to KV** — contract point 8. #340 (`bc62185`) shipped `pipeline/rule_validation.py`, which writes one row per declared rule to `rule_validation_results` with `PASS` / `FAIL` / `NOT_EVALUABLE` and names the absent inputs. **Nothing publishes those rows to KV**, so the Listing screen's rules card cannot be built (see the stop record below). Claude consumes the rules card only once the snapshot exists. | Codex → Claude | NOT STARTED |

**Rules card (contract point 8) — STOPPED BEFORE BUILDING, 2026-08-19.**

The plan for this cycle included a two-layer rules card on the Listing screen.
It was **not built**, and the reason is a repository fact, not a preference:

- The V2 producer exists and is merged — `pipeline/rule_validation.py`
  (`ENGINE_VERSION = "v2-rules-1"`), writing to `rule_validation_results`.
- **No KV snapshot carries a rule row.** `pipeline/build/build_snapshots.ts`
  publishes exactly five payload families — `ipo-command:v6`, `ipo:index:v3`,
  `ipo-live-preopen:v2`, `journey:isin:<ISIN>:v1` and
  `ipo-details:isin:<ISIN>:v1` — and none of them reads `rule_validation_results`
  (grep for the table across `lib/`, `app/`, `components/` and
  `pipeline/build/` returns nothing). #339 adds five more payload families and
  **still adds no rule payload**.
- The only paths to the data from the web plane would be a new API route or a
  SQL query. Both are forbidden to a UI cycle, and inventing either would put a
  DB client back into a zero-wake surface.

So the card is deferred as **B-7** with the contract stated below, and the UI
ships nothing that implies a rule was evaluated.

**B-7 producer contract requested (Codex to confirm/adjust).** Shape it like the
existing per-ISIN details snapshot so the Listing screen can read it with the
consumer it already has:

```
snapshot name: ipo-rules:isin:<ISIN>:v1   (KV, published like ipo-details:isin:*:v1)
{
  schema_version: "ipo-rules-v1",
  engine_version: string,               // rule_validation_results.engine_version, e.g. "v2-rules-1"
  evaluated_at:   string|null,          // run_at, ISO
  dataset:        string,               // the cohort sentence the producer already stores
  layers: {
    CANONICAL: [ Rule ],                // MAY BE EMPTY — the honest state today
    DISCOVERY: [ Rule ]                 // every entry rendered with a DISCOVERY label
  }
}

Rule = {
  rule_id:        string,               // e.g. "qib_15x"
  rule_version:   string,               // e.g. "v2-1"
  layer:          "CANONICAL" | "DISCOVERY",
  rule_filter:    string,               // the human-readable predicate, verbatim
  status:         "PASS" | "FAIL" | "NOT_EVALUABLE",
  status_detail:  string|null,          // why, in the producer's own words
  missing_inputs: string[],             // NAMED inputs, empty unless NOT_EVALUABLE
  inputs_used:    object|null           // declared inputs + coverage, as already stored
}
```

Three constraints on that contract, and they are not negotiable from the
consumer side:

1. **Omit `win_rate`, `avg_return`, `median_return`, `expectancy`,
   `max_drawdown`, `p_vs_baseline`, `beats_baseline` and `baseline_win_rate`.**
   They exist on the table but are performance statistics; §4c/B-1 and the #334
   percentage regression forbid rendering them, and the cleanest guarantee is
   that they never reach a payload the UI can read. `status` already carries
   everything the card shows.
2. **Every declared rule ships a row, including `NOT_EVALUABLE` ones.** A rule
   omitted from the payload is indistinguishable from a rule nobody wrote — the
   exact failure mode the producer was built to end.
3. **`CANONICAL` may be an empty array and the consumer will render an honest
   empty state for it** — "no house rule has been ratified against V2 evidence
   yet" — never a zero, never a count, never a silent omission of the layer.

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

## 4d. Owner nine-point contract — refreshed 2026-08-19

The original checklist (PR #328) lives in
`docs/specifications/OWNER_9_POINT_CONTRACT.md` and stays as that PR's record.
This is the current state, reconciled against merged PRs (through #340), the
owner's 08-16 cron run and 08-19 SBI pilot, and what the UI can actually consume
today. No row is VERIFIED: every one of them is waiting on owner evidence.

| # | Point | Producer | Consumer | State | Blocker | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | IPO discovery (open / upcoming / current) + completeness retry | `nse_lifecycle.py`, completeness plan | Command Center (`ipo-command:v6`, `ipo:index:v3`) | **CODE COMPLETE → OWNER CHECK** | #336 (backfill deadlines/timeouts) and #340 D3 (completeness scored on what is DUE) are both merged; no post-#340 owner run is recorded | Owner runs the cron and pastes the `before=…% after=…%` completeness line |
| 2 | RHP / SBI / official NSE forward anchor allocation | downloads + SBI ingest + NSE lifecycle | Complete Details | **BLOCKED (anchor)** · RHP lane at a **1,025-document backlog** (08-16) · SBI lane **OWNER CHECK**: the 08-19 pilot ran 2 documents for $0.083 and lost 9 of 10 claims to the 15-word ceiling D7 removes | Official forward-allocation shape unproven, no aggregator may be scraped; the SBI pilot predates `sbi-v1.5` | Owner runs the NSE forward probe; **clean re-pilot on `sbi-v1.5` before the ~193-document run**; drain the RHP backlog before completeness is claimed |
| 3 | R2 storage / ledger / SHA | `document_ledger.store_document` | Complete Details evidence | **CODE COMPLETE → OWNER CHECK** | Production handshake never observed by an owner | Owner attaches one real store + fetch round trip |
| 4 | Kite → daily / 15-minute / TOP levels | Kite refresh, daily candles, `kite_fetch_15m`, `topout_online` | Journey / Listing Review | **CODE COMPLETE → OWNER CHECK** — the 08-16 run inserted **2,044 15-minute bars across 4 IPOs** and wrote **4 TOP observations**, $0 spend; #340 D2 stops the token landing on a duplicate spine row | **5 of 10 Kite tokens unresolved** (pre-#340 run); the 15-minute bars are in Postgres but **not published to KV**, so no consumer can render them | Resolve the 5 tokens and check CSM 493 carries its token on one row; ship **B-3** (proposed in #339, open) |
| 5 | Listing pre-open capture | `capture_preopen.py` | Command Center · Live | **CODE COMPLETE → OWNER CHECK** | Live overlay deliberately BLOCKED (Kite credential automation unproven) | Owner decision on credential automation |
| 6 | Complete Details record | snapshot builder → `ipo-details:isin:*:v1` | Complete Details (CD1, #335) | **CODE COMPLETE → OWNER CHECK** | Owner mobile UAT not signed off | Owner walks one populated and one pending ISIN |
| 7 | Junk filtering / decision engine | decision engine → `decisions` | Command Center verdicts | **CODE COMPLETE → OWNER CHECK** | Live verdict distribution never checked against production | Owner spot-checks the current distribution |
| 8 | Listing rules | **`pipeline/rule_validation.py` (V2, `v2-rules-1`, merged in #340)** — one row per rule, `NOT_EVALUABLE` with the absent input named, `CANONICAL` empty, everything mined labelled `DISCOVERY`. The V1 `compatibility/scripts/rule_validation.py` stays quarantined. | none today | **PRODUCER CODE COMPLETE → CONSUMER BLOCKED** | The rows reach Postgres only — **no KV snapshot carries them** (verified against `pipeline/build/build_snapshots.ts` and #339). Writes are also gated on `RULE_VALIDATION_OWNER_APPROVED=1` | Ship **B-7** (§4c) — a `ipo-rules:isin:<ISIN>:v1` payload with `status` / `status_detail` / `missing_inputs` and **no** win-rate columns. Until it exists **no rules card and no rule count renders anywhere** |
| 9 | Journey TOP / watch state (no bottom, no entry interpretation) | `topout_online` → `listing_observations(level)` → `journey:isin:*:v1` | **Listing Review (LR1, this PR)** | **CODE COMPLETE → OWNER CHECK** | Consumer renders `state` / `watch_kind` / `fire_path` / `trigger` as DISCOVERY; the 15-minute tape behind it needs **B-3** | Owner checks one listed IPO with a fired TOP; `STALE_INPUT` (added by #333) renders as NOT EVALUATED |

**Hexagon, 08-16:** `TIER1_REJECTION`, invalidated by a later high. Recorded as
**expected detector semantics**, not a defect — the detector invalidates a watch
when a new high forms.

**Explicitly out of scope this cycle (recorded, not built):** Admin live-lane
health (needs **B-2**), a 15-minute tape (needs **B-3**), quantitative
performance statistics (needs **B-1**), and the **rules card (needs B-7** — the
producer now exists, the KV payload does not; see the stop record in §4c).

---

## 5. Capability rows

Advanced this cycle: **CH1** (the consumer-honesty pass). Everything else is
carried forward unchanged, still awaiting the same owner evidence.

| Row | Capability | State |
| --- | --- | --- |
| D1 | Theme system (system/light/dark, no hydration flash, semantic tokens) | CODE COMPLETE → OWNER CHECK (screenshots) |
| D2 | Shared screen states (loading/empty/pending/stale/config-required/failed+retry) | CODE COMPLETE → OWNER CHECK |
| D3 | Command Center simplification + truthfulness (no fabricated edge %, REIT/InvIT visibly excluded, three-verdict preserved) | CODE COMPLETE → OWNER CHECK |
| D7 | Mobile-first Command Center at 380px | CODE COMPLETE → OWNER CHECK (screenshots) |
| A3 | Admin Operations dashboard — **zero-wake** (KV-only, no Neon web polling); active-IPO + completeness from KV with UNKNOWN on degraded; lane health awaits the `pipeline-health:v1` producer | CODE COMPLETE → OWNER CHECK |
| LR1 | Listing Review / journey screen — per listed IPO: listing-day outcome (`listing_open`, `gap_pct`, `d1_close`, best/worst close, `ceiling_20` with its shipped non-executable label) rendered through the SAME `fieldDisplay` state renderer as Complete Details; a first-five-session **daily** price tape from the journey snapshot with one honest line about what KV does not carry; top-structure DISCOVERY observations mirroring the detector's own label; no win-rate/backtest percentage anywhere. KV-only consumer of two existing routes (`/api/ipo/journey` → ISIN → `/api/ipo/details/<ISIN>`). | CODE COMPLETE → OWNER CHECK (owner mobile UAT) |
| CH1 | Pending-vs-missing reason strings — the details / journey consumers no longer print the producer's generic `"Data is not available from the current V2 source."` on a field whose absence the IPO's own lifecycle explains. A payload-derived lifecycle read (has it listed? has it been priced?) selects one honest sentence per field; a MISSING field now also names the producer that would fill it. `DetailField.state` is never rewritten — only the sentence and the word in front of it. | CODE COMPLETE → OWNER CHECK (owner walks Molbio / ipo_id 1100) |
| CD1 | Complete Details record screen — full `ipo-details-v1` record: identity/timeline, issue overview (+ derived market cap / lot value, labeled pro-forma), canonical financials & pro-forma (VERIFIED FACT vs DETERMINISTIC PRO-FORMA), valuation & fair value (house + canonical, no performance %), RHP & SBI verbatim evidence split by `source_type`, governance/risk, persisted decision, listing outcome, and a consolidated missing-data register. KV-only consumer; every leaf driven off `DetailField.state`; no `JSON.stringify`/`[object Object]` reaches the DOM. | CODE COMPLETE → OWNER CHECK (owner mobile UAT) |

All prior five (D1/D2/D3/D7/A3) plus **CD1**, **LR1** and **CH1** are **CODE
COMPLETE** and awaiting **OWNER CHECK** (UI screenshots + manual UAT). None is
VERIFIED DONE until the owner signs off.

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

### 5c. Pending vs missing (CH1) — build notes & the strings that changed

- **The complaint, verbatim from the owner's live screen** (Molbio, ipo_id
  1100): *"Issue price — not available — Data is not available from the current
  V2 source."* Molbio had not been priced yet. The absence was the lifecycle;
  the sentence described a defect that did not exist.
- **What that sentence actually is.** `lib/v2/ipo-details.ts:10` gives its
  `field()` helper a default `reason` argument. Every absent scalar it has no
  specific reason for gets that one string. It means *"no reason was written"* —
  it is a producer default, not a producer finding. The UI is therefore free to
  substitute a specific sentence, and this pass does exactly that and nothing
  more.
- **`DetailField.state` is never touched.** The state badge still renders
  whatever the payload shipped (a `MISSING` issue price still shows `MISSING`).
  Only the human-readable sentence and the lead word in front of it are the
  UI's. `absenceCopy()` is a pure read; a unit test asserts the payload object
  is unchanged after every key in the book is resolved against it.
- **The lifecycle is read from the payload, never from a clock.**
  `lifecycleFacts()` derives two booleans:
  `listed` from whether any `listing_outcome` leaf is `PENDING` (the producer's
  own `outcomePending`, which is exactly "has not listed yet"), and `priced`
  from whether `issue.issue_price` is `AVAILABLE`. Nothing new is requested of
  the producer.
- **Stated limitation, not worked around:** the only lifecycle date this
  snapshot carries is the listing date — no issue open / close / allotment date
  ships in v1 (`ipo-details.ts` says so itself). So "before pricing" is
  approximated by "before listing", and the Issue overview says that on screen
  in one line rather than implying a precision the payload does not have.
- **A reason the producer actually wrote is never overwritten.** Only the
  generic default is substituted. `"Current NSE ingestion does not retain
  noOfSharesOffered."`, `"P/E could not be computed; see missing_inputs."`,
  `"Listing outcome … is pending until the IPO lists."` and the rest render
  exactly as the producer wrote them.
- **MISSING now names its producer.** Absent rows previously hid `source`
  (it rendered only when there was a value), so a genuine gap did not say who
  would fill it. Absent rows now carry `producer: <source>` — which is the
  "keep MISSING with the producer named" half of the brief.
- **Register and rows agree by construction.** `buildMissingRegister()` resolves
  its reasons through the same `absenceCopy()`, so the §10 register cannot quote
  a different sentence from the row above it.

**Every reason string this cycle changed** — all of them replace the single
generic default, and each is chosen by the gate in its row:

| Field (payload path) | Gate | Reason when the lifecycle explains it | Reason when it does not |
| --- | --- | --- | --- |
| `identity.listing_date` | not yet listed | `pending — set when the exchange confirms the listing date` | `No listing date is recorded for this IPO.` |
| `issue.issue_price` | not yet listed | `pending — set when the issue is priced` | `No issue price is recorded for this IPO in the issue record.` |
| `issue.band_low` | not yet listed | `pending — set when the price band is announced` | `No price band is recorded for this IPO in the issue record.` |
| `issue.band_high` | not yet listed | `pending — set when the price band is announced` | `No price band is recorded for this IPO in the issue record.` |
| `issue.issue_size_cr` | not yet listed | `pending — set when the issue size is filed with the offer document` | `No issue size is recorded for this IPO in the issue record.` |
| `issue.fresh_issue_cr` | not yet listed | `pending — the fresh-issue amount is set when the offer document is filed` | `No fresh-issue amount is recorded for this IPO in the issue record.` |
| `issue.ofs_cr` | not yet listed | `pending — the offer-for-sale amount is set when the offer document is filed` | `No offer-for-sale amount is recorded for this IPO in the issue record.` |
| `issue.lot_size` | not yet listed | `pending — fixed with the price band` | `No lot size is recorded for this IPO in the issue record.` |
| `issue.face_value` | not yet listed | `pending — carried with the issue terms once they are filed` | `No face value is recorded for this IPO in the issue record.` |
| `valuation.score` | not yet priced | `pending — the v2 scoring engine runs on the issue price, which is not set yet` | `No v2-score valuation row is stored for this IPO.` |
| `valuation.band` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.engine_version` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.computed_at` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.peer_median_pe` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.fair_value_low` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.fair_value_high` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.inputs_used` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.missing_inputs` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.pe_source` | not yet priced | *(same pair)* | *(same pair)* |
| `valuation.pb_source` | not yet priced | *(same pair)* | *(same pair)* |
| `decision.verdict` | always | `pending — a persisted decision is not yet available` | *(same — see below)* |

`decision.verdict` has no lifecycle gate on purpose: the producer already marks
its own siblings `decision.reasons` and `decision.evidence` `PENDING` with
"A persisted decision is not yet available." whenever no decision row exists.
`verdict` is the one leaf it forgets, so the consumer says what the producer
says about the other two rather than inventing a third answer.

**One line added to the screen** (Issue overview): *"Pending vs missing is read
from the only lifecycle date this snapshot carries — the listing date. No issue
open / close date ships in v1, so a field the issue has not reached yet is
called pending, never a defect."*

**Fields deliberately NOT given a lifecycle reason**, because their absence is
permanent in v1 and the producer already names the producer that would fill
them: `issue.reservation_split` (NSE ingestion), `issue.shareholding_pre_post`,
`issue.objects_of_issue_with_amounts`, `issue.cash` (RHP extraction),
`decision.kill_reason` (derived, JUNK-only), `valuation.margin_of_safety`
(derived), `valuation.pe` / `valuation.pb` (the producer's `ratio()` already
writes a specific reason), and every `listing_outcome` leaf (the producer's
`outcome()` already distinguishes pending-until-listing from
no-computed-outcome). Those stay MISSING, with the producer named.

- **Scope honoured:** consumer-only. `pipeline_files_changed = 0`,
  `producer/schema_changes = 0`, `lib/v2_files_changed = 0`, no new API route,
  no SQL, no `DATABASE_URL` import, no payload fallback, no producer field
  invented. Edits limited to `lib/ui/details-format.ts`,
  `components/ipo/CompleteDetails.tsx`, `components/ipo/ListingReview.tsx`, a
  new unit test `lib/ui/pending-vs-missing.test.ts`, a new UAT spec
  `uat/tests/pending-vs-missing-reasons.spec.ts`, and this runbook.

---

## 6. Guardrails honoured this cycle

**Consumer-honesty cycle (2026-08-19):** `pipeline_files_changed = 0`,
`scripts_files_changed = 0`, `lib/v2_files_changed = 0`, `schema_changes = 0`,
`.github_files_changed = 0`, package dependencies changed = 0, new API routes =
0, new SQL = 0, `DATABASE_URL` imports added = 0, producer fields invented = 0.
Two commits: CH1 (the pending-vs-missing reason strings) and this
reconciliation. **The rules card was planned as a third commit and was not
built** — the repository check came back negative (no KV payload carries a rule
row), so it is recorded as backlog **B-7** with its producer contract instead of
being invented. Nothing is marked VERIFIED.

- `pipeline_files_changed = 0`
- `scripts_files_changed = 0`
- `shared_seams_touched = NONE`
- `production_calls = 0`, `production_writes = 0`, `deployments = 0`
- No `DATABASE_URL` fallback added; no new DB query; no fabricated field.
- npm audit thresholds and advisory allowlist unchanged; Python install/execution unchanged; production pipeline schedules unchanged.
