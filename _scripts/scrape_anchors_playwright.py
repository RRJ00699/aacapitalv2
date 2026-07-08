#!/usr/bin/env python3
"""
scrape_anchors_playwright.py — fills anchor_names+count for IPOs IPOMatrix's API
couldn't reach, by RENDERING the IPOMatrix anchor page with Playwright (no JWT).

Resolves each IPO's IPOMatrix id + slug from Chittorgarh report 82 (already used
elsewhere), navigates to ipomatrix.com/ipo/<slug>/<id>/#s-anchor, waits for the
anchor investor table to render, scrapes the investor names. Registrars stay
(the quality backtest filters them). Fill-empty, resume-safe.

Setup (once): pip install playwright ; playwright install chromium
  python _scripts/scrape_anchors_playwright.py --limit 5          # test render
  python _scripts/scrape_anchors_playwright.py --apply            # full
"""
import os, re, sys, json, time, argparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def norm(x):
    x = re.sub(r"<[^>]+>", "", str(x or "")).lower()
    x = re.sub(r"\b(ltd|limited|pvt|private|ipo|the)\b\.?", " ", x)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", x)).strip()

def list_get(url):
    """report 82 via curl_cffi (or urllib) for id+slug resolution."""
    try:
        from curl_cffi import requests as creq
        return json.loads(creq.get(url, impersonate="chrome", timeout=35).text)
    except ImportError:
        import urllib.request as u
        return json.loads(u.urlopen(u.Request(url, headers={"User-Agent": UA}), timeout=35)
                          .read().decode("utf-8", "replace"))

def resolve_ids():
    """symbol/name -> (ipomatrix_id, slug) from report 82, all years."""
    sym, name = {}, {}
    for yr in range(2010, 2027):
        fy = f"{yr}-{str(yr+1)[2:]}"
        try:
            d = list_get(f"https://webnodejs.chittorgarh.com/cloud/report/data-read/"
                         f"82/1/7/{yr}/{fy}/0/mainboard/0?search=&v=21-38")
        except Exception:
            continue
        for row in (d.get("reportTableData") or []):
            m = re.search(r"/ipo/([^/]+)/(\d+)/", str(row.get("Company", "")))
            if not m: continue
            slug, cid = m.group(1), int(m.group(2))
            sy = str(row.get("~nse_symbol") or "").upper().strip()
            if sy: sym[sy] = (cid, slug)
            name[norm(row.get("~compare_name") or row.get("~IPO"))] = (cid, slug)
    return sym, name

def scrape_anchor_names(page, url, timeout_ms):
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    # the anchor section renders after client fetch; wait for a row with an investor
    try:
        page.wait_for_selector("text=/Anchor Investor/i", timeout=15000)
    except Exception:
        pass
    # give the SPA a beat to populate the table
    for _ in range(10):
        html = page.content()
        if re.search(r"(MUTUAL FUND|INSURANCE|FUND|LLP|CAPITAL|Pte)", html):
            break
        time.sleep(0.8)
    html = page.content()
    names = []
    # anchor table rows: first cell = investor name (as in the screenshot list)
    for m in re.finditer(r"<td[^>]*>\s*([A-Z][A-Za-z0-9&.,\-()' ]{4,70})\s*</td>", html):
        v = m.group(1).strip()
        if re.search(r"(FUND|INSURANCE|LLP|CAPITAL|TRUST|MF|Pte|AMC|INVESTMENT|PENSION|"
                     r"MUTUAL|GLOBAL|EMERGING|SECURITIES|ADVISORS|Ltd|LIMITED)", v, re.I):
            names.append(v)
    seen = set(); out = []
    for n in names:
        if n not in seen: seen.add(n); out.append(n)
    return out

def stats(r):
    n=len(r)
    if n<8: return None
    s=sorted(r); return n,sum(1 for x in r if x>0)/n*100,s[n//2],sum(r)/n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--timeout", type=int, default=45000)
    ap.add_argument("--sleep", type=float, default=1.0)
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("""SELECT id, UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)), company_name
                   FROM ipo_intelligence
                   WHERE anchor_count IS NULL AND listing_date IS NOT NULL
                   ORDER BY listing_date DESC""")
    todo = cur.fetchall()
    print(f"IPOs still needing anchors: {len(todo)}")
    print("resolving IPOMatrix ids from report 82...")
    sym_map, name_map = resolve_ids()
    print(f"resolved: {len(sym_map)} by symbol, {len(name_map)} by name")

    from playwright.sync_api import sync_playwright
    filled = fetched = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        page = browser.new_context(user_agent=UA).new_page()
        for pid, sym, nm in todo:
            hit = sym_map.get(sym) or name_map.get(norm(nm))
            if not hit: continue
            if a.limit and fetched >= a.limit: break
            cid, slug = hit
            fetched += 1
            url = f"https://www.ipomatrix.com/ipo/{slug}/{cid}/#s-anchor"
            try:
                names = scrape_anchor_names(page, url, a.timeout)
            except Exception as e:
                print(f"  {sym or slug}: {str(e)[:50]}"); continue
            time.sleep(a.sleep)
            if not names:
                print(f"  {sym or slug}: no anchors rendered"); continue
            filled += 1
            print(f"  {(sym or slug):16} anchors={len(names):2}  e.g. {', '.join(names[:3])}")
            if a.apply:
                cur.execute("""UPDATE ipo_intelligence SET
                    anchor_names=COALESCE(anchor_names,%s), anchor_count=COALESCE(anchor_count,%s)
                    WHERE id=%s""", (json.dumps(names), len(names), pid))
                if fetched % 20 == 0: conn.commit()
        browser.close()
    if a.apply: conn.commit()
    print(f"\n{'WROTE' if a.apply else 'DRY'}: {filled}/{fetched}")
    conn.close()

if __name__ == "__main__":
    main()
