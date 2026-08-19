Status: CURRENT

# AACapital — End-to-End Automated Pipeline Spec

The full "IPO appears → data fills → decision made" flow, source-of-truth to
command-center. This documents the target contract; the canonical driver
(`pipeline/cron.py`) is built to it.

> Corrected 2026-08-17: this paragraph previously named `_scripts/run_ipo_pipeline.py`
> as the implementing pipeline and "the VM" as the host. That script is quarantined
> under `compatibility/scripts/` and the VM is decommissioned. The body below already
> annotates the retired Chittorgarh lane correctly; only this heading was stale.

## 0. The principle
An IPO enters our world the moment it appears on an NSE listing/upcoming feed.
From there, every field fills itself from our sources of truth via the nightly
(and listing-morning) cron — no manual entry. The command center rates the
company and keeps updating (anchors, OFS, price band, PE-vs-peer) as data lands,
until the only thing still unknown at IPO-open is QIB. The owner uses the command
center to decide whether a company is worth caring about, does their own research
on the gaps Sonnet flags, and makes the final call on listing day against house rules.

## 1. Trigger — new IPO discovery
- **NSE discovery** is the live entry point: the canonical official-universe refresh
  (`pipeline/nse_lifecycle.py --discovery-only`, driven by `pipeline/cron.py`) is what
  creates IPO rows when an issue appears on NSE.
- **Chittorgarh** scrapers are RETIRED/quarantined — `scrape_chittorgarh.py` and
  `enrich_ipo_chittorgarh.py` now live under `compatibility/scripts/` and are NOT run in
  production (marked UNREACHABLE/QUARANTINED in `docs/repository-inventory.tsv`). They are
  not the primary calendar source.
- An IPO row is created with identity (name, symbol, dates, size, band) and then
  progressively enriched by the steps below.

## 2. Sources of truth → what each fills
| Source | Fills | Script |
|---|---|---|
| NSE upcoming/listings | discovery, symbol, listing/open/close dates | `fetch_nse_ipos.py` |
| Chittorgarh (RETIRED — quarantined under `compatibility/scripts/`, not run) | formerly calendar, issue size, band, anchors, subscription | `compatibility/scripts/scrape_chittorgarh.py`, `compatibility/scripts/enrich_ipo_chittorgarh.py` |
| IPOMatrix | anchors/structure for new IPOs (JWT, admin-set cookie) | `ipomatrix_ingest.py` |
| InvestorGain | GMP (day-before + history) — context only | `scrape_investorgain_gmp.py` |
| SEBI / Chittorgarh | RHP prospectus PDF | `fetch_new_rhps.py`, `download_sebi_rhps_playwright.py` |
| SBI (research desk) | SBI IPO note PDF + peer/valuation | `download_sbi_notes.py`, `parse_sbi_notes.py` |
| Screener | financials (EPS, ROE, CAGR, debt), peer P/E | `download_screener_playwright.py`, `import_screener_financials.py` |
| NSE bhavcopy | delivery %, listing OHLC | `fetch_delivery_bhavcopy.py`, `backfill_ipo_ohlc.py` |
| Kite | candles, listing_open, live price | `kite-sync-candles.py`, `sync_inwindow_candles.py` |

Rule: strong-key joins only (ISIN > exact normalized name, never fuzzy);
fill-empty-only (COALESCE) enrichment; one owning source per column.

## 3. Document handling — RHP (Sonnet) + SBI (scrape/parse)
- **RHP → Sonnet (forensic verdict):** Claude Sonnet reads the **RHP only** and
  produces the forensic verdict (clean / watch / reject) plus governance flags,
  material risks, and the gaps the owner should research. Sonnet is single-purpose
  here — RHP forensic, nothing else. (`rhp_sonnet.py` → `rhp_sonnet_store.py`.)
- **SBI → existing scrape + parse (structured data):** the SBI research note is
  handled by the existing download + parse jobs (`download_sbi_notes.py`,
  `parse_sbi_notes.py`), which extract the structured fields (rating, peer table,
  valuation) into `ipo_research_notes`. SBI is NOT sent to Sonnet.
- **Cost cap:** Sonnet RHP extraction is capped at **$3 per run**.
- **Failure handling:** if two or more RHPs need extraction and one fails because
  the cost cap / rate limit is hit, that IPO is **logged as pending and picked up
  on the next run** — never silently dropped. The log records IPO, reason, timestamp.
- **Download to VM:** the auto job downloads the RHP (and, for IPOs from SBI Funds
  onward, the SBI note) PDFs to the VM and stores a link for each; earlier RHPs
  already sit in local storage.

> Note: an earlier draft proposed sending both RHP and SBI to Sonnet (and a Haiku
> pass for broker docs). That is **not** the design — Sonnet stays RHP-only; SBI is
> structured scrape/parse. Broker-doc LLM extraction is out of scope for now.

## 4. Command-center computation (once inputs land)
As soon as the required inputs exist, the command center computes and keeps updating:
- **Quality vs junk** — RHP+SBI Sonnet gate (reject = hard pass).
- **Score** — the quantitative listing-open score.
- **Fair value + PE-vs-peer** — from Screener financials + peer P/E.
- **Verdict** — AVOID / WATCH / TRADE (buy-at-open logic).
- **Anchors, OFS mix, price band** — updated as each fills.

**The one accepted gap:** **QIB** is not available before IPO open. Everything else
should be present **on or before the first day the IPO opens.** No other field may
sit blank once its source has published.

## 5. The owner's loop (what automation serves)
1. Command center flags an IPO worth caring about (quality + score).
2. Owner does additional research — promoter interviews, answering the gaps Sonnet
   flagged in the RHP/SBI read.
3. On listing day, owner decides if it qualifies the house rules (and uses the
   live pre-open engine, §6B of the requirements doc, for the buy-at-open call).

## 6. Automation contract (cron)
- Runs on the **VM crontab** (not GitHub Actions — those are intentionally disabled).
- **Twice daily:** once ~1 hour before market open, once ~2 hours after close, on
  trading days. (IST market 09:15–15:30 → ~08:15 IST pre + ~17:30 IST post.)
- **SBI scrape** is the exception kept in GitHub Actions (by design, not stored/run on VM).
- Every job is also runnable on demand from the **Admin screen** (`job_runner.py` whitelist).
- **Nothing fails silently:** each job catches its errors and writes a readable
  reason to `job_runs` for the admin screen; a failed doc-extraction re-queues.

## 7. Known state / gaps (honest, at time of writing)
- `fetch_nse_ipos.py` (`_scripts/ipo/`) is now wired as the FIRST pipeline step
  (NSE discovery trigger) — upserts new IPOs into ipo_intelligence, dedup-safe.
- Sonnet reads the RHP only (by design). SBI is structured scrape/parse — no LLM.
- `eps_post` is null for current upcoming IPOs → modeled fair value is null → the live
  engine uses the GMP-implied anchor until Screener financials populate EPS.
- The current "data not flowing" symptom (anchors/GMP blank on upcoming IPOs) is a
  break to diagnose, separate from this spec — the scrapers and pipeline exist.
