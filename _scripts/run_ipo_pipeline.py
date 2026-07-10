#!/usr/bin/env python3
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
    if not preflight(): sys.exit(1)

    ok=True
    # order matters: SCRAPE new IPOs/GMP → regime → candles → listing_open → consolidated → levels → gate
    # scrape steps are non-hard (a source hiccup shouldn't kill the data refresh). Adjust script
    # names to your scrapers; missing ones just warn and skip.
    # no --year: scrape_chittorgarh.py defaults to the CURRENT year (never goes stale)
    step("scrape IPO calendar + details", ["scrape_chittorgarh.py","--write-db"])
    # anchor/subscription depth (non-hard: token/CF hiccup shouldn't kill the run)
    step("anchor + subscription enrich",  ["ipo/enrich_ipo_chittorgarh.py","--auto","--apply"])
    step("refresh GMP",                   ["ipo/refresh_gmp.py"])
    step("delivery pct (NSE bhavcopy)",    ["fetch_delivery_bhavcopy.py","--backfill-days","3"])
    step("bulk/block deals (NSE)",         ["fetch_institutional_deals.py"])
    step("insider trades (NSE, exp.)",     ["fetch_insider_trades.py"])
    step("anchor-deal conviction match",   ["match_anchor_deals.py","--apply"])
    ok&=step("market regime + VIX (today)", ["backfill_market_regimes.py"])
    ok&=step("candles: in-window daily sync",  ["sync_inwindow_candles.py"])
    step("candles: full NSE universe",     ["kite-sync-candles.py","--days","5"])
    ok&=step("listing-day fields (kite)",     ["ipo/backfill_ipo_ohlc.py"])
    ok&=step("derive listing_open",         ["fill_listing_open_from_candles.py"])
    step("download SBI notes (new only)", ["download_sbi_notes.py","--out","data/research_notes"])
    step("parse SBI notes -> DB",         ["parse_sbi_notes.py","--dir","data/research_notes","--write-db"])
    step("ipo score v0 (derived)",       ["ipo_score.py","--apply"])
    step("d10 outcome precompute",        ["compute_d10.py"])
    step("reconcile listing dates",     ["reconcile_listing_dates.py","--apply"])
    step("close-in-range strength",     ["close_in_range.py","--apply"])
    step("master computables backfill",   ["backfill_master_computables.py","--apply"])
    step("sector cleanup",                ["fix_sectors.py","--apply"])
    step("peer PE (self-computed)",       ["compute_peer_pe.py","--apply"])
    step("quality flags (Laser pattern)", ["compute_quality_flags.py","--apply"])
    step("convergence ranking (Today)",   ["compute_convergence_ranking.py"])
    step("convergence snapshot (history)", ["snapshot_convergence.py"])
    step("d10 outcome precompute",        ["compute_d10.py"])
    step("master computables backfill",   ["backfill_master_computables.py","--apply"])
    step("sector cleanup",                ["fix_sectors.py","--apply"])
    step("peer PE (self-computed)",       ["compute_peer_pe.py","--apply"])
    step("quality flags (Laser pattern)", ["compute_quality_flags.py","--apply"])
    step("convergence ranking (Today)",   ["compute_convergence_ranking.py"])
    step("convergence snapshot (history)", ["snapshot_convergence.py"])
    ok&=step("rebuild consolidated",        ["build_ipo_consolidated_v2.py"])
    # REMOVED: OBIR floor/ceiling compute (no value, burned CU-hrs) — 2026-07-10
    step("compute IPO verdicts (TRADE/WATCH/CAUTION/AVOID)", ["compute_verdicts.py","--apply"])
    step("sync trade journal (kite orders)", ["sync_trade_journal.py"])
    step("compute journal outcomes",         ["compute_journal_outcomes.py","--apply"])
    step("backup critical tables",           ["backup_critical_tables.py"])
    if a.weekly:
        step("purge post-lock candles",     ["purge_candles_after_lockin.py","--buffer","10","--apply"])
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
