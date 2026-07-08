#!/usr/bin/env python3
"""
backfill_anchors_slug.py — fills anchor_names + anchor_count using the AUTHORITATIVE
slug from Chittorgarh list report 82 (~URLRewrite_Folder_Name), then fetching each
IPO's detail page and parsing its AnchorTable. No token, no slug-guessing.

Report 82 (already used by scrape_chittorgarh.py) gives per IPO: real slug,
nse_symbol, detail URL. We match to ipo_intelligence by nse_symbol (name fallback),
fetch the detail page via curl_cffi (chrome impersonation clears the bot wall),
and extract anchor investor names. Fill-empty, resume-safe.

  python _scripts/backfill_anchors_slug.py --years 2024-2026 --limit 8   # test
  python _scripts/backfill_anchors_slug.py --years 2010-2026 --apply     # full
  python _scripts/backfill_anchors_slug.py --test-only                   # backtest
"""
import os, re, sys, json, time, argparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
LIST = ("https://webnodejs.chittorgarh.com/cloud/report/data-read/"
        "82/1/7/{year}/{fy}/0/mainboard/0?search=&v=21-38")

def fetch(url, post=False):
    try:
        from curl_cffi import requests as creq
        return creq.get(url, impersonate="chrome", timeout=35).text
    except ImportError:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": UA,
            "Referer": "https://www.chittorgarh.com/"})
        return urllib.request.urlopen(req, timeout=35).read().decode("utf-8", "replace")

def norm(name):
    s = re.sub(r"<[^>]+>", "", str(name or "")).lower()
    s = re.sub(r"\b(ltd|limited|pvt|private|ipo|the)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def parse_anchors(html):
    mt = re.search(r"id=['\"]AnchorTable['\"].*?</table>", html, re.S)
    names = []
    if mt:
        for am in re.finditer(r'ipo-anchor-list-vs-listing-gain/\d+/\w+/\d+"[^>]*>\s*([^<]+?)\s*</a>', mt.group()):
            n = am.group(1).strip()
            if n and n.lower() not in ("", "na", "-"): names.append(n)
    if not names:  # fallback: anchor section list items
        sec = re.search(r"[Aa]nchor [Ii]nvestor.*?(?:</table>|</ul>|</div>)", html, re.S)
        if sec:
            for m in re.finditer(r'>\s*([A-Z][A-Za-z&.,\s]{4,60}(?:Fund|Trust|LLP|Ltd|Limited|Capital|Investments|MF|Insurance|Mutual|AMC|Advisors|Pte|Inc))\s*<', sec.group()):
                names.append(m.group(1).strip())
    # dedupe preserve order
    seen = set(); out = []
    for n in names:
        if n not in seen: seen.add(n); out.append(n)
    return out

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0)/n*100, s[n//2], sum(rets)/n

def run_backtest(cur):
    cur.execute("""SELECT anchor_count, listing_gap_pct, d10_best_pct
                   FROM ipo_intelligence WHERE anchor_count IS NOT NULL AND d10_best_pct IS NOT NULL""")
    rows = cur.fetchall()
    print(f"\n=== ANCHOR COUNT vs d10 — n={len(rows)} ===")
    if len(rows) < 30:
        print("still <30 with outcomes; backfill more then --test-only."); return
    def b(c): c=int(c); return "1-5" if c<=5 else "6-10" if c<=10 else "11-20" if c<=20 else "20+"
    pooled={}
    for c,g,d in rows: pooled.setdefault(b(c),[]).append(float(d))
    print(f"{'anchors':8}{'n':>5}{'win%':>7}{'med':>7}{'mean':>7}")
    for k in ("1-5","6-10","11-20","20+"):
        st=stats(pooled.get(k,[]))
        if st: print(f"{k:8}{st[0]:>5}{st[1]:>7.1f}{st[2]:>+7.1f}{st[3]:>+7.1f}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2010-2026")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--test-only", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.0)
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    if a.test_only:
        run_backtest(cur); return
    cur.execute("""SELECT id, UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)), company_name, anchor_count
                   FROM ipo_intelligence""")
    by_sym, by_name, have = {}, {}, set()
    for pid, sym, nm, ac in cur.fetchall():
        if sym: by_sym[sym] = pid
        by_name[norm(nm)] = pid
        if ac is not None: have.add(pid)
    if "-" in a.years:
        y0, y1 = map(int, a.years.split("-")); years = range(y0, y1 + 1)
    else:
        years = [int(a.years)]
    filled = fetched = 0
    for year in years:
        fy = f"{year}-{str(year+1)[2:]}"
        try:
            data = json.loads(fetch(LIST.format(year=year, fy=fy)))
        except Exception as e:
            print(f"{year}: list error {e}"); continue
        for row in (data.get("reportTableData") or []):
            sym = str(row.get("~nse_symbol") or "").upper().strip()
            slug = row.get("~URLRewrite_Folder_Name")
            pid = by_sym.get(sym) or by_name.get(norm(row.get("~compare_name") or row.get("~IPO")))
            if not pid or pid in have or not slug: continue
            if a.limit and fetched >= a.limit: break
            fetched += 1
            url = f"https://www.chittorgarh.com/ipo/{slug}/"
            try:
                names = parse_anchors(fetch(url))
            except Exception as e:
                print(f"  {slug}: {e}"); continue
            time.sleep(a.sleep)
            if not names:
                print(f"  {sym or slug}: no anchors parsed"); continue
            filled += 1; have.add(pid)
            print(f"  {(sym or slug):16} anchors={len(names):2}  e.g. {', '.join(names[:3])}")
            if a.apply:
                cur.execute("""UPDATE ipo_intelligence SET
                    anchor_names=COALESCE(anchor_names,%s), anchor_count=COALESCE(anchor_count,%s)
                    WHERE id=%s""", (json.dumps(names), len(names), pid))
        if a.limit and fetched >= a.limit: break
        if a.apply: conn.commit()
        print(f"{year}: filled {filled} (cumulative)")
    print(f"\n{'WROTE' if a.apply else 'DRY'}: {filled} filled / {fetched} fetched")
    run_backtest(cur)
    conn.close()

if __name__ == "__main__":
    main()
