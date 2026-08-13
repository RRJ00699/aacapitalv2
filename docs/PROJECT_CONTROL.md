# AACapital — Project Control Plan

> Repo-native control surface. Single source of truth for program state,
> two-agent ownership, seams, and the exact producer fields the UI is waiting
> on. Refresh from evidence each cycle — never from memory.

- **Current main:** `18e4df78ee6ccb323e25856bc84efe1e96715617`
- **Last refreshed:** 2026-08-13
- **Refreshed by:** Claude (UI foundation cycle)

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

### Merges / PRs
- **PR #331 — MERGED.**
- **PR #332 — MERGED.**
- **PR #330 — CLOSED as superseded (NOT merged).** Do not resurrect its branch; any follow-up is a fresh change.
- **Codex pipeline-integrity PR — IN PROGRESS.** Backend producer correctness (the falsely-green lanes). Claude does not touch it.

### Daily pipeline
- **State: OWNER CHECK (regressed from green).** The latest owner run exposed
  **falsely-green Kite, candle, and TOP states** — the pipeline reported success
  while those lanes were stale/wrong. Health cannot be trusted from automation
  alone until the Codex pipeline-integrity PR lands and an owner re-verifies.

### Workstreams
| Workstream | State | Note |
| --- | --- | --- |
| UI program | **PARTIAL** | Foundation (theme, screen states, Command Center truthfulness, Admin operations) landing this cycle; more surfaces remain. |
| Migration | **IN PROGRESS** | Schema/data migration ongoing (Codex). |
| BOTTOM | **NOT STARTED** | |
| Anchor | **BLOCKED** | Waiting on the official forward-subscription payload; no UI consumption until the producer contract exists. |
| Rules producer | **BLOCKED** | Waiting on an owner decision. |

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

| Consumer surface | Requested field | Purpose |
| --- | --- | --- |
| Admin · Operations | `pipeline_step_runs.duration_ms` | Per-lane duration (no timing captured today) |
| Admin · Operations | `admin.owner_action_queue[]` | Owner-action queue |
| Admin · Operations | `pipeline_step_runs.config_required` | Flag lanes that need configuration |
| Admin · Operations | `rhp.retry_pending_count` | Retry / pending document count |
| Admin · Operations | `admin.paid_call_status{used,cap}` | Paid-call status/cap (no secret values) |
| Command Center | `strategy_backtest{cohort,win_rate,n,median}` | Validated cohort win-rates for the playbook. Until this ships, **no win-rate / "edge" percentage renders** — the UI shows qualitative setup descriptions only. |
| Command Center · Live | `rules_static[] / rules_live[] / rules_passed / rules_total` | Live rule evaluation. Rule counts render **only** when present in the payload. |
| Command Center · Anchor | official forward-subscription payload | Anchor workstream is BLOCKED until this producer contract exists. |

Contextual themes (market-session, verdict-driven, time-of-day) are **out of
scope** and remain an owner decision — not built in the theme v1.

---

## 5. Capability rows

Advanced this cycle: **D1, D2, D3, D7, A3.**

| Row | Capability | State |
| --- | --- | --- |
| D1 | Theme system (system/light/dark, no hydration flash, semantic tokens) | CODE COMPLETE → OWNER CHECK (screenshots) |
| D2 | Shared screen states (loading/empty/pending/stale/config-required/failed+retry) | CODE COMPLETE → OWNER CHECK |
| D3 | Command Center simplification + truthfulness (no fabricated edge %, REIT/InvIT visibly excluded, three-verdict preserved) | CODE COMPLETE → OWNER CHECK |
| D7 | Mobile-first Command Center at 380px | CODE COMPLETE → OWNER CHECK (screenshots) |
| A3 | Admin Operations dashboard (first failing lane in 5 min, honest unavailable states) | CODE COMPLETE → OWNER CHECK |

All five are **CODE COMPLETE** and awaiting **OWNER CHECK** (UI screenshots +
manual UAT). None is VERIFIED DONE until the owner signs off.

---

## 6. Guardrails honoured this cycle

- `pipeline_files_changed = 0`
- `scripts_files_changed = 0`
- `shared_seams_touched = NONE`
- `production_calls = 0`, `production_writes = 0`, `deployments = 0`
- No `DATABASE_URL` fallback added; no new DB query; no fabricated field.
- npm audit thresholds and advisory allowlist unchanged; Python install/execution unchanged; production pipeline schedules unchanged.
