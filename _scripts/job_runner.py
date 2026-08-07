#!/usr/bin/env python3
"""
_scripts/job_runner.py — the VM side of the Admin job console.
Runs every minute via cron. Checks Neon for queued jobs, runs the whitelisted script,
writes status + log tail + error back to Neon. The web app only ever touches Neon —
never the server. Secure by default (no open ports).

Cron: * * * * * cd $AAC && set -a && . ./.env && set +a && venv/bin/python _scripts/job_runner.py >> logs/jobs.log 2>&1
"""
import os, sys, subprocess, datetime, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)

# ── Neon-cost throttle (Rakesh 2026-07-17: endpoint never slept; this poller
# was the ~6 CU-h/day idle bill). Cron stays * * * * * for 1-minute pickup in
# the ACTIVE window; outside it we exit BEFORE any DB import/connect except on
# :00/:10/:20/:30/:40/:50 — 10-min gaps let the 5-min autosuspend actually fire.
# ACTIVE: Mon-Sat 07:00-23:30 IST (admin hours + full market day).
def _throttled():
    now_ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    active = now_ist.weekday() < 6 and (7 <= now_ist.hour < 23 or (now_ist.hour == 23 and now_ist.minute <= 30))
    return (not active) and now_ist.minute % 10 != 0

def _flag_pending():
    """Ask the Worker's KV flag (ZERO Neon contact) whether any job is queued.
    True/False, or None when unreachable/misconfigured (falls back to the
    time-throttled DB poll below)."""
    key = os.getenv("ADMIN_JOB_KEY", "")
    if not key:
        return None
    try:
        import urllib.request, json as _j
        req = urllib.request.Request(
            "https://aacapitalprivatelimited.com/api/admin/job-flag",
            # UA required: Cloudflare bot protection 403s the default
            # Python-urllib UA from datacenter IPs — this exact miss kept the
            # flag check failing -> minute-cadence DB polls -> the 147 CU-h
            # month (diagnosed 2026-07-18; smoke_probe passed because it
            # always sent a UA).
            headers={"X-AAC-Key": key, "User-Agent": "aac-runner"})
        d = _j.load(urllib.request.urlopen(req, timeout=10))
        return bool(d.get("pending")) if d.get("ok") else None
    except Exception:
        return None

def _should_exit_idle():
    """A4 idle gate: True = exit NOW, before psycopg2 import / any Neon contact.
    Flag says no jobs -> exit any hour. Flag unreachable -> night/weekend
    throttle (only :00/:10/... minutes poll)."""
    _p = _flag_pending()
    if _p is False:
        return True       # no jobs queued: Neon never touched, any hour
    if _p is None and _throttled():
        return True       # flag unavailable: night/weekend throttle applies
    return False

if __name__ == "__main__" and _should_exit_idle():
    sys.exit(0)

import psycopg2

def _clear_flag():
    key = os.getenv("ADMIN_JOB_KEY", "")
    if not key: return
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://aacapitalprivatelimited.com/api/admin/job-flag",
            headers={"X-AAC-Key": key, "User-Agent": "aac-runner"}, method="DELETE")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


DB = os.getenv("DATABASE_URL")

# WHITELIST — the only commands the UI can trigger. Add here to expose a new button.
# IPO Power House — IPO-focused jobs only.
# Removed: theses (script deleted), exit_backtest/base_backtest/convergence (old
# experiments), screener_* (the Screener side-quest), coverage/universe_backfill
# (one-time backfills). Keep the daily flow IPO-only.
JOBS = {
    # 2026-07-21: run_ipo_pipeline.py is RETIRED (prints a banner + exit 1 —
    # the owner hit exactly this from Admin). The lean pipeline IS production.
    "pipeline":        ["_scripts/run_ipo_pipeline_lean.py"],
    "pipeline_weekly": ["_scripts/run_ipo_pipeline_lean.py", "--weekly"],
    "ipo_lifecycle":   ["pipeline/nse_lifecycle.py", "--write"],
    "news":            ["_scripts/fetch_ipo_news.py", "--apply"],
    "consolidate":     ["compatibility/consolidated/consolidate_master.py", "--apply"],
    "peer_pe_notes":   ["_scripts/derive_peer_pe_from_notes.py", "--apply"],
    "peer_pe":         ["_scripts/fetch_peer_pe.py", "--apply"],
    "vm_verify":       ["_scripts/vm_verify.py"],
    "token":           ["_scripts/refresh_kite_token.py"],
    "gmp":             ["_scripts/scrape_investorgain_gmp.py", "--write-db"],
    "sbi_download":    ["_scripts/download_sbi_notes.py", "--out", "data/research_notes"],
    "sbi_parse":       ["_scripts/parse_sbi_notes.py", "--dir", "data/research_notes", "--write-db"],
    "rhp_auto":         ["_scripts/rhp_auto.py", "--apply"],
    "ipomatrix":        ["_scripts/ipomatrix_ingest.py", "--only-null", "--apply"],
    "breadth":         ["_scripts/market_breadth.py", "--apply"],
    "sync":            ["_scripts/git_sync.py"],
    # Mobile-first ops (2026-07-18): the derived layer could only be recomputed
    # by running the WHOLE pipeline. These let the phone re-run one stage after a
    # fix, without a laptop. All are idempotent (UPDATE-in-place / ON CONFLICT).
    "verdicts":        ["_scripts/compute_verdicts.py", "--apply"],
    "score":           ["_scripts/ipo_score.py", "--apply"],
    "quality":         ["_scripts/compute_quality_score.py", "--apply"],
    "schema":          ["_scripts/schema_sync.py"],
    "smoke":           ["_scripts/smoke_probe.py"],
    "sbi_haiku":       ["_scripts/sbi_haiku_extract.py"],
}

def ensure_table(cur):
    """Compatibility sentinel for tools which delimit the job catalog here.

    Schema provisioning is explicit; this no-op is deliberately never called.
    """
    return None

def claim_one(cur):
    # atomic claim so two runners never double-execute
    cur.execute("""
        UPDATE job_runs SET status='running', started_at=now()
        WHERE id = (SELECT id FROM job_runs WHERE status='queued'
                    ORDER BY requested_at LIMIT 1 FOR UPDATE SKIP LOCKED)
        RETURNING id, job""")
    return cur.fetchone()

def run_job(job):
    cmd = JOBS.get(job)
    if not cmd:
        return 2, "", f"unknown job '{job}' (not in whitelist)"
    p = subprocess.run([sys.executable] + cmd, cwd=REPO, capture_output=True, text=True, timeout=6*3600)
    out = ((p.stdout or "") + ("\n" + p.stderr if p.stderr else "")).strip()
    tail = "\n".join(out.splitlines()[-60:])          # last 60 lines
    err = None
    if p.returncode != 0:
        errlines = (p.stderr or out).strip().splitlines()
        err = errlines[-1] if errlines else f"exit {p.returncode}"
    return p.returncode, tail, err

def main():
    if not DB:
        print("no DATABASE_URL"); return
    conn = psycopg2.connect(DB); conn.autocommit = False; cur = conn.cursor()
    processed = 0
    while True:
        claimed = claim_one(cur); conn.commit()
        if not claimed:
            # QUEUE EMPTY -> clear the KV flag. _clear_flag() was defined but
            # NEVER CALLED (2026-07-18): the flag read pending:true forever, so
            # this minute-cron runner opened a Neon connection EVERY MINUTE and
            # the scale-to-zero design was silently defeated.
            _clear_flag()
            break
        jid, job = claimed
        try:
            code, tail, err = run_job(job)
            cur.execute("""UPDATE job_runs SET status=%s, finished_at=now(),
                           exit_code=%s, error=%s, log_tail=%s WHERE id=%s""",
                        ("done" if code == 0 else "failed", code, err, tail, jid))
        except Exception as e:
            cur.execute("""UPDATE job_runs SET status='failed', finished_at=now(),
                           exit_code=-1, error=%s, log_tail=%s WHERE id=%s""",
                        (str(e)[:300], traceback.format_exc()[-2000:], jid))
        conn.commit(); processed += 1
    conn.close()
    if processed: print(f"{datetime.datetime.now():%H:%M} ran {processed} job(s)")

if __name__ == "__main__":
    main()
