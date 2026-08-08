#!/usr/bin/env python3
"""
enrich_promoter_holding.py — fills promoter_pre_equity / promoter_holding_post
(and, as a bonus from the same list rows, fresh_cr / ofs_cr) from Chittorgarh.

Walk: report-82 list pages per year -> match rows to ipo_intelligence by
nse_symbol (name fallback) -> fill fresh/ofs from list row -> fetch the IPO
detail page -> parse 'Promoter Holding  <pre>%  <post>%'. Fill-empty only.
Resume-safe: IPOs already having promoter_holding_post are skipped.

  python _scripts/enrich_promoter_holding.py --years 2023 --limit 5      # test
  python _scripts/enrich_promoter_holding.py --years 2010-2026 --apply   # full
"""
import os, re, sys, time, json, argparse, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
LIST = ("https://webnodejs.chittorgarh.com/cloud/report/data-read/"
        "82/{page}/7/{year}/{fy}/0/mainboard/0?search=&v=21-38")

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
        "Referer": "https://www.chittorgarh.com/"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")

def fnum(v):
    try:
        f = float(str(v).replace(",", "").strip())
        return f if f >= 0 else None
    except (TypeError, ValueError):
        return None

def norm(name):
    s = (name or "").lower()
    s = re.sub(r"\b(ltd|limited|pvt|private|ipo)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def parse_promoter(html):
    """Returns (pre_pct, post_pct) from the detail page, or (None, None)."""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt)
    m = re.search(r"Promoter Holding\s+([\d.]+)%\s+([\d.]+)%", txt)
    if m:
        pre, post = float(m.group(1)), float(m.group(2))
        if 0 <= post <= pre <= 100: return pre, post
        if 0 <= pre <= 100 and 0 <= post <= 100: return pre, post
    return None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2010-2026")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if "-" in a.years:
        y0, y1 = map(int, a.years.split("-")); years = range(y0, y1 + 1)
    else:
        years = [int(a.years)]
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("""SELECT id, UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)), company_name,
                          promoter_holding_post, fresh_cr, ofs_cr
                   FROM ipo_intelligence""")
    by_sym, by_name = {}, {}
    for r in cur.fetchall():
        if r[1]: by_sym[r[1]] = r
        by_name[norm(r[2])] = r
    done = fresh_fill = prom_fill = fetched = 0
    for year in years:
        fy = f"{year}-{str(year+1)[2:]}"
        for page in range(1, 61):
            try:
                data = json.loads(get(LIST.format(page=page, year=year, fy=fy)))
            except Exception as e:
                print(f"{year} p{page}: list error {e}"); break
            rows = data.get("reportTableData") or []
            if not rows: break
            for row in rows:
                sym = str(row.get("~nse_symbol") or "").upper().strip()
                rec = by_sym.get(sym) or by_name.get(norm(row.get("~compare_name") or row.get("~IPO")))
                if not rec: continue
                pid, _, _, prom_post, fcr, ocr = rec
                # bonus: fresh/ofs from the list row
                f_new, o_new = fnum(row.get("Fresh Capital (Rs.cr.)")), fnum(row.get("Offer for sale (Rs.cr.)"))
                if a.apply and ((fcr is None and f_new is not None) or (ocr is None and o_new is not None)):
                    cur.execute("""UPDATE ipo_intelligence SET fresh_cr=COALESCE(fresh_cr,%s),
                                   ofs_cr=COALESCE(ofs_cr,%s) WHERE id=%s""", (f_new, o_new, pid))
                    fresh_fill += 1
                if prom_post is not None: continue          # resume-safe
                m = re.search(r'href="(https://www\.chittorgarh\.com/ipo/[^"]+)"', str(row.get("Company", "")))
                if not m: continue
                if a.limit and fetched >= a.limit: break
                fetched += 1
                try:
                    pre, post = parse_promoter(get(m.group(1)))
                except Exception as e:
                    print(f"  {sym}: detail error {e}"); continue
                time.sleep(a.sleep)
                if post is None: continue
                prom_fill += 1
                print(f"  {sym or row.get('~IPO','?'):14} pre={pre}%  post={post}%")
                if a.apply:
                    cur.execute("""UPDATE ipo_intelligence SET
                        promoter_pre_equity=COALESCE(promoter_pre_equity,%s),
                        promoter_holding_post=COALESCE(promoter_holding_post,%s)
                        WHERE id=%s""", (pre, post, pid))
            if a.limit and fetched >= a.limit: break
        if a.limit and fetched >= a.limit: break
        print(f"{year}: done (cumulative promoter={prom_fill}, fresh/ofs rows={fresh_fill})")
    if a.apply: conn.commit()
    print(f"\n{'WROTE' if a.apply else 'DRY (no writes)'}: promoter rows={prom_fill}, "
          f"fresh/ofs rows touched={fresh_fill}, detail pages fetched={fetched}")
    conn.close()

if __name__ == "__main__":
    main()
