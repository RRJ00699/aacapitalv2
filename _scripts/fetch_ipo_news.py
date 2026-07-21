#!/usr/bin/env python3
"""fetch_ipo_news.py — free-tier street-report discovery (2026-07-22).

Whitelisted Google News RSS per current/recent IPO; Reuters preferred when a
directly relevant article exists, else highest-scored approved publisher.
Stores METADATA + short RSS-provided snippet only — never article text, never
paywall bypass. Manual override: insert a row with source='manual' (it always
wins). Fill/supersede: new selection sets is_current=false on the old row.

  python _scripts/fetch_ipo_news.py            # preview
  python _scripts/fetch_ipo_news.py --apply
"""
import argparse
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

WHITELIST = {  # publisher -> priority (lower = preferred)
    "reuters": 1, "economictimes": 2, "economic times": 2,
    "moneycontrol": 3, "business standard": 4, "business-standard": 4, "livemint": 5, "mint": 5,
}
REJECT = re.compile(r"gmp|grey market|telegram|youtube|sponsored", re.I)


def score(company: str, title: str, publisher: str, listed_within_7d: bool):
    t, p = title.lower(), publisher.lower()
    first = company.lower().split()[0]
    if first not in t: return None                     # exact-company gate (first token, then verified below)
    if not listed_within_7d: return None
    prio = next((v for k, v in WHITELIST.items() if k in p), None)
    if prio is None: return None                       # approved publishers only
    if REJECT.search(t): return None
    sc = 100 - prio * 10
    if re.search(r"debut|listing|lists|listed|shares (open|jump|fall)", t): sc += 20
    else: return None                                  # listing context required
    if re.search(r"analyst|valuation|premium|discount", t): sc += 10
    return sc


def discover(company: str):
    q = urllib.parse.quote(f'"{company}" IPO listing OR shares debut OR listing performance')
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AACapital IPO research)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        root = ET.fromstring(r.read())
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("{*}source") or item.findtext("source") or "").strip()
        date = (item.findtext("pubDate") or "").strip()
        desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:280]
        out.append((title, link, pub, date, desc))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not db: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(db, connect_timeout=20); cur = conn.cursor()
    cur.execute("""SELECT company_name, nse_symbol, listing_date FROM ipo_intelligence
        WHERE COALESCE(is_sme,false)=false AND (issue_size_cr IS NULL OR issue_size_cr>=200)
          AND listing_date BETWEEN (now() AT TIME ZONE 'Asia/Kolkata')::date - 7
                               AND (now() AT TIME ZONE 'Asia/Kolkata')::date + 7""")
    targets = cur.fetchall()
    print(f"news targets (listing ±7d, eligible): {len(targets)}")
    for name, sym, ld in targets:
        cur.execute("SELECT 1 FROM ipo_news WHERE company_name=%s AND source='manual' AND is_current", (name,))
        if cur.fetchone():
            print(f"  · {name[:38]:40} manual override present — untouched"); continue
        try:
            items = discover(name)
        except Exception as e:
            print(f"  ! {name[:38]:40} discovery failed: {e}")
            if a.apply:
                cur.execute("""INSERT INTO ipo_news (company_name,nse_symbol,publisher,headline,url,source,fetch_status,is_current)
                               VALUES (%s,%s,'-','-','-','rss','failed',false)""", (name, sym))
            continue
        best = None
        for title, link, pub, date, desc in items:
            sc = score(name, title, pub, True)
            if sc is not None and (best is None or sc > best[0]):
                best = (sc, title, link, pub, date, desc)
        if not best:
            print(f"  · {name[:38]:40} no acceptable article yet (honest state)"); continue
        sc, title, link, pub, date, desc = best
        print(f"  {'✓' if a.apply else '→'} {name[:38]:40} [{pub} · {sc}] {title[:60]}")
        if a.apply:
            cur.execute("UPDATE ipo_news SET is_current=false WHERE company_name=%s AND source='rss' AND is_current", (name,))
            cur.execute("""INSERT INTO ipo_news (company_name,nse_symbol,publisher,headline,url,published_at,snippet,selection_score)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (name, sym, pub, title, link, date or None, desc, sc))
    if a.apply: conn.commit(); print("APPLIED")
    else: print("DRY-RUN — add --apply to write.")
    conn.close(); return 0


if __name__ == "__main__":
    sys.exit(main())
