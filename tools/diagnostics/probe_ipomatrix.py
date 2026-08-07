# -*- coding: utf-8 -*-
"""probe_ipomatrix.py v2 — corrected diagnostic (no writes).
v1 omitted five request-body params the real ingest sends, so the API returned
nothing and 'rows scanned: 0' was a probe failure, not an answer. This version
uses the EXACT body + response keys from ipomatrix_ingest.resolve_ids.
Run:  python tools/diagnostics/probe_ipomatrix.py
"""
import json, os, re, sys
import psycopg2

def jwt_from_db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM platform_config WHERE key IN ('ipomatrix_cookie','ipomatrix_jwt')")
    rows = dict(cur.fetchall()); conn.close()
    tok = rows.get("ipomatrix_jwt") or rows.get("ipomatrix_cookie") or ""
    m = re.search(r"(eyJ[\w-]+\.[\w-]+\.[\w-]+)", tok)
    return m.group(1) if m else tok.strip()

def post(jwt, body):
    LIST = "https://alphanodejs.chittorgarh.com/api/media-report-data-read"
    hdr = {"content-type": "application/json", "accept": "application/json, text/plain, */*",
           "origin": "https://www.ipomatrix.com", "referer": "https://www.ipomatrix.com/",
           "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
           "x-access-token": jwt}
    try:
        from curl_cffi import requests as creq
        return creq.post(LIST, data=json.dumps(body).encode(), headers=hdr,
                         impersonate="chrome", timeout=35).json()
    except ImportError:
        import urllib.request as u
        return json.loads(u.urlopen(u.Request(LIST, data=json.dumps(body).encode(),
                          headers=hdr, method="POST"), timeout=35).read().decode("utf-8", "replace"))

def main():
    jwt = jwt_from_db()
    if not jwt:
        sys.exit("no ipomatrix cookie/jwt in platform_config — refresh it in settings")
    want = re.compile(r"sbi\s*funds|alpine|caliber", re.I)
    hits, total = [], 0
    for yr in (2026, 2025):
        pg = 1
        while True:
            try:
                d = post(jwt, {"id": 82, "pageno": pg, "month": 7, "year": str(yr),
                               "fy": "2026-27", "sort": "0",
                               "param_id": "mainboard", "sub_param_id": "0",
                               "search": "", "extraParam": "", "minplandate": "2006-01-01"})
            except Exception as e:
                print(f"  year {yr} page {pg}: request failed: {str(e)[:80]}"); break
            rows = d.get("reportTableData") or []
            if not rows:
                if pg == 1: print(f"  year {yr}: 0 rows (keys seen: {list(d.keys())[:6]})")
                break
            total += len(rows)
            for row in rows:
                nm = str(row.get("~compare_name") or row.get("~IPO") or "")
                if want.search(nm) or want.search(str(row.get("Company", ""))):
                    hits.append({"name": nm, "sym": row.get("~nse_symbol"),
                                 "isin": row.get("~isin"),
                                 "company_link": str(row.get("Company",""))[:120]})
            tp = int(d.get("totalPages") or 1)
            if pg >= tp: break
            pg += 1
    print(f"rows scanned: {total}")
    if hits:
        print(f"FOUND {len(hits)} — data EXISTS on IPOMatrix; if ingest still skips them, paste these rows:")
        for h in hits: print("  ", json.dumps(h, ensure_ascii=False))
    else:
        print("NOT FOUND across", total, "rows — report 82 genuinely lacks these pre-listing IPOs.")
        print("(Trustworthy this time only if rows scanned > 0.)")

if __name__ == "__main__":
    main()
