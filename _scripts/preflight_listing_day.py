#!/usr/bin/env python3
"""
preflight_listing_day.py — ONE command that proves listing-day readiness. READ-ONLY.

Checks (PASS/FAIL each, exit 1 if any FAIL):
  1. env: DATABASE_URL present
  2. deps: psycopg2 / playwright / rapidfuzz importable in this python
  3. Kite token valid (same check the pipeline preflight uses)
  4. upcoming IPOs (listing_date within 14 days) have nse_symbol set
     — flags <Rs200cr ones the launcher's --auto-today filter will skip
  5. files: ipo_live_launcher.py, ipo/kite_ticker_ipo.py, ipo/analyze_listing_day.py
  6. tables exist: ipo_tick_feed, ipo_level_analysis
  7. crontab has: launcher (09:10 M-F), token refresh, nightly pipeline

  venv/bin/python _scripts/preflight_listing_day.py
"""
import os, sys, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
results = []

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

print("LISTING-DAY PREFLIGHT")
print("=" * 60)

# 1. env
db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
check("DATABASE_URL set", bool(db), "" if db else "run: set -a && . ./.env && set +a")

# 2. deps
for mod in ("psycopg2", "playwright", "rapidfuzz"):
    try:
        __import__(mod); check(f"import {mod}", True)
    except ImportError:
        check(f"import {mod}", False, "wrong python? use venv/bin/python")

# 3. kite token
try:
    sys.path.insert(0, HERE)
    from kite_connect import get_kite
    prof = get_kite().profile()
    check("Kite token valid", True, f"user {prof.get('user_id','?')}")
except Exception as e:  # noqa: BLE001
    check("Kite token valid", False, f"{e} — run refresh_kite_token.py")

# 4-6. DB checks
if db:
    try:
        import psycopg2
        conn = psycopg2.connect(db, connect_timeout=15); cur = conn.cursor()
        cur.execute("""SELECT company_name, nse_symbol, listing_date, issue_size_cr
                       FROM ipo_intelligence
                       WHERE listing_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 14
                       ORDER BY listing_date""")
        rows = cur.fetchall()
        if not rows:
            check("upcoming IPOs (14d)", True, "none scheduled — launcher will idle-exit (normal)")
        else:
            missing = [r[0] for r in rows if not (r[1] or "").strip()]
            small = [f"{r[0]} ({r[3] or '?'}cr)" for r in rows if r[3] is not None and r[3] < 200]
            for r in rows:
                print(f"      • {r[0][:40]:40} sym={r[1] or 'MISSING'} lists {r[2]} size={r[3]}cr")
            check("upcoming IPOs have nse_symbol", not missing,
                  f"MISSING symbol: {missing}" if missing else f"{len(rows)} IPO(s) ready")
            if small:
                print(f"      note: <200cr, launcher --auto-today will SKIP: {small}")
        for t in ("ipo_tick_feed", "ipo_level_analysis"):
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (t,))
            check(f"table {t} exists", bool(cur.fetchone()))
        conn.close()
    except Exception as e:  # noqa: BLE001
        check("DB reachable", False, str(e)[:120])

# 5. files
for f in ("ipo_live_launcher.py", os.path.join("ipo", "kite_ticker_ipo.py"),
          os.path.join("ipo", "analyze_listing_day.py")):
    check(f"file _scripts/{f}", os.path.exists(os.path.join(HERE, f)))

# 7. crontab
try:
    ct = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    check("cron: live launcher", "ipo_live_launcher" in ct)
    check("cron: token refresh", "refresh_kite_token" in ct)
    check("cron: nightly pipeline", "run_ipo_pipeline" in ct)
except Exception as e:  # noqa: BLE001
    check("crontab readable", False, str(e)[:80])

print("=" * 60)
fails = [n for n, ok, _ in results if not ok]
if fails:
    print(f"RESULT: {len(fails)} FAIL — fix before listing day: {fails}")
    sys.exit(1)
print(f"RESULT: ALL {len(results)} CHECKS PASS — listing-day ready. "
      f"On the day: tail -f logs/ticks.log and watch ipo_tick_feed grow.")
