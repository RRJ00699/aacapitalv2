#!/usr/bin/env python3
"""
scrape_chittorgarh.py — hands-off Chittorgarh calendar scraper (replaces the manual
--file export drop). Playwright clears Cloudflare, then reads the clean JSON calendar
API per year and upserts raw IPO facts into ipo_intelligence.
Rule 1: raw scraped facts are FILL-EMPTY-ONLY (COALESCE), value-sanity BEFORE the write.
  python _scripts/scrape_chittorgarh.py --year 2026            # DRY-RUN
  python _scripts/scrape_chittorgarh.py --year 2026 --write-db
  python _scripts/scrape_chittorgarh.py --from 2010 --to 2026 --write-db
Needs Playwright chromium + DATABASE_URL.
"""
import os, sys, re, argparse, datetime, json
API = ("https://webnodejs.chittorgarh.com/cloud/report/data-read/82/1/7/"
       "{year}/{fy}/0/mainboard/0?search=&v=21-38")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
def fy(year): return f"{year}-{str(year+1)[-2:]}"
def clean(s):
    if s is None: return None
    return re.sub(r"<[^>]+>", "", str(s)).replace("&amp;", "&").strip() or None
def num(s):
    if s is None: return None
    s = re.sub(r"[^0-9.\-]", "", str(s))
    try: return float(s) if s not in ("", "-", ".") else None
    except: return None
def parse_date(s):
    if not s: return None
    s = str(s).strip()
    for f in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
        try: return datetime.datetime.strptime(s, f).date()
        except Exception: pass
    return None
def fetch_year(page, year):
    url = API.format(year=year, fy=fy(year))
    js = """async (u) => { const r = await fetch(u, {headers:{'Accept':'application/json'}});
            return {status:r.status, text: await r.text()}; }"""
    res = page.evaluate(js, url)
    if res["status"] != 200:
        print(f"  {year}: HTTP {res['status']}"); return []
    try: data = json.loads(res["text"])
    except Exception as e: print(f"  {year}: bad JSON ({e})"); return []
    rows = data.get("reportTableData") or []
    out = []
    for r in rows:
        rec = {
            "company":      clean(r.get("Company")),
            "nse_symbol":   clean(r.get("~nse_symbol")),
            "isin":         clean(r.get("~isin")),
            "bse_code":     clean(r.get("~bse_script_code")),
            "slug":         clean(r.get("~URLRewrite_Folder_Name")),
            "open_date":    parse_date(r.get("~Issue_Open_Date") or r.get("Opening Date")),
            "close_date":   parse_date(r.get("~IssueCloseDate") or r.get("Closing Date")),
            "listing_date": parse_date(r.get("~ListingDate") or r.get("Listing Date")),
            "issue_price":  num(r.get("Issue Price (Rs.)")),
            "issue_size_cr":num(r.get("Total Issue Amount (Incl.Firm reservations) (Rs.cr.)")),
        }
        if rec["company"]: out.append(rec)
    return out
def sane(rec):
    p = rec["issue_price"]
    if p is not None and (p <= 0 or p > 100000): rec["issue_price"] = None
    z = rec["issue_size_cr"]
    if z is not None and z < 0: rec["issue_size_cr"] = None
    ld = rec["listing_date"]
    if ld and (ld.year < 2005 or ld > datetime.date.today() + datetime.timedelta(days=120)):
        rec["listing_date"] = None
    if rec["open_date"] and rec["close_date"] and rec["open_date"] > rec["close_date"]:
        rec["open_date"] = rec["close_date"] = None
    return rec
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int); ap.add_argument("--from", dest="frm", type=int)
    ap.add_argument("--to", type=int); ap.add_argument("--write-db", action="store_true")
    a = ap.parse_args()
    years = [a.year] if a.year else list(range(a.frm or 2010, (a.to or datetime.date.today().year) + 1))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright --break-system-packages ; python -m playwright install chromium")
    all_rows = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        page = b.new_context(user_agent=UA).new_page()
        page.goto("https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/",
                  wait_until="domcontentloaded", timeout=90000)
        for _ in range(15):
            if "just a moment" not in page.title().lower(): break
            page.wait_for_timeout(1500)
        for y in years:
            rows = [sane(r) for r in fetch_year(page, y)]
            print(f"  {y}: {len(rows)} IPOs"); all_rows += rows
        b.close()
    print(f"\ntotal: {len(all_rows)} IPO rows across {len(years)} year(s)")
    for r in all_rows[:6]:
        print(f"  {(r['company'] or '')[:34]:34} {r['nse_symbol'] or '-':10} "
              f"open={r['open_date']} list={r['listing_date']} price={r['issue_price']} size={r['issue_size_cr']}")
    if not a.write_db:
        print("\nDRY-RUN — add --write-db to persist (fill-empty-only)."); return
    import psycopg2
    u = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL")
    conn = psycopg2.connect(u); cur = conn.cursor()
    for col, typ in [("isin","text"),("bse_code","text"),("chittorgarh_slug","text")]:
        cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
    ins = upd = 0
    for r in all_rows:
        row = None
        if r["nse_symbol"]:
            cur.execute("SELECT id FROM ipo_intelligence WHERE nse_symbol=%s LIMIT 1", (r["nse_symbol"],))
            row = cur.fetchone()
        if not row:
            cur.execute("SELECT id FROM ipo_intelligence WHERE lower(company_name)=lower(%s) LIMIT 1", (r["company"],))
            row = cur.fetchone()
        if row:
            cur.execute("""UPDATE ipo_intelligence SET
                nse_symbol=COALESCE(nse_symbol,%s), isin=COALESCE(isin,%s), bse_code=COALESCE(bse_code,%s),
                chittorgarh_slug=COALESCE(chittorgarh_slug,%s), open_date=COALESCE(open_date,%s),
                close_date=COALESCE(close_date,%s), listing_date=COALESCE(listing_date,%s),
                issue_price=COALESCE(issue_price,%s), issue_size_cr=COALESCE(issue_size_cr,%s)
                WHERE id=%s""",
                (r["nse_symbol"], r["isin"], r["bse_code"], r["slug"], r["open_date"], r["close_date"],
                 r["listing_date"], r["issue_price"], r["issue_size_cr"], row[0]))
            upd += cur.rowcount
        else:
            cur.execute("""INSERT INTO ipo_intelligence
                (company_name, nse_symbol, isin, bse_code, chittorgarh_slug,
                 open_date, close_date, listing_date, issue_price, issue_size_cr, chittorgarh_imported)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true) ON CONFLICT DO NOTHING""",
                (r["company"], r["nse_symbol"], r["isin"], r["bse_code"], r["slug"],
                 r["open_date"], r["close_date"], r["listing_date"], r["issue_price"], r["issue_size_cr"]))
            ins += cur.rowcount
    conn.commit()
    print(f"\nchittorgarh: {ins} new IPOs inserted, {upd} existing rows fill-empty updated.")
if __name__ == "__main__": main()
