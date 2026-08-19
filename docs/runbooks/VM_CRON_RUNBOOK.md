Status: SUPERSEDED by docs/runbooks/DAILY_RUN.md — the VM is decommissioned
Authority: docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-21
Verified commit: efa45de
Last verified against VM: 2026-07-21 01:04 IST snapshot (owner-run)
Verified commit on VM at snapshot: b3d9bcb (#255)

# VM CRON RUNBOOK (SUPERSEDED — the host no longer exists)

> **The Hetzner VM this runbook operates is decommissioned (owner-confirmed).**
> Nothing below can be run: there is no host to ssh to, no crontab to inspect,
> and no `/root/aac` working directory. Its installer,
> `setup_vm_cron.sh`, was archived to `_archive/scripts/` in the same cleanup that
> added this marking.
>
> The SHA stamps above are from 2026-07-21 (`efa45de` in-repo, `b3d9bcb` on the
> VM at snapshot) and were already the oldest verification stamps in `docs/`.
>
> **Read instead:** `docs/runbooks/DAILY_RUN.md` — the owner's supported daily
> command is now `python pipeline\cron.py` on the owner's Windows workstation —
> and `docs/runbooks/PRODUCTION_JOBS.md` for the verified caller map.
>
> Retained, not deleted: it is the record of the schedule the VM actually ran, and
> the evidence behind `docs/decisions/LEAN_RETIREMENT_DECISIONS.md` B1.

The VM (Hetzner, Nuremberg) is the automation engine. **Its system timezone is
set to `Asia/Kolkata` (IST)** — verified 2026-07-21 via `timedatectl` — so
every crontab time below is a true IST wall-clock time. If `timedatectl` ever
stops saying Kolkata, every schedule silently shifts: `vm_verify.py` checks
this first and flags it loudly.

Working directory: **`/root/aac`** (not `~/aacapitalv2`). Python:
`/root/aac/venv/bin/python`. Env: `/root/aac/.env` (sourced by every entry).
Logs: `/root/aac/logs/`.

## The one verification command

```bash
cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/vm_verify.py; echo "exit=$?"
```

Paste the full output back. Exit 1 = a CRITICAL stage (RHP download/parse,
Sonnet, score, or cron execution itself) is FAILED. PENDING (a source not yet
published) never fails the run; "never ran" reports NOT VERIFIED, never
success.

## Schedule (Mon–Fri unless noted) — IST · US-Central

US-Central shown for CDT (summer, IST−10:30). In winter (CST) subtract one
more hour. `vm_verify.py` prints the DST-correct conversion for today.

| IST | US-Central (CDT) | Job | Log |
|---|---|---|---|
| 08:30 | 22:00 prev day | Kite token refresh → **lean pipeline** (self-updates repo to origin/main first) | token.log · pipeline.log |
| 08:45 (daily) | 22:15 prev day | token top-up (ready before 09:00 pre-open) | token.log |
| 08:50 | 22:20 prev day | Chittorgarh morning scrape `--write-db` | scrape_am.log |
| 08:57 | 22:27 prev day | NSE pre-open capture (self-exits on non-listing days) | nse_preopen.log |
| 09:10 | 22:40 prev day | listing-day tick launcher (self-exits if nothing lists) | ticks.log |
| 09:25 · 13:00 | 22:55 prev · 02:30 | live-feed verification (×2) | verify_feed.log |
| 17:00 | 06:30 | token refresh → **lean pipeline** (2nd daily run) | token.log · pipeline.log |
| 18:05 | 07:35 | pipeline watchdog | watchdog.log |
| every minute | — | admin job console (self-throttles nights/weekends) | jobs.log |

## Facts the 2026-07-21 snapshot established

1. **Repo lag is by design**: the VM syncs to `origin/main` only inside the
   08:30/17:00 pipeline self-update. A PR merged at 21:51 IST is live on the
   VM at 08:30 IST next morning. Emergency sync: Admin → Sync, or
   `cd /root/aac && git fetch && git reset --hard origin/main`.
2. **RHP over-match**: `rhps/` held `ntpc`, `standard-chartered-plc`,
   `the-shipping-corporation-of-india`, `tirupati-inks` — SEBI filings that
   are not upcoming mainboard IPOs. `vm_verify.py §4` flags such dirs as
   SUSPECT; the matcher fix is tracked separately.
3. **Extraction backlog is visible**: slug dirs existed for 7 companies while
   `rhp_summaries/` held only Caliber — download ≠ analyzed. The matrix in
   `vm_verify.py §3` shows exactly this as PARTIAL, per the four-state rule.
4. Tick freshness breached its 1h SLA (2.1h) — watchdog territory, not fatal.

## Post-deploy acceptance — "how do I know it really works"

The ladder, in order; each rung catches what the one below cannot. Rungs 1–3
run in the sandbox/CI before every commit; rungs 4–5 are yours after deploy.

| # | Rung | Command | Pass looks like |
|---|---|---|---|
| 1 | Compiles | `npx tsc --noEmit` + `npm run build` (PC) | zero errors |
| 2 | Logic + SQL execute | `python -m pytest _scripts/tests/ -q` (needs `pip install pgserver`) | all pass, ~0 skipped |
| 3 | Routes actually run | included in rung 2 (route harness executes handlers with counting stubs) | A1/A2/A3 green |
| 4 | Production reality | the one VM command above | exit 0; §3 matrices honest; §5 payload live |
| 5 | Live day | watch one listing morning on /dashboard/ipo2 | ticks flow, states advance, no unsupported claims |

After THIS deploy specifically, expect in the vm_verify output: the two
stale Sonnet verdicts labeled "NO pdf fingerprint (legacy/stale)"; zero
SUSPECT rhps/ dirs after the next pipeline (matcher fix + prune); `compute
journal outcomes` and `SBI Haiku` either green or failing with a
self-explanatory stderr_tail; and once a NEW RHP lands end-to-end, insight
rows fanning out and cards showing "RHP · quoted" badges.

## Recovery quick-reference

| Symptom | First command | Then |
|---|---|---|
| No pipeline_steps in 36h (vm_verify CRITICAL) | `tail -50 logs/pipeline.log` | check crontab intact; run the 08:30 line by hand |
| Kite token URGENT ntfy | `venv/bin/python _scripts/refresh_kite_token.py` | rotate creds in Settings if TOTP rejected |
| RHP all-failed ntfy | `venv/bin/python _scripts/fetch_new_rhps.py --apply` | inspect the printed per-company ✗ reasons |
| ticks stale on a listing day | `pgrep -af kite_ticker` → if absent `venv/bin/python _scripts/ipo_live_launcher.py` | `tools/diagnostics/verify_live_feed.py` |
| VM running old code | `git -C /root/aac log -1 --oneline` vs GitHub main | Admin → Sync or manual reset above |

Locking/overlap: the lean pipeline is sequential within one cron line; the
job console self-throttles. Formal cross-run locking is part of the state-
machine PR (see `docs/specifications/PROVENANCE_DESIGN.md` §5) — until then, do not run the
pipeline by hand during the 08:30/17:00 windows.

## Kite nightly maintenance (why late-night manual runs show a red step)

Kite's historical-data API has a nightly maintenance window (~23:30–01:00
IST). A manual pipeline run inside it fails 'market regime + VIX' with
"No NIFTY candles returned" — that is the vendor, not the code. The
08:30/17:00 IST cron runs never touch the window. Trigger manual runs in
daytime IST, or ignore that one red at night.
