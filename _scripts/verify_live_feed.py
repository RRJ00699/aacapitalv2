#!/usr/bin/env python3
"""
verify_live_feed.py — automated listing-day feed verification (closes the runbook).

Self-arming: exits idle unless an IPO in ipo_intelligence has listing_date = TODAY
(mirrors the launcher's mainboard >=Rs200cr filter). On a listing day it verifies:
  1. writer process alive (kite_ticker_ipo.py)
  2. logs/ticks.log written to in the last 10 min
  3. ipo_tick_feed GROWING (row count sampled 60s apart) + fresh timestamp
  4. ipo_level_analysis refreshed in the last 15 min
Results -> system_health. On ANY fail, GETs $HEALTHCHECK_URL_WATCHDOG/fail
(healthchecks.io instant-alert endpoint) so you get an email within a minute —
no schedule needed for irregular listing days. Timestamp columns are auto-detected
from information_schema (no hardcoded column names).

Cron (09:25 + 13:00 IST, Mon-Fri):
  25 9  * * 1-5 cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/verify_live_feed.py >> logs/verify_feed.log 2>&1
  0  13 * * 1-5 cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/verify_live_feed.py >> logs/verify_feed.log 2>&1
"""
import os, sys, time, datetime, subprocess, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
FAIL_URL = (os.environ.get("HEALTHCHECK_URL_WATCHDOG", "").strip().rstrip("/"))
results = []

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail[:300]))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def ts_col(cur, table):
    """Pick the table's timestamp column from the schema — never guess names."""
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name=%s AND data_type LIKE 'timestamp%%'""", (table,))
    cols = [c for (c,) in cur.fetchall()]
    for pref in ("recorded_at", "created_at", "updated_at", "ts", "timestamp"):
        if pref in cols:
            return pref
    return cols[0] if cols else None

def main():
    if not DB:
        sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
    today = datetime.date.today()
    cur.execute("""SELECT company_name, COALESCE(NULLIF(nse_symbol,''), symbol)
                   FROM ipo_intelligence
                   WHERE listing_date = CURRENT_DATE
                     AND issue_size_cr >= 200 AND issue_size_cr < 100000""")
    listings = cur.fetchall()
    print(f"VERIFY LIVE FEED {today} — listings today: {listings or 'none'}")
    if not listings:
        print("idle — nothing listing today (>=Rs200cr). exit 0.")
        conn.close(); return

    # 1. writer process
    p = subprocess.run(["pgrep", "-f", "kite_ticker_ipo.py"], capture_output=True, text=True)
    check("tick writer process alive", bool(p.stdout.strip()),
          f"pids {p.stdout.split()}" if p.stdout.strip() else "launcher didn't start it — check logs/ticks.log")

    # 2. log freshness
    logp = os.path.join(REPO, "logs", "ticks.log")
    fresh = os.path.exists(logp) and (time.time() - os.path.getmtime(logp)) < 600
    check("ticks.log written <10min", fresh,
          logp if fresh else f"{logp} stale/missing")

    # 3. tick feed growing
    tcol = ts_col(cur, "ipo_tick_feed")
    cur.execute("SELECT COUNT(*) FROM ipo_tick_feed"); n1 = cur.fetchone()[0]
    if tcol:
        cur.execute(f"SELECT MAX({tcol}) FROM ipo_tick_feed"); mx = cur.fetchone()[0]
        recent = mx is not None and (datetime.datetime.now(mx.tzinfo) - mx).total_seconds() < 300
        check("ipo_tick_feed timestamp <5min", recent, f"{tcol} max={mx}")
    print("  ... sampling growth (60s) ...")
    time.sleep(60)
    cur.execute("SELECT COUNT(*) FROM ipo_tick_feed"); n2 = cur.fetchone()[0]
    check("ipo_tick_feed growing", n2 > n1, f"{n1} -> {n2} (+{n2-n1})")

    # 4. levels freshness
    lcol = ts_col(cur, "ipo_level_analysis")
    if lcol:
        cur.execute(f"SELECT MAX({lcol}) FROM ipo_level_analysis"); lm = cur.fetchone()[0]
        lok = lm is not None and (datetime.datetime.now(lm.tzinfo) - lm).total_seconds() < 900
        check("ipo_level_analysis refreshed <15min", lok, f"{lcol} max={lm}")
    else:
        check("ipo_level_analysis has timestamp col", False, "cannot judge freshness")

    # persist + alert
    cur.execute("""CREATE TABLE IF NOT EXISTS system_health (
                     id SERIAL PRIMARY KEY, run_date DATE NOT NULL,
                     check_name TEXT NOT NULL, ok BOOLEAN NOT NULL,
                     detail TEXT, created_at TIMESTAMPTZ DEFAULT now())""")
    for name, ok, detail in results:
        cur.execute("INSERT INTO system_health (run_date, check_name, ok, detail) VALUES (%s,%s,%s,%s)",
                    (today, f"livefeed: {name}", ok, detail))
    conn.commit(); conn.close()

    fails = [n for n, ok, _ in results if not ok]
    if fails:
        print(f"RESULT: {len(fails)} FAIL on a LISTING DAY: {fails}")
        if FAIL_URL:
            try:
                urllib.request.urlopen(FAIL_URL + "/fail", timeout=15)
                print("instant-alert sent via healthchecks /fail")
            except Exception as e:  # noqa: BLE001
                print(f"alert ping failed ({e})")
        sys.exit(1)
    print("RESULT: LIVE FEED VERIFIED — all checks pass on a real listing day.")

if __name__ == "__main__":
    main()
