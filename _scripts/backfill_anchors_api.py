#!/usr/bin/env python3
"""
backfill_anchors_api.py — fills anchor_names + anchor_count for the whole IPO
universe using Chittorgarh's IPOMatrix anchor report (id 163). One clean POST
per year returns every IPO with anchor investor names — no per-page slug guessing.

Needs a fresh JWT (the report is auth-gated). Get it once from the browser:
  ipomatrix.com anchor page -> F12 -> Network -> any 'media-report-data-read'
  request -> Headers -> copy the 'x-access-token' value. Paste into
  Settings (key: ipomatrix_token) OR env IPOMATRIX_TOKEN.

  python _scripts/backfill_anchors_api.py --years 2021-2026            # dry
  python _scripts/backfill_anchors_api.py --years 2010-2026 --apply
"""
import os, re, sys, json, argparse

URL = "https://alphanodejs.chittorgarh.com/api/media-report-data-read"
REPORT = 163

def norm(name):
    s = (name or "").lower()
    s = re.sub(r"\b(ltd|limited|pvt|private|the)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get_token(cur):
    t = os.environ.get("IPOMATRIX_TOKEN")
    if t: return t
    try:
        cur.execute("SELECT value FROM platform_config WHERE key='ipomatrix_token'")
        r = cur.fetchone()
        return r[0] if r else None
    except Exception:
        return None

def fetch_year(token, year):
    try:
        from curl_cffi import requests as creq
        get = lambda: creq.post(URL, impersonate="chrome", timeout=40,
            headers={"x-access-token": token, "content-type": "application/json"},
            json={"report_id": REPORT, "year": str(year), "search": "", "page": 1, "limit": 500})
    except ImportError:
        import urllib.request
        def get():
            body = json.dumps({"report_id": REPORT, "year": str(year),
                               "search": "", "page": 1, "limit": 500}).encode()
            req = urllib.request.Request(URL, data=body, headers={
                "x-access-token": token, "content-type": "application/json",
                "User-Agent": "Mozilla/5.0 Chrome/124.0"})
            class R:  # shim
                text = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
            return R()
    r = get()
    return json.loads(r.text)

def extract_anchors(row):
    """Anchor investor names live in a field; try common keys + any 'anchor' list."""
    for k in ("anchor_investors", "AnchorInvestors", "anchor_names", "anchor_investor_names"):
        v = row.get(k)
        if isinstance(v, str) and len(v) > 3:
            names = [n.strip() for n in re.split(r"[,;|]", v) if n.strip()]
            if names: return names
        if isinstance(v, list) and v:
            return [str(x).strip() for x in v if str(x).strip()]
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2021-2026")
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
    token = get_token(cur)
    if not token:
        sys.exit("No IPOMATRIX_TOKEN (env) or platform_config 'ipomatrix_token'. "
                 "Grab x-access-token from DevTools; see header docstring.")
    cur.execute("""SELECT id, UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)), company_name
                   FROM ipo_intelligence""")
    by_sym, by_name = {}, {}
    for pid, sym, nm in cur.fetchall():
        if sym: by_sym[sym] = pid
        by_name[norm(nm)] = pid
    total_fill = 0
    for year in years:
        try:
            data = fetch_year(token, year)
        except Exception as e:
            print(f"{year}: fetch error {e}"); continue
        rows = data.get("data") or data.get("reportTableData") or []
        if not rows and data.get("msg") not in (1, "1", None):
            print(f"{year}: API said {str(data)[:120]} — token expired?"); return
        yfill = 0
        # peek schema once
        if year == list(years)[0] and rows:
            akeys = [k for k in rows[0] if "anchor" in k.lower()]
            print(f"anchor-ish keys in row: {akeys}")
        for row in rows:
            sym = str(row.get("nse_symbol") or row.get("~nse_symbol") or "").upper().strip()
            nm = row.get("company_name") or row.get("~compare_name") or row.get("Company") or ""
            pid = by_sym.get(sym) or by_name.get(norm(re.sub(r"<[^>]+>", "", str(nm))))
            if not pid: continue
            names = extract_anchors(row)
            if not names: continue
            yfill += 1
            if a.apply:
                cur.execute("""UPDATE ipo_intelligence SET
                    anchor_names=COALESCE(anchor_names,%s), anchor_count=COALESCE(anchor_count,%s)
                    WHERE id=%s""", (json.dumps(names), len(names), pid))
        print(f"{year}: matched+anchored {yfill} IPOs")
        total_fill += yfill
    if a.apply: conn.commit()
    print(f"\n{'WROTE' if a.apply else 'DRY'}: {total_fill} IPOs with anchor names")
    conn.close()

if __name__ == "__main__":
    main()
