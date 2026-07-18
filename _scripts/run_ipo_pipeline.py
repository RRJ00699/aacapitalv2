#!/usr/bin/env python3
# ═══════════════ TOMBSTONE (2026-07-16) ═══════════════
# RETIRED: superseded by run_ipo_pipeline_lean.py (34 steps, no frozen-table
# writes). This script was found still wired in the VM crontab on 2026-07-16
# — hence this guard. Kept temporarily as a rollback path; delete after lean
# has a clean month. To run anyway: AAC_LEGACY=1 python run_ipo_pipeline.py
import os as _os, sys as _sys
if _os.environ.get("AAC_LEGACY") != "1":
    _sys.exit("RETIRED: use run_ipo_pipeline_lean.py (set AAC_LEGACY=1 to force the old pipeline)")
# ═══════════════════════════════════════════════════════
"""
run_ipo_pipeline.py — ONE command that runs the whole IPO dashboard data workflow, in order.
Idempotent (every step is golden-rule / skip-existing), safe to run daily.

  python _scripts\\run_ipo_pipeline.py             # daily run
  python _scripts\\run_ipo_pipeline.py --weekly    # daily + purge post-lock candles

Schedule it (Windows Task Scheduler, runs daily 6:30pm CT after data settles):
  schtasks /create /tn "AAC IPO Pipeline" /tr "python C:\\aacapital-v2\\_scripts\\run_ipo_pipeline.py" /sc daily /st 18:30

PREREQ (the one manual step): a valid Kite token in platform_config. Kite requires a daily
OAuth login, so refresh the token each morning; the pipeline pre-flights it and stops early if stale.
Logs to _scripts/logs/pipeline_YYYY-MM-DD.log.
"""
import subprocess, sys, os, datetime, argparse
HERE=os.path.dirname(os.path.abspath(__file__))
REPO=os.path.dirname(HERE)
LOGDIR=os.path.join(HERE,"logs"); os.makedirs(LOGDIR,exist_ok=True)
LOG=os.path.join(LOGDIR,f"pipeline_{datetime.date.today()}.log")

def log(m):
    line=f"[{datetime.datetime.now():%H:%M:%S}] {m}"
    print(line)
    with open(LOG,"a",encoding="utf-8") as f: f.write(line+"\n")

def preflight():
    """Stop early if the Kite token is stale — saves a doomed run."""
    try:
        sys.path.insert(0,HERE)
        from kite_connect import get_kite
        get_kite().profile(); log("preflight OK — Kite token valid"); return True
    except Exception as e:
        log(f"PREFLIGHT FAILED — Kite token stale/invalid ({e}). Refresh token, then re-run."); return False

def step(name, args, hard=False):
    log(f"── {name} ──")
    # skip cleanly if the script file is missing (don't error the whole nightly)
    script = args[0] if args else ""
    if script.endswith(".py") and not os.path.exists(os.path.join(HERE, script)):
        log(f"   ⏭  {script} not in repo — skipping (not a failure)")
        return True
    r=subprocess.run([sys.executable]+args, cwd=HERE, capture_output=True, text=True)
    out=(r.stdout or "").strip().splitlines()
    for l in out[-6:]: log("   "+l)          # tail of each step's output
    if r.returncode!=0:
        log(f"   ⚠️ {name} exited {r.returncode}"+(" (HARD FAIL — stopping)" if hard else ""))
        if r.stderr: log("   "+r.stderr.strip().splitlines()[-1])
        return False
    log(f"   ✓ {name} done"); return True

def self_update():
    """Sync the repo to origin/main so the VM always runs the latest pushed code.
    You push from your PC; the next scheduled run picks it up. No SSH needed."""
    try:
        subprocess.run(["git","fetch","--quiet","origin","main"], cwd=REPO, timeout=90)
        subprocess.run(["git","reset","--hard","--quiet","origin/main"], cwd=REPO, timeout=90)
        log("self-update: synced to origin/main")
    except Exception as e:
        log(f"self-update skipped ({e}) — running current code")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--weekly",action="store_true"); a=ap.parse_args()
    log(f"=== IPO PIPELINE START {datetime.datetime.now():%Y-%m-%d %H:%M} ===")
    self_update()
    kite_ok = preflight()   # was: if not preflight(): sys.exit(1)
    if not kite_ok:
        log("⚠️ Kite token stale — SKIPPING Kite-only steps (candles/OHLC/journey). "
            "All non-Kite work (scrape, GMP, SBI, RHP, score, consolidated) still runs. "
            "Refresh token to restore price/candle steps.")

    ok=True
    # order matters: SCRAPE new IPOs/GMP → regime → candles → listing_open → consolidated → levels → gate
    # scrape steps are non-hard (a source hiccup shouldn't kill the data refresh). Adjust script
    # names to your scrapers; missing ones just warn and skip.
    # no --year: scrape_chittorgarh.py defaults to the CURRENT year (never goes stale)
    # NSE discovery trigger: seed new IPOs from the live NSE feed into ipo_intelligence
    # FIRST, so a freshly-announced IPO enters our world before enrichment runs.
    # Upserts by company_name (dedup-safe, RULE 1); non-hard so an NSE hiccup won't kill the run.
    step("NSE discovery (new IPOs)",        ["ipo/fetch_nse_ipos.py"])
    step("scrape IPO calendar + details", ["scrape_chittorgarh.py","--write-db"])
    # anchor/subscription depth (non-hard: token/CF hiccup shouldn't kill the run)
    step("anchor + subscription enrich",  ["ipo/enrich_ipo_chittorgarh.py","--auto","--apply"])
    # IPOMatrix: gold-standard JSON for new/incomplete IPOs (anchors/structure).
    # --only-null = just IPOs missing data; skips cleanly if the JWT cookie is stale.
    step("IPOMatrix enrich (new IPOs)",   ["ipomatrix_ingest.py","--only-null","--apply"])
    step("refresh GMP",                   ["ipo/refresh_gmp.py"])
    step("delivery pct (NSE bhavcopy)",    ["fetch_delivery_bhavcopy.py","--backfill-days","3"])
    # [IPO-only] removed non-IPO step (writes to dropped table):
    #step("bulk/block deals (NSE)",         ["fetch_institutional_deals.py"])
    # [IPO-only] removed non-IPO step (writes to dropped table):
    #step("insider trades (NSE, exp.)",     ["fetch_insider_trades.py"])
    # anchor-deal conviction match removed 2026-07-18 (dead: institutional_large_deals
    # table does not exist; no consumer). Script archived to _archive/.
    ok&=step("market regime + VIX (today)", ["backfill_market_regimes.py"])
    ok &= (step("candles: in-window daily sync",  ["sync_inwindow_candles.py"]) if kite_ok else True)
    (step("candles: full NSE universe",     ["kite-sync-candles.py","--days","5"]) if kite_ok else None)
    ok &= (step("listing-day fields (kite)",     ["ipo/backfill_ipo_ohlc.py"]) if kite_ok else True)
    ok &= (step("derive listing_open",         ["fill_listing_open_from_candles.py"]) if kite_ok else True)
    step("download SBI notes (new only)", ["download_sbi_notes.py","--out","data/research_notes"])
    step("parse SBI notes -> DB",         ["parse_sbi_notes.py","--dir","data/research_notes","--write-db"])
    step("ipo score v0 (derived)",       ["ipo_score.py","--apply"])
    step("d10 outcome precompute",        ["compute_d10.py"])
    step("reconcile listing dates",     ["reconcile_listing_dates.py","--apply"])
    # REMOVED 2026-07-18 (dead step): close-in-range — CIR rejected as leakage
    # (spec §5); no consumer. Script archived to _archive/. (close_in_range.py)
    step("master computables backfill",   ["backfill_master_computables.py","--apply"])
    # [DEAD-TABLE, removed] step("sector cleanup",                ["fix_sectors.py","--apply"])
    # [DEAD-TABLE, removed] step("peer PE (self-computed)",       ["compute_peer_pe.py","--apply"])
    # [DEAD-TABLE, removed] step("quality flags (Laser pattern)", ["compute_quality_flags.py","--apply"])
    # [IPO-only] removed non-IPO step (writes to dropped table):
    #step("convergence ranking (Today)",   ["compute_convergence_ranking.py"])
    # [IPO-only] removed non-IPO step (writes to dropped table):
    #step("convergence snapshot (history)", ["snapshot_convergence.py"])
    step("d10 outcome precompute",        ["compute_d10.py"])
    step("master computables backfill",   ["backfill_master_computables.py","--apply"])
    # [DEAD-TABLE, removed] step("sector cleanup",                ["fix_sectors.py","--apply"])
    # [DEAD-TABLE, removed] step("peer PE (self-computed)",       ["compute_peer_pe.py","--apply"])
    # [DEAD-TABLE, removed] step("quality flags (Laser pattern)", ["compute_quality_flags.py","--apply"])
    # [IPO-only] removed non-IPO step (writes to dropped table):
    #step("convergence ranking (Today)",   ["compute_convergence_ranking.py"])
    # [IPO-only] removed non-IPO step (writes to dropped table):
    #step("convergence snapshot (history)", ["snapshot_convergence.py"])
    step("sync issue_details -> intelligence (isin)", ["sync_issue_details.py","--apply"])
    ok&=step("rebuild consolidated",        ["build_ipo_consolidated_v2.py"])
    # REMOVED: OBIR floor/ceiling compute (no value, burned CU-hrs) — 2026-07-10
    step("compute IPO verdicts (TRADE/WATCH/CAUTION/AVOID)", ["compute_verdicts.py","--apply"])
    step("compute red-flag scanner", ["compute_flags.py","--apply"])
    # (distribution detector RETIRED 2026-07-15 — clean backtest n=368: fires 10%,
    #  +0.8pt win / zero median vs trail-12; complexity without edge)
    # --- RHP forensic pipeline (governance/legal/concentration moat) ---
    # (download_rhps/rhp_batch RETIRED 2026-07-15 — superseded by rhp_auto.py on its
    #  own cron: fetch_new_rhps -> rhp_sonnet ($1 cap) -> rhp_sonnet_store -> purge)
    # (accuracy leaderboard RETIRED 2026-07-15 — script/table removed)
    step("sync trade journal (kite orders)", ["sync_trade_journal.py"])
    step("compute journal outcomes",         ["compute_journal_outcomes.py","--apply"])
    step("backup critical tables",           ["backup_critical_tables.py"])
    if a.weekly:
        step("purge post-lock candles",     ["purge_candles_after_lockin.py","--buffer","10","--apply"])
        step("data hygiene (stale purge)",   ["purge_stale_data.py","--apply"])
    # health gate LAST — fails loud if anything regressed
    gate=step("health-check (gate)",        ["check_data_contract.py"], hard=False)
    step("value-sanity report",             ["check_value_sanity.py"])

    log(f"=== PIPELINE {'OK' if ok and gate else 'COMPLETED WITH WARNINGS — check log'} ===")
    if ok and gate:
        url = os.environ.get("HEALTHCHECK_URL", "").strip()
        if url:
            try:
                import urllib.request; urllib.request.urlopen(url, timeout=15)
                log("dead-man switch pinged")
            except Exception as e:
                log(f"healthcheck ping failed ({e}) — healthchecks.io will alert (as designed)")
    sys.exit(0 if ok and gate else 2)

if __name__=="__main__": main()
