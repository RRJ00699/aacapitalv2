#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wayback_preopen_harvest.py — free recent-data workaround for the pre-open book.

NSE's pre-open page (IPO/Re-listed category) is fed by a JSON API. NSE keeps no
archive, but the Internet Archive's crawler sometimes captured that URL — and a
capture between 09:00–09:58 IST on a listing morning IS a real book snapshot.
This script:
  1. pulls listing dates (2024+) from ipo_intelligence
  2. queries the Wayback CDX API for snapshots of the pre-open API/page in the
     09:00–10:00 IST window (03:30–04:30 UTC) of each listing date
  3. downloads any JSON hits, parses IPO rows (symbol, IEP, buy/sell qty)
  4. previews; --apply INSERTs into ipo_preopen_book with source='backfill-wayback'
READ-ONLY unless --apply. Free. Expect a modest hit rate — every hit is gold.
Run:  python _scripts/wayback_preopen_harvest.py            # preview
      python _scripts/wayback_preopen_harvest.py --apply
"""
import argparse, json, os, sys, time, urllib.request

CDX = "https://web.archive.org/cdx/search/cdx"
TARGETS = [
    "nseindia.com/api/market-data-pre-open*",          # the JSON the page loads
    "nseindia.com/market-data/pre-open-market*",       # the page itself
    "www1.nseindia.com/live_market/dynaContent/live_analysis/pre_open*",  # legacy
]

def http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=40).read()

def listing_dates():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    cur.execute("""SELECT DISTINCT listing_date::date FROM ipo_intelligence
                   WHERE listing_date >= '2024-01-01' AND listing_date < CURRENT_DATE
                   ORDER BY 1""")
    d = [r[0] for r in cur.fetchall()]; conn.close(); return d

def cdx_hits(target, day):
    # 09:00-10:00 IST = 03:30-04:30 UTC on the same date
    frm = day.strftime("%Y%m%d") + "033000"
    to  = day.strftime("%Y%m%d") + "043000"
    q = (f"{CDX}?url={urllib.parse.quote(target)}&from={frm}&to={to}"
         f"&output=json&filter=statuscode:200&limit=20")
    try:
        rows = json.loads(http(q).decode())
        return [(r[1], r[2]) for r in rows[1:]]  # (timestamp, original url)
    except Exception:
        return []

def parse_preopen_json(blob):
    """NSE pre-open API shape: {'data':[{'metadata':{'symbol','lastPrice',
    'totalBuyQuantity','totalSellQuantity',...}}]} — tolerate variants."""
    out = []
    try:
        d = json.loads(blob)
    except Exception:
        return out
    for item in (d.get("data") or []):
        md = item.get("metadata") or item
        sym = (md.get("symbol") or "").upper()
        iep = md.get("lastPrice") or md.get("iep") or md.get("finalPrice")
        bq  = md.get("totalBuyQuantity") or md.get("buyQty")
        sq  = md.get("totalSellQuantity") or md.get("sellQty")
        if sym and (bq or sq):
            out.append((sym, iep, bq, sq))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import urllib.parse  # noqa (used in cdx_hits)
    days = listing_dates()
    print(f"listing dates 2024+: {len(days)} | probing Wayback (be patient, ~1s/query)")
    found = []
    for day in days:
        for tgt in TARGETS:
            for ts, orig in cdx_hits(tgt, day):
                print(f"  HIT {day} {ts} {orig[:80]}")
                try:
                    blob = http(f"https://web.archive.org/web/{ts}id_/{orig}")
                    rows = parse_preopen_json(blob)
                    for sym, iep, bq, sq in rows:
                        lean = (round((float(bq)-float(sq))/float(sq)*100,1)
                                if (bq and sq and float(sq) > 0) else None)
                        found.append((sym, iep, bq, sq, lean, f"{day} 09:45:00+05:30"))
                        print(f"      {sym} iep={iep} buy={bq} sell={sq}")
                except Exception as e:
                    print(f"      fetch/parse failed: {str(e)[:60]}")
            time.sleep(1)  # be polite to archive.org
    print(f"\nparsed book rows: {len(found)}")
    if not found: 
        print("No archived captures in the window — the free well is dry; vendor path stands.")
        return
    if a.apply:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
        for sym, iep, bq, sq, lean, ts in found:
            cur.execute("""INSERT INTO ipo_preopen_book
                (symbol, discovery_price, buy_qty, sell_qty, lean_pct, captured_at, source)
                VALUES (%s,%s,%s,%s,%s,%s,'backfill-wayback')""",
                (sym, iep, bq, sq, lean, ts))
        conn.commit(); conn.close(); print("COMMITTED")
    else:
        print("preview only — rerun with --apply to insert (source='backfill-wayback')")

if __name__ == "__main__":
    main()
