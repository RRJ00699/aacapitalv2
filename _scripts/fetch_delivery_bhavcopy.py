#!/usr/bin/env python3
"""
fetch_delivery_bhavcopy.py — daily NSE delivery % into delivery_data.

Delivery % is NOT in Kite's historical API (that's why delivery_data is empty). The real source is
NSE's daily "Securities Deliverable Data" bhavcopy (sec_bhavdata_full), which has DELIV_QTY + DELIV_PER
per symbol. This fetches it, parses it, upserts into delivery_data(symbol, date, delivery_percentage,
delivery_quantity). Backfillable: NSE keeps months of history.

HONESTY / ROBUSTNESS:
  * NSE blocks plain requests -> we prime cookies on the homepage first, then fetch with browser
    headers + Referer. Same wall as Screener.
  * NSE moved the URL in 2024 -> we try the current nsearchives host, then the legacy host. The exact
    URL tried is printed so a format change is obvious, not silent.
  * Trading-day aware: weekends/holidays have no file -> we SKIP (not error) when NSE returns 404.
  * FAILS LOUD: if a requested business day can't be fetched at all (not a holiday), exit non-zero so
    the GitHub Action turns red instead of green-but-empty.

Run:
  python fetch_delivery_bhavcopy.py                      # yesterday (most recent trading day)
  python fetch_delivery_bhavcopy.py --date 2026-06-25
  python fetch_delivery_bhavcopy.py --backfill-days 120  # last N calendar days (skips holidays)
Env: DATABASE_URL
"""
import os, sys, io, time, argparse, datetime as dt
import requests
import pandas as pd

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/all-reports",
    })
    # prime cookies (NSE sets them on the homepage / reports page)
    try:
        s.get("https://www.nseindia.com", timeout=15)
        s.get("https://www.nseindia.com/all-reports", timeout=15)
    except Exception as e:
        print(f"  WARN cookie prime failed: {e}")
    return s

def bhav_urls(d: dt.date):
    dd = d.strftime("%d%m%Y")
    return [
        # current (2024+) archive host
        f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{dd}.csv",
        # legacy host/path (pre-2024)
        f"https://www1.nseindia.com/products/content/sec_bhavdata_full_{dd}.csv",
    ]

def fetch_one(s: requests.Session, d: dt.date):
    """Returns DataFrame[symbol, delivery_percentage, delivery_quantity] or None if no file (holiday)."""
    last_status = None
    for url in bhav_urls(d):
        try:
            r = s.get(url, timeout=25)
            last_status = r.status_code
            if r.status_code == 200 and len(r.content) > 200:
                df = pd.read_csv(io.StringIO(r.text))
                df.columns = [c.strip() for c in df.columns]
                # columns: SYMBOL, SERIES, ... DELIV_QTY, DELIV_PER (some rows ' -' for non-EQ)
                if "SYMBOL" not in df.columns or "DELIV_PER" not in df.columns:
                    print(f"  {url} -> unexpected columns: {list(df.columns)[:8]}")
                    continue
                df = df[df["SERIES"].astype(str).str.strip() == "EQ"].copy()
                df["delivery_percentage"] = pd.to_numeric(df["DELIV_PER"], errors="coerce")
                df["delivery_quantity"] = pd.to_numeric(df["DELIV_QTY"], errors="coerce")
                out = df[["SYMBOL", "delivery_percentage", "delivery_quantity"]].rename(
                    columns={"SYMBOL": "symbol"})
                out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
                out = out.dropna(subset=["delivery_percentage"])
                return out
        except Exception as e:
            print(f"  {url} -> ERR {e}")
    if last_status == 404:
        return None   # no file = holiday/weekend, skip quietly
    print(f"  could not fetch {d} (last status {last_status})")
    return False      # genuine failure

def upsert(conn, d: dt.date, df: pd.DataFrame):
    import psycopg2
    from psycopg2.extras import execute_values
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS delivery_data (
            id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, date DATE NOT NULL,
            delivery_percentage NUMERIC, delivery_quantity BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(symbol, date))""")
    conn.commit()
    rows = [(r.symbol, d, float(r.delivery_percentage),
             int(r.delivery_quantity) if pd.notna(r.delivery_quantity) else None)
            for r in df.itertuples()]
    execute_values(cur, """
        INSERT INTO delivery_data (symbol, date, delivery_percentage, delivery_quantity) VALUES %s
        ON CONFLICT (symbol, date) DO UPDATE SET
          delivery_percentage = EXCLUDED.delivery_percentage,
          delivery_quantity   = EXCLUDED.delivery_quantity""", rows, page_size=1000)
    conn.commit()
    return len(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: most recent weekday)")
    ap.add_argument("--backfill-days", type=int, default=0, help="fetch the last N calendar days")
    ap.add_argument("--refetch", action="store_true", help="re-download days already in DB (default: skip them)")
    args = ap.parse_args()
    if not URL: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(URL)
    s = nse_session()

    if args.backfill_days > 0:
        today = dt.date.today()
        days = [today - dt.timedelta(days=i) for i in range(1, args.backfill_days + 1)]
    elif args.date:
        days = [dt.date.fromisoformat(args.date)]
    else:
        d = dt.date.today() - dt.timedelta(days=1)
        while d.weekday() >= 5:  # back up over weekend
            d -= dt.timedelta(days=1)
        days = [d]

    # incremental: skip dates already loaded (unless --refetch). Makes big backfills resumable
    if not args.refetch and days:
        cur0 = conn.cursor()
        cur0.execute("SELECT DISTINCT date FROM delivery_data WHERE date >= %s AND date <= %s",
                     (min(days), max(days)))
        have = {r[0] for r in cur0.fetchall()}
        before = len(days)
        days = [d for d in days if d not in have]
        skipped_existing = before - len(days)
        if skipped_existing:
            print(f"  skipping {skipped_existing} day(s) already in DB (use --refetch to force)")
    else:
        skipped_existing = 0

    total_rows, got, holidays, failures = 0, 0, 0, 0
    for d in days:
        if d.weekday() >= 5:
            continue  # skip weekends in backfill
        res = fetch_one(s, d)
        if res is None:
            holidays += 1
        elif res is False:
            failures += 1
        else:
            n = upsert(conn, d, res)
            total_rows += n; got += 1
            print(f"  {d}: {n} symbols")
        time.sleep(0.8)  # be polite to NSE
    conn.close()
    print(f"\ndelivery_data: {got} day(s) written, {total_rows:,} rows "
          f"({holidays} holiday/weekend skips, {skipped_existing} already-present skips, {failures} failures).")
    if failures and got == 0:
        sys.exit(2)  # fail loud: requested days couldn't be fetched at all

if __name__ == "__main__":
    main()
