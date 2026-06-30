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

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--weekly",action="store_true"); a=ap.parse_args()
    log(f"=== IPO PIPELINE START {datetime.datetime.now():%Y-%m-%d %H:%M} ===")
    if not preflight(): sys.exit(1)

    ok=True
    # order matters: regime → candles → listing_open → consolidated → levels → health gate
    ok&=step("market regime + VIX (today)", ["backfill_market_regimes.py"])
    ok&=step("backfill candles (new IPOs)", ["ipo/backfill_ipo_ohlc.py"])
    ok&=step("derive listing_open",         ["fill_listing_open_from_candles.py"])
    ok&=step("rebuild consolidated",        ["build_ipo_consolidated_v2.py"])
    ok&=step("daily floor/ceiling levels",  ["ipo_daily_levels.py","--from-db","--write-db"])
    if a.weekly:
        step("purge post-lock candles",     ["purge_candles_after_lockin.py","--buffer","10","--apply"])
    # health gate LAST — fails loud if anything regressed
    gate=step("health-check (gate)",        ["check_data_contract.py"], hard=False)

    log(f"=== PIPELINE {'OK' if ok and gate else 'COMPLETED WITH WARNINGS — check log'} ===")
    sys.exit(0 if ok and gate else 2)

if __name__=="__main__": main()
