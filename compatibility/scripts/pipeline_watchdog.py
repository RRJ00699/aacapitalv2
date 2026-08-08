#!/usr/bin/env python3
"""
pipeline_watchdog.py — catches SILENT failures. Runs at 17:00 IST (1h after the
nightly), independent of the pipeline, so a pipeline that never started is caught too.

Checks:
  1. today's pipeline log exists and contains 'PIPELINE OK'
  2. data freshness: market_regimes covers the last trading day; price_candles
     max date within 5 days; ipo_intelligence has a future-or-recent listing row
  3. writes one row per check to system_health (created if missing) -> visible
     in Neon / admin console
  4. DEAD-MAN'S SWITCH: on all-pass, pings $HEALTHCHECK_URL_WATCHDOG (healthchecks.io).
     If this script crashes, the VM dies, or cron breaks, the ping goes missing and
     healthchecks emails you. Silence itself becomes the alarm.

  venv/bin/python _scripts/pipeline_watchdog.py     # exit 0 all-pass, 1 otherwise
"""
import os, sys, datetime, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
PING = os.environ.get("HEALTHCHECK_URL_WATCHDOG", "").strip()
results = []

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail[:300]))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def last_trading_day(today):
    d = today - datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d

def main():
    today = datetime.date.today()
    print(f"WATCHDOG {today}")
    # 1. pipeline log
    logp = os.path.join(HERE, "logs", f"pipeline_{today}.log")
    if os.path.exists(logp):
        txt = open(logp, encoding="utf-8", errors="ignore").read()
        check("pipeline ran + OK today", "PIPELINE OK" in txt,
              "" if "PIPELINE OK" in txt else "log exists but no 'PIPELINE OK' — open it")
    else:
        check("pipeline ran + OK today", False, f"no log at {logp} — cron/VM problem")
    # 2. data freshness
    if not DB:
        check("DATABASE_URL", False)
    else:
        try:
            import psycopg2
            conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
            ltd = last_trading_day(today)
            cur.execute("SELECT MAX(evaluation_date) FROM market_regimes")
            mr = cur.fetchone()[0]
            check("market_regimes fresh", mr is not None and mr >= ltd - datetime.timedelta(days=2),
                  f"max={mr} (last trading day {ltd})")
            cur.execute("SELECT MAX(date) FROM price_candles")
            pc = cur.fetchone()[0]
            check("price_candles fresh", pc is not None and (today - pc).days <= 5, f"max={pc}")
            cur.execute("""SELECT COUNT(*) FROM ipo_intelligence
                           WHERE listing_date >= CURRENT_DATE - 30""")
            n = cur.fetchone()[0]
            check("calendar has recent/upcoming IPOs", n > 0, f"{n} rows (30d window)")
            # 3. persist
            cur.execute("""CREATE TABLE IF NOT EXISTS system_health (
                             id SERIAL PRIMARY KEY, run_date DATE NOT NULL,
                             check_name TEXT NOT NULL, ok BOOLEAN NOT NULL,
                             detail TEXT, created_at TIMESTAMPTZ DEFAULT now())""")
            cur.execute("DELETE FROM system_health WHERE run_date < CURRENT_DATE - 60")
            for name, ok, detail in results:
                cur.execute("""INSERT INTO system_health (run_date, check_name, ok, detail)
                               VALUES (%s,%s,%s,%s)""", (today, name, ok, detail))
            conn.commit(); conn.close()
        except Exception as e:  # noqa: BLE001
            check("DB reachable", False, str(e)[:150])
    fails = [n for n, ok, _ in results if not ok]
    if fails:
        print(f"RESULT: {len(fails)} FAIL: {fails} — NOT pinging dead-man switch (you'll be alerted).")
        sys.exit(1)
    if PING:
        try:
            urllib.request.urlopen(PING, timeout=15)
            print("RESULT: ALL PASS — dead-man switch pinged.")
        except Exception as e:  # noqa: BLE001
            print(f"RESULT: ALL PASS but ping failed ({e}) — healthchecks will alert; that's the point.")
    else:
        print("RESULT: ALL PASS. (Set HEALTHCHECK_URL_WATCHDOG in .env for email-on-silence.)")

if __name__ == "__main__":
    main()
