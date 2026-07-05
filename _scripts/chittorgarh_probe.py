#!/usr/bin/env python3
"""
chittorgarh_probe.py — READ-ONLY diagnostic. No DB writes.

Answers two questions with raw evidence:
  1. Which URL slot (if any) controls the result window/pagination?
     (base returns only ~5 rows for past years; 2026 returns 30)
  2. What are the EXACT keys and value formats in reportTableData rows?
     (v2's date parsing returned None — the real keys/formats differ)

Prints, per URL variant: row count, first & last company, min/max open-date-ish
value. Then one FULL raw row (json) for 2021 and the response's top-level keys.

  venv/bin/python _scripts/chittorgarh_probe.py
"""
import json, re, sys, time

BASE = "https://webnodejs.chittorgarh.com/cloud/report/data-read/{a}/{b}/{c}/{year}/{fy}/{m}/mainboard/{p}?search=&v=21-38"
WARMUP = "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def url(year, fy, a=82, b=1, c=7, m=0, p=0):
    return BASE.format(a=a, b=b, c=c, year=year, fy=fy, m=m, p=p)

def get(ctx, u):
    try:
        r = ctx.request.get(u, headers={"accept": "application/json"}, timeout=30000)
        if not r.ok:
            return None, f"HTTP {r.status}"
        return r.json(), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"

def company_of(row):
    for k in row.keys():
        if re.search(r"company|issuer", k, re.I):
            return re.sub(r"<[^>]+>", "", str(row[k]))[:34].strip()
    return "?"

def date_of(row):
    for k in row.keys():
        if re.search(r"open", k, re.I):
            return str(row[k])[:20]
    return "?"

def summarize(tag, data, err):
    if err:
        print(f"  {tag:34} ERROR {err}")
        return 0
    rows = (data or {}).get("reportTableData") or []
    if not rows:
        # show what keys DID come back so we see error payloads too
        print(f"  {tag:34} 0 rows  (top-level keys: {list((data or {}).keys())[:8]})")
        return 0
    print(f"  {tag:34} {len(rows):3} rows  first={company_of(rows[0])!r} "
          f"last={company_of(rows[-1])!r}  open[first]={date_of(rows[0])!r}")
    return len(rows)

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("use venv/bin/python (playwright missing)")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA)
        pg = ctx.new_page()
        print("warming up (Cloudflare) ...")
        pg.goto(WARMUP, wait_until="domcontentloaded", timeout=60000)
        for _ in range(15):
            if "moment" not in pg.title().lower():
                break
            pg.wait_for_timeout(1500)

        print("\n=== A. baseline: 2026 vs 2021 (both FY forms) ===")
        for year in (2026, 2021):
            for fy in (f"{year}-{(year+1)%100:02d}", f"{year-1}-{year%100:02d}"):
                d, e = get(ctx, url(year, fy))
                summarize(f"{year} fy={fy} m=0 p=0", d, e)
                time.sleep(0.4)

        fy21 = "2021-22"
        print("\n=== B. vary MONTH slot (2021) ===")
        for m in (1, 3, 6, 9, 12):
            d, e = get(ctx, url(2021, fy21, m=m))
            summarize(f"2021 m={m}", d, e)
            time.sleep(0.4)

        print("\n=== C. vary trailing PAGE slot (2021) ===")
        for p in (0, 1, 2, 3):
            d, e = get(ctx, url(2021, fy21, p=p))
            summarize(f"2021 p={p}", d, e)
            time.sleep(0.4)

        print("\n=== D. vary slot B (the '1') (2021) ===")
        for bb in (0, 1, 2, 3):
            d, e = get(ctx, url(2021, fy21, b=bb))
            summarize(f"2021 b={bb}", d, e)
            time.sleep(0.4)

        print("\n=== E. vary slot C (the '7') (2021) ===")
        for cc in (0, 1, 7, 12, 100):
            d, e = get(ctx, url(2021, fy21, c=cc))
            summarize(f"2021 c={cc}", d, e)
            time.sleep(0.4)

        print("\n=== F. raw shape ===")
        d, e = get(ctx, url(2021, fy21))
        if d:
            print("top-level keys:", list(d.keys()))
            for k, v in d.items():
                if k != "reportTableData":
                    print(f"  {k} = {json.dumps(v)[:200]}")
            rows = d.get("reportTableData") or []
            if rows:
                print("\nFULL first row (2021):")
                print(json.dumps(rows[0], indent=2, default=str)[:3000])
        d, e = get(ctx, url(2026, "2026-27"))
        rows = (d or {}).get("reportTableData") or []
        if rows:
            print("\nFULL first row (2026):")
            print(json.dumps(rows[0], indent=2, default=str)[:3000])
        b.close()

if __name__ == "__main__":
    main()
