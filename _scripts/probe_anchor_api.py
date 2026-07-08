#!/usr/bin/env python3
"""probe_anchor_api.py — READ-ONLY. Fetches ONE year of Chittorgarh anchor
report (163) with your token and dumps the exact row schema, so the backfill
targets real field names. No DB writes.

Token: env IPOMATRIX_TOKEN or platform_config 'ipomatrix_token'.
  python _scripts/probe_anchor_api.py --year 2025
"""
import os, sys, json, argparse, re
URL = "https://alphanodejs.chittorgarh.com/api/media-report-data-read"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--year", default="2025")
    a = ap.parse_args()
    tok = os.environ.get("IPOMATRIX_TOKEN")
    if not tok:
        try:
            import psycopg2
            DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
            c = psycopg2.connect(DB, connect_timeout=15).cursor()
            c.execute("SELECT value FROM platform_config WHERE key='ipomatrix_token'")
            r = c.fetchone(); tok = r[0] if r else None
        except Exception: pass
    if not tok: sys.exit("no IPOMATRIX_TOKEN / platform_config ipomatrix_token")
    body = {"report_id": 163, "year": str(a.year), "search": "", "page": 1, "limit": 5}
    try:
        from curl_cffi import requests as creq
        r = creq.post(URL, impersonate="chrome", timeout=40,
            headers={"x-access-token": tok, "content-type": "application/json"}, json=body)
        txt = r.text
    except ImportError:
        import urllib.request
        req = urllib.request.Request(URL, data=json.dumps(body).encode(),
            headers={"x-access-token": tok, "content-type": "application/json",
                     "User-Agent": "Mozilla/5.0 Chrome/124.0"})
        txt = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    try:
        d = json.loads(txt)
    except Exception:
        print("non-JSON response (token bad?):", txt[:300]); return
    print("top-level keys:", list(d.keys()))
    rows = d.get("data") or d.get("reportTableData") or []
    print(f"rows: {len(rows)}")
    if not rows:
        print("raw:", str(d)[:400]); return
    print("\n== row 0 full schema ==")
    for k, v in rows[0].items():
        mark = "  <-- ANCHOR" if "anchor" in k.lower() else ("  <-- NAME/SYM" if re.search(r"symbol|company|name", k, re.I) else "")
        print(f"  {k}: {str(v)[:70]}{mark}")

if __name__ == "__main__":
    main()
