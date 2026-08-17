# Lean pipeline retirement decision register

**Status:** OWNER DECISION REQUIRED — evidence captured for PR #328; no ports are authorized here.

## B1 scheduling evidence

| Evidence | Finding | Status |
|---|---|---|
| `.github/workflows/pipeline.yml` | GitHub Actions does not schedule the lean pipeline; it is `workflow_dispatch` only and says “MANUAL DISPATCH ONLY — no schedule”. | VERIFIED |
| `_archive/scripts/setup_vm_cron.sh` | A legacy VM-cron installer that *would* schedule `_scripts/run_ipo_pipeline_lean.py` **if a human ran it on the VM**. It is **archived, not installed, and never was installed by this repository** — no workflow, `job_runner.py` entry, `package.json` script, or module reference executes it. Moved from the repo root to `_archive/scripts/` (VM decommissioned, owner-confirmed) and retained as the historical evidence behind this row. | VERIFIED |
| Production VM | Installer presence never proved installation, and the installer is now archived. The VM itself is decommissioned per owner confirmation; no crontab state remains to probe. The read-only probe below is retained for the record only. | SUPERSEDED — VM decommissioned |
| `pipeline/cron.py` | Verified owner-PC daily driver from #327's two green owner acceptance runs. | VERIFIED |

Owner read-only probe (historical — the VM is decommissioned, so there is no
host left to run this against; kept so the record shows what was asked for):

```bash
crontab -l 2>/dev/null | grep -E 'run_ipo_pipeline_lean|pipeline/cron.py|refresh_kite_token' || true
```

> **Open conflict for the owner.** `docs/runbooks/VM_CRON_RUNBOOK.md` is still
> stamped `Status: CURRENT` and describes the Hetzner VM as "the automation
> engine". That contradicts the decommissioning confirmation this row now
> records. This cleanup does not resolve the conflict — retiring or re-stamping
> an operational runbook is an owner call, not a hygiene change.

## Capability decisions

`YES` means `pipeline/cron.py` owns the capability; `PARTIAL` means the canonical driver covers only part of the legacy behavior. Recommendations are advisory. Every verdict intentionally remains `OWNER`.

| Capability | Current script/job | What it does | cron.py equivalent | Codex recommendation | Evidence | Owner verdict |
|---|---|---|---|---|---|---|
| NSE discovery and lifecycle | `ipo/fetch_nse_ipos.py` | Legacy IPO discovery | YES | DROP | `cron.py` invokes `nse_lifecycle.py` discovery and lifecycle | OWNER |
| Legacy issue enrichment | `ipomatrix_ingest.py` | Retired external enrichment | NO | DROP | Owner removed this source; canonical lifecycle is official NSE | OWNER |
| EPS post-issue backfill | `backfill_eps_post.py` | Derives post-issue EPS inputs | PARTIAL | PORT | No direct canonical cron step identified | OWNER |
| GMP refresh | `ipo/refresh_gmp.py` | Third-party grey-market input | NO | DROP | No official-source canonical lane | OWNER |
| NSE delivery percentage | `fetch_delivery_bhavcopy.py` | Post-listing delivery data | NO | KEEP-legacy | Official NSE capability not present in `cron.py` | OWNER |
| Market regime/VIX | `backfill_market_regimes.py` | Legacy market context | NO | KEEP-legacy | No canonical IPO cron equivalent | OWNER |
| Daily/listing OHLC legacy chain | `sync_inwindow_candles.py`, `ipo/backfill_ipo_ohlc.py`, `fill_listing_open_from_candles.py` | Legacy candles and listing outcomes | YES | DROP | `cron.py` uses canonical `kite_fetch.py` | OWNER |
| SBI acquisition/extraction | `download_sbi_notes.py`, `sbi_haiku_extract.py` lean calls | Downloads and legacy Haiku extraction | YES | DROP | `cron.py` has owner-gated R2-first SBI ingest/extraction | OWNER |
| RHP acquisition/extraction | `rhp_auto.py` | Legacy RHP download/Sonnet orchestration | YES | DROP | `cron.py` has bounded RHP download/extraction gates | OWNER |
| Legacy score and verdict | `ipo_score.py`, `compute_quality_score.py`, `compute_verdicts.py` | V1 derived scores/verdicts | YES | DROP | `cron.py` invokes canonical `drive.py` once | OWNER |
| Red-flag scanner | `compute_flags.py` | Legacy forensic flags | PARTIAL | PORT | Canonical drive has verdict evidence but field parity is not proven | OWNER |
| Peer valuation chain | `derive_peer_pe_from_notes.py`, `fetch_peer_pe.py` | Legacy peer multiples | PARTIAL | KEEP-legacy | No exact canonical parity proven | OWNER |
| Trade journal and outcomes | `sync_trade_journal.py`, `compute_journal_outcomes.py` | Broker journal and derived outcomes | NO | KEEP-legacy | Outside canonical daily IPO driver | OWNER |
| Backup/purge/health utilities | `backup_critical_tables.py`, `purge_candles_after_lockin.py`, diagnostic scripts | Maintenance, backup, and legacy health gates | PARTIAL | KEEP-legacy | Canonical reporting overlaps health only; backup/purge do not | OWNER |
| Listing pre-open | `nse_preopen_capture.py` / legacy external schedule | Listing-morning book | YES | DROP | `cron.py` lifecycle invokes canonical `capture_preopen.py`; no lean call remains | OWNER |

Full lean retirement and any owner-approved ports are a separate follow-up PR after the owner annotates this register. This PR does not begin that work.
