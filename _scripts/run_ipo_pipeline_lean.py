#!/usr/bin/env python3
"""
run_ipo_pipeline_lean.py — the LEAN IPO data workflow.

Runs ONLY the steps that feed LIVE (canonical) tables from APPROVED sources,
per DATA_ARCHITECTURE.md. Cut vs the old run_ipo_pipeline.py:
  - fetch_institutional_deals (institutional_large_deals — not IPO-needed)
  - fetch_insider_trades (insider_transactions — not IPO-needed)
  - compute_convergence_ranking + snapshot_convergence (abandoned engine bloat)
  - the entire DUPLICATE block (old steps 26-32 re-ran peer_pe/quality/d10/etc.)
No step here writes a FROZEN table (ipo_master/predictions/feature_store/similarity).
Result: the real IPO flow, no zombies, ~half the DB compute.

  python _scripts/run_ipo_pipeline_lean.py            # daily/twice-daily run
  python _scripts/run_ipo_pipeline_lean.py --weekly   # + purge post-lock candles

PREREQ: a valid Kite token in platform_config (refresh runs first in cron).
Kite-only steps skip cleanly if the token is stale; all non-Kite work still runs.
Logs to _scripts/logs/pipeline_lean_YYYY-MM-DD.log.
"""
import subprocess, sys, os, datetime, argparse
HERE=os.path.dirname(os.path.abspath(__file__))
REPO=os.path.dirname(HERE)
LOGDIR=os.path.join(HERE,"logs"); os.makedirs(LOGDIR,exist_ok=True)
LOG=os.path.join(LOGDIR,f"pipeline_lean_{datetime.date.today()}.log")


def _log_step(name, script, ok, err=""):
    """StepBoard sink: EVERY step outcome -> pipeline_steps (green/red board in
    Settings, Rakesh 2026-07-17). Best-effort — can never break the pipeline."""
    try:
        import psycopg2 as _pg, os as _os
        _c = _pg.connect(_os.environ.get("DATABASE_URL") or _os.environ.get("NEON_DATABASE_URL", ""))
        _u = _c.cursor()
        _u.execute("""CREATE TABLE IF NOT EXISTS pipeline_steps (
            id SERIAL PRIMARY KEY, run_date DATE DEFAULT CURRENT_DATE,
            step TEXT, script TEXT, ok BOOLEAN,
            error TEXT, ran_at TIMESTAMPTZ DEFAULT NOW())""")
        _u.execute("INSERT INTO pipeline_steps (step, script, ok, error) VALUES (%s,%s,%s,%s)",
                   (name, script, ok, (err or "")[:300]))
        _c.commit(); _c.close()
    except Exception:
        pass

def log(m):
    line=f"[{datetime.datetime.now():%H:%M:%S}] {m}"
    print(line)
    with open(LOG,"a",encoding="utf-8") as f: f.write(line+"\n")

def preflight():
    """Stop-gate for Kite: returns True if the token is valid, else False (Kite steps skip)."""
    try:
        sys.path.insert(0,HERE)
        from kite_connect import get_kite
        get_kite().profile(); log("preflight OK — Kite token valid"); return True
    except Exception as e:
        log(f"preflight: Kite token stale/invalid ({e}) — Kite-only steps will skip"); return False

def step(name, args, hard=False):
    log(f"── {name} ──")
    script = args[0] if args else ""
    if script.endswith(".py") and not os.path.exists(os.path.join(HERE, script)):
        log(f"   ⏭  {script} not in repo — skipping (not a failure)")
        return True
    r=subprocess.run([sys.executable]+args, cwd=HERE, capture_output=True, text=True)
    for l in (r.stdout or "").strip().splitlines()[-6:]: log("   "+l)
    if r.returncode!=0:
        log(f"   ⚠️ {name} exited {r.returncode}"+(" (HARD FAIL — stopping)" if hard else ""))
        _log_step(name, script, False, (r.stderr or r.stdout or ""))
        try:
            # Failure sink -> pipeline_failures (Settings page shows these so
            # Rakesh can spot dead credentials/cookies without SSH).
            import psycopg2 as _pg
            _c = _pg.connect(os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL",""))
            _u = _c.cursor()
            _u.execute("""CREATE TABLE IF NOT EXISTS pipeline_failures (
                id SERIAL PRIMARY KEY, step TEXT, script TEXT,
                stderr_tail TEXT, failed_at TIMESTAMPTZ DEFAULT NOW())""")
            _u.execute("INSERT INTO pipeline_failures (step, script, stderr_tail) VALUES (%s,%s,%s)",
                       (name, script, (r.stderr or r.stdout or "")[-500:]))
            _c.commit(); _c.close()
        except Exception:
            pass
        if r.stderr: log("   "+r.stderr.strip().splitlines()[-1])
        return False
    log(f"   ✓ {name} done"); return True
    _log_step(name, script, True)

def self_update():
    """Sync repo to origin/main so the VM always runs the latest pushed code."""
    try:
        subprocess.run(["git","fetch","--quiet","origin","main"], cwd=REPO, timeout=90)
        subprocess.run(["git","reset","--hard","--quiet","origin/main"], cwd=REPO, timeout=90)
        log("self-update: synced to origin/main")
    except Exception as e:
        log(f"self-update skipped ({e}) — running current code")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--weekly",action="store_true"); a=ap.parse_args()
    log(f"=== LEAN IPO PIPELINE START {datetime.datetime.now():%Y-%m-%d %H:%M} ===")
    self_update()
    kite_ok = preflight()
    if not kite_ok:
        log("⚠️ Kite token stale — SKIPPING Kite-only steps (candles/OHLC). "
            "All non-Kite work (scrape, GMP, SBI, score, consolidated, verdicts) still runs.")

    ok=True
    # ── DISCOVERY + SOURCE-OF-TRUTH ENRICHMENT ──
    # NSE discovery trigger FIRST: a freshly-announced IPO enters ipo_intelligence
    # before enrichment. Dedup-safe (upsert by company_name, RULE 1). Non-hard.
    step("NSE discovery (new IPOs)",        ["ipo/fetch_nse_ipos.py"])
    step("scrape IPO calendar + details",   ["scrape_chittorgarh.py","--write-db"])
    step("anchor + subscription enrich",    ["ipo/enrich_ipo_chittorgarh.py","--auto","--apply"])
    step("IPOMatrix enrich (new IPOs)",     ["ipomatrix_ingest.py","--only-null","--apply"])
    step("IPOMatrix refresh (upcoming drip-feed)", ["ipomatrix_ingest.py","--upcoming","--apply"])
    step("EPS backfill (caution-marked)",   ["backfill_eps_post.py","--apply"])
    step("refresh GMP",                     ["ipo/refresh_gmp.py"])
    step("delivery pct (NSE bhavcopy)",     ["fetch_delivery_bhavcopy.py"])
    step("anchor-deal conviction match",    ["match_anchor_deals.py"])
    step("market regime + VIX (today)",     ["backfill_market_regimes.py"])

    # ── KITE PRICE DATA (skip cleanly if token stale) ──
    if kite_ok:
        step("candles: in-window daily sync", ["sync_inwindow_candles.py"])
        step("candles: full NSE universe",    ["kite-sync-candles.py"])
        step("listing-day fields (kite)",     ["ipo/backfill_ipo_ohlc.py"])
        step("derive listing_open",           ["fill_listing_open_from_candles.py"])
    else:
        log("   ⏭  Kite steps skipped (stale token)")

    # ── SBI RESEARCH NOTES (structured scrape/parse — NOT sent to Sonnet) ──
    step("download SBI notes (new only)",   ["download_sbi_notes.py"])
    step("parse SBI notes -> DB",           ["parse_sbi_notes.py"])
    step("SBI Haiku extract ($0.50 cap)",   ["sbi_haiku_extract.py"])

    # ── RHP forensic (Sonnet, RHP-only) — non-hard, shares the $3/day budget ──
    # rhp_auto self-gates to the remaining daily budget (reads rhp_run_log), so
    # running it in BOTH daily lean runs never exceeds $3/day combined. A Sonnet
    # or SEBI hiccup here must not kill the data pipeline → non-hard.
    step("RHP forensic (Sonnet, $3/day cap)", ["rhp_auto.py", "--apply"])

    # ── COMPUTE (single pass — no duplicate block) ──
    step("ipo score v0 (derived)",          ["ipo_score.py","--apply"])
    step("d10 outcome precompute",          ["compute_d10.py"])
    step("reconcile listing dates",         ["reconcile_listing_dates.py"])
    step("close-in-range strength",         ["close_in_range.py"])
    step("master computables backfill",     ["backfill_master_computables.py"])
    step("sector cleanup",                  ["fix_sectors.py"])
    step("peer PE (self-computed)",         ["compute_peer_pe.py"])          # fair value — KEEP
    step("quality flags (Laser pattern)",   ["compute_quality_flags.py"])

    # ── BUILD + VERDICTS ──
    step("sync issue_details -> intelligence (isin)", ["sync_issue_details.py"])
    ok&=step("rebuild consolidated",        ["build_ipo_consolidated_v2.py"])
    step("compute IPO verdicts (TRADE/WATCH/CAUTION/AVOID)", ["compute_verdicts.py","--apply"])
    step("compute red-flag scanner",        ["compute_flags.py","--apply"])
    step("Quality score (pre-list)",      ["compute_quality_score.py","--apply"])

    # ── JOURNAL + MAINTENANCE ──
    step("sync trade journal (kite orders)", ["sync_trade_journal.py"])
    step("compute journal outcomes",         ["compute_journal_outcomes.py","--apply"])
    step("backup critical tables",           ["backup_critical_tables.py"])
    if a.weekly:
        step("purge post-lock candles",     ["purge_candles_after_lockin.py","--buffer","10","--apply"])
        step("data hygiene (stale purge)",   ["purge_stale_data.py","--apply"])

    # ── HEALTH GATE LAST ──
    gate=step("health-check (gate)",        ["check_data_contract.py"], hard=False)
    step("value-sanity report",             ["check_value_sanity.py"])

    log(f"=== LEAN PIPELINE {'OK' if ok and gate else 'COMPLETED WITH WARNINGS — check log'} ===")
    if ok and gate:
        url = os.environ.get("HEALTHCHECK_URL", "").strip()
        if url:
            try:
                import urllib.request; urllib.request.urlopen(url, timeout=15)
                log("dead-man switch pinged")
            except Exception as e:
                log(f"healthcheck ping failed ({e})")
    sys.exit(0 if ok and gate else 2)

if __name__=="__main__": main()
