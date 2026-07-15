#!/usr/bin/env python3
"""
scrape_investorgain_gmp.py — daily GMP from InvestorGain → ipo_gmp table (golden-rule upsert).
GMP is CONTEXT, not a signal (non-predictive in our backtest) — stored for tracking/hype only.

  pip install playwright psycopg2-binary --break-system-packages ; python -m playwright install chromium
  python _scripts\\scrape_investorgain_gmp.py            # dry-run (prints rows)
  python _scripts\\scrape_investorgain_gmp.py --write-db
"""
import argparse, os, re, sys, datetime
URL="https://www.investorgain.com/report/live-ipo-gmp/331/"

def scrape():
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); pg=b.new_page()
        # domcontentloaded is robust: networkidle waits for ALL network to go quiet,
        # which ad/analytics-heavy pages like investorgain rarely do -> 60s timeout.
        # Instead: load the DOM, then explicitly wait for the data table to appear.
        last_err=None
        for attempt in range(2):
            try:
                pg.goto(URL, wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_selector("table tr", timeout=20000)  # the data is here
                pg.wait_for_timeout(1500)                        # let rows settle
                last_err=None
                break
            except PWTimeout as e:
                last_err=e
                pg.wait_for_timeout(2000)                        # brief backoff, retry once
        if last_err:
            b.close()
            raise SystemExit("GMP scrape: investorgain unreachable/slow (2 attempts) — "
                             "context-only data, skipping this run.")
        rows=pg.eval_on_selector_all("table tr", """els => els.map(r =>
            Array.from(r.querySelectorAll('th,td')).map(c => c.innerText.trim()))""")
        b.close()
    out=[]
    for r in rows:
        if len(r)<3 or not r[0] or r[0].lower().startswith("ipo"): continue
        # header/sort rows scraped as data ("NAME \u25b2 \u25bc" reached ipo_gmp 07-15)
        if re.match(r"\s*name\b", r[0], re.I) or "\u25b2" in r[0] or "\u25bc" in r[0]: continue
        name=re.sub(r"\s+(BSE SME|NSE SME|IPO).*$","",r[0]).strip()
        # extract ONE valid signed decimal — never char-strip (char-stripping turned
        # "-- (-0.00%)" into the '--0.0000' poison that crashed the 07-15 nightly,
        # and would concatenate "₹85 (44.74%)" into "8544.74")
        def _first_num(c):
            m=re.search(r"-?\d+(?:\.\d+)?", c.replace(",",""))
            return m.group(0) if m else ""
        gmp=next((_first_num(c) for c in r if "₹" in c and _first_num(c)), "") \
            or next((_first_num(c) for c in r if _first_num(c)), "")
        est=next((c for c in r if "%" in c), "")
        out.append({"company":name,"raw":" | ".join(r),"gmp":gmp,"est_listing":est})
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--write-db",action="store_true"); a=ap.parse_args()
    try: import psycopg2  # noqa
    except ImportError: sys.exit("pip install playwright psycopg2-binary --break-system-packages")
    data=scrape(); today=datetime.date.today()
    print(f"scraped {len(data)} GMP rows")
    for d in data[:10]: print("  ",d["company"][:34], d["gmp"], d["est_listing"])
    if not a.write_db: print("\ndry-run — add --write-db to upsert into ipo_gmp."); return
    import psycopg2
    conn=psycopg2.connect(os.getenv("DATABASE_URL")); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ipo_gmp(
        company text, date date, gmp text, est_listing text, raw text,
        PRIMARY KEY(company,date))""")
    n=0
    for d in data:
        cur.execute("""INSERT INTO ipo_gmp(company,date,gmp,est_listing,raw)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(company,date) DO UPDATE
            SET gmp=EXCLUDED.gmp, est_listing=EXCLUDED.est_listing, raw=EXCLUDED.raw""",
            (d["company"],today,d["gmp"],d["est_listing"],d["raw"])); n+=cur.rowcount
    conn.commit(); print(f"✓ upserted {len(data)} GMP rows for {today}")

if __name__=="__main__": main()
