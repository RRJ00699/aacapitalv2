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
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); pg=b.new_page()
        pg.goto(URL, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
        rows=pg.eval_on_selector_all("table tr", """els => els.map(r =>
            Array.from(r.querySelectorAll('th,td')).map(c => c.innerText.trim()))""")
        b.close()
    out=[]
    for r in rows:
        if len(r)<3 or not r[0] or r[0].lower().startswith("ipo"): continue
        name=re.sub(r"\s+(BSE SME|NSE SME|IPO).*$","",r[0]).strip()
        gmp=next((re.sub(r"[^\d.-]","",c) for c in r if "₹" in c or re.search(r"\d",c)), "")
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
