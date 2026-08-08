#!/usr/bin/env python3
"""fetch_insider_trades.py — EXPERIMENTAL: NSE insider/promoter (PIT) disclosures
for the IPO universe -> insider_transactions. Same cookie-prime session pattern as
fetch_institutional_deals.py (proven from this VM). Dedup-keyed; prints a RAW
record if fields drift so nothing fails silently.
  venv/bin/python _scripts/fetch_insider_trades.py [--days 60]"""
import os, sys, time, argparse, hashlib, datetime as dt
try:
    import requests, psycopg2
except ImportError:
    sys.exit("use venv/bin/python")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API = "https://www.nseindia.com/api/corporates-pit"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading",
    "Connection": "keep-alive",
}

def get_session():
    s = requests.Session(); s.headers.update(HEADERS)
    s.get("https://www.nseindia.com", timeout=20); time.sleep(1); s.get(HEADERS["Referer"], timeout=20)
    time.sleep(1)
    return s

def num(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return None

def parse_date(v):
    s = str(v or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s[:11].strip(), fmt).date()
        except ValueError:
            continue
    return None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS insider_transactions (
                     id SERIAL PRIMARY KEY, symbol TEXT NOT NULL, company TEXT,
                     person TEXT, person_category TEXT, security_type TEXT,
                     action TEXT, quantity NUMERIC, value_cr NUMERIC,
                     txn_date DATE, mode TEXT, dedup_key TEXT UNIQUE,
                     created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""SELECT DISTINCT UPPER(COALESCE(NULLIF(nse_symbol,''), symbol))
                   FROM ipo_intelligence
                   WHERE COALESCE(NULLIF(nse_symbol,''), symbol) IS NOT NULL""")
    universe = {r[0] for r in cur.fetchall()}
    print(f"IPO universe: {len(universe)} symbols")

    to_d = dt.date.today(); from_d = to_d - dt.timedelta(days=a.days)
    s = get_session()
    r = s.get(API, params={"index": "equities",
                           "from_date": from_d.strftime("%d-%m-%Y"),
                           "to_date": to_d.strftime("%d-%m-%Y")}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"NSE PIT HTTP {r.status_code} — feed blocked/moved (experimental, non-fatal)")
    data = r.json().get("data") or []
    print(f"NSE PIT rows returned: {len(data)}")
    if not data:
        print("0 rows — RAW response head:", str(r.text)[:300]); return

    ins = skip = off = 0
    shown_raw = False
    for d in data:
        sym = (d.get("symbol") or "").strip().upper()
        if sym not in universe:
            off += 1; continue
        row = {
            "symbol": sym, "company": (d.get("company") or "").strip(),
            "person": (d.get("acqName") or d.get("personName") or "").strip(),
            "person_category": (d.get("personCategory") or "").strip(),
            "security_type": (d.get("secType") or "").strip(),
            "action": (d.get("tdpTransactionType") or d.get("acquisitionDisposal") or "").strip(),
            "quantity": num(d.get("secAcq") or d.get("noOfSecurities")),
            "value_cr": (num(d.get("secVal")) or 0) / 1e7 or None,
            "txn_date": parse_date(d.get("date") or d.get("intimDate") or d.get("acqfromDt")),
            "mode": (d.get("acqMode") or "").strip(),
        }
        if not row["person"] and not shown_raw:
            print("RAW record (field-drift check):", {k: d.get(k) for k in list(d)[:12]})
            shown_raw = True
        key = hashlib.md5("|".join(str(row[k]) for k in
              ("symbol", "person", "action", "quantity", "txn_date", "mode")).encode()).hexdigest()
        cur.execute("""INSERT INTO insider_transactions
                       (symbol, company, person, person_category, security_type,
                        action, quantity, value_cr, txn_date, mode, dedup_key)
                       VALUES (%(symbol)s,%(company)s,%(person)s,%(person_category)s,
                               %(security_type)s,%(action)s,%(quantity)s,%(value_cr)s,
                               %(txn_date)s,%(mode)s,%(key)s)
                       ON CONFLICT (dedup_key) DO NOTHING""", {**row, "key": key})
        ins += cur.rowcount; skip += (1 - cur.rowcount)
    conn.commit(); conn.close()
    print(f"insider_transactions: +{ins} new, {skip} dup, {off} outside IPO universe.")

if __name__ == "__main__":
    main()
