#!/usr/bin/env python3
"""
fetch_peer_pe.py — populate ipo_intelligence.peer_median_pe from screener.in.

This lights up the valuation-vs-peers dimension (your Hyundai-vs-Maruti / HDB edge).
For each IPO symbol that is still missing peer_median_pe (GOLDEN RULE: fill empties
ONLY — never touch a populated cell), it:
   1. GETs the screener company page  -> extracts the internal company_id
   2. GETs the peers AJAX endpoint     -> reads the 'Median' row's P/E
   3. Writes peer_median_pe into ipo_intelligence WHERE peer_median_pe IS NULL

Auth: the peers endpoint may need a logged-in session. If so, copy your screener
cookie from the browser dev-tools (Network tab -> any request -> Cookie header) and:
    setx SCREENER_COOKIE "sessionid=xxxx; csrftoken=yyyy"     (then reopen shell)

USAGE — test on your own examples first, dry-run (writes nothing):
    python _scripts\fetch_peer_pe.py --symbols HYUNDAI HDBFIN --dry-run
Then the full backfill (only fills NULLs, so it's safely re-runnable):
    python _scripts\fetch_peer_pe.py --apply
"""
import os, re, io, sys, time, argparse

try:
    import requests
except ImportError:
    sys.exit("pip install requests --break-system-packages")
try:
    import pandas as pd
except ImportError:
    sys.exit("pip install pandas lxml --break-system-packages")
try:
    import psycopg2
except ImportError:
    psycopg2 = None

BASE = "https://www.screener.in"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AAcapital-research/1.0"

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
    ck = os.getenv("SCREENER_COOKIE")
    if ck:
        s.headers["Cookie"] = ck.strip()
    return s

def get_company_id(s, symbol):
    """Resolve screener's internal numeric company_id from the company page."""
    r = s.get(f"{BASE}/company/{symbol}/", timeout=30)
    if r.status_code != 200:
        return None, f"page HTTP {r.status_code}"
    html = r.text
    for pat in (r"/company/source/\w+/(\d+)/", r'data-company-id="(\d+)"', r"/api/company/(\d+)/"):
        m = re.search(pat, html)
        if m:
            return m.group(1), None
    if "login" in r.url or "Login" in html[:2000]:
        return None, "looks like a login wall (set SCREENER_COOKIE)"
    return None, "company_id not found in page"

PEER_ENDPOINTS = [
    "{base}/api/company/{cid}/peers/",
    "{base}/company/{cid}/peers/",
    "{base}/api/company/peers/{cid}/",
]

def get_peer_median_pe(s, cid, symbol):
    """Read the 'Median' row P/E from the peers AJAX table; fall back to computing it.
    The exact peers endpoint is uncertain, so try a few; report which worked."""
    r = None
    for tmpl in PEER_ENDPOINTS:
        url = tmpl.format(base=BASE, cid=cid)
        rr = s.get(url, timeout=30, headers={"X-Requested-With": "XMLHttpRequest",
                                             "Referer": f"{BASE}/company/{symbol}/"})
        if rr.status_code == 200 and rr.text.strip():
            r = rr; break
    if r is None:
        return None, None, "all peer endpoints failed (cookie set? else grab URL from DevTools)"
    try:
        tables = pd.read_html(io.StringIO(r.text))
    except ValueError:
        return None, None, "no table in peers response"
    df = tables[0]
    df.columns = [str(c).strip() for c in df.columns]
    pe_col = next((c for c in df.columns if re.search(r"\bp[\s./_-]*e\b", c, re.I)), None)
    if not pe_col:
        return None, None, f"no P/E column ({df.columns.tolist()[:6]})"
    name_col = df.columns[0]
    names = df[name_col].astype(str)
    med_row = df[names.str.contains("median", case=False, na=False)]
    # peers = rows that aren't the subject company or the median/summary row
    peer_vals = pd.to_numeric(
        df[~names.str.contains("median", case=False, na=False)][pe_col], errors="coerce"
    ).dropna()
    n_peers = int(max(len(peer_vals) - 1, 0))  # minus the subject company itself
    if not med_row.empty:
        v = pd.to_numeric(med_row[pe_col].iloc[0], errors="coerce")
        if pd.notna(v):
            return round(float(v), 2), n_peers, "median-row"
    if len(peer_vals) >= 2:
        return round(float(peer_vals.median()), 2), n_peers, "computed-median"
    return None, n_peers, "insufficient peer PEs"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", help="test specific NSE symbols")
    ap.add_argument("--apply", action="store_true", help="write to DB (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=3.0, help="seconds between companies (be polite)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    DB = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    s = make_session()
    if not os.getenv("SCREENER_COOKIE"):
        print("⚠️  SCREENER_COOKIE not set — screener returns 404 to anonymous peer calls.")
        print("    Use the SAME cookie your financials importer uses:")
        print('    $env:SCREENER_COOKIE = "csrftoken=...; sessionid=..."\n')

    # build the worklist: explicit symbols, else every IPO missing peer_median_pe
    if args.symbols:
        targets = [(sym, None) for sym in args.symbols]
    else:
        if not (psycopg2 and DB):
            sys.exit("Need DATABASE_URL + psycopg2 (or pass --symbols).")
        conn = psycopg2.connect(DB); cur = conn.cursor()
        cur.execute("""SELECT nse_symbol FROM ipo_intelligence
                       WHERE nse_symbol IS NOT NULL AND peer_median_pe IS NULL
                       ORDER BY listing_date DESC NULLS LAST""")
        targets = [(r[0], None) for r in cur.fetchall()]
        conn.close()
    if args.limit:
        targets = targets[:args.limit]

    print(f"{'SYMBOL':16}{'peer_PE':>9}{'#peers':>8}  source / note")
    print("-"*60)
    results = {}
    for sym, _ in targets:
        try:
            cid, err = get_company_id(s, sym)
            if not cid:
                print(f"{sym:16}{'-':>9}{'-':>8}  ✗ {err}"); time.sleep(args.sleep); continue
            pe, npeers, note = get_peer_median_pe(s, cid, sym)
            if pe is not None:
                results[sym] = pe
                print(f"{sym:16}{pe:>9.2f}{npeers:>8}  {note}")
            else:
                print(f"{sym:16}{'-':>9}{(npeers or 0):>8}  ✗ {note}")
        except Exception as e:
            print(f"{sym:16}{'-':>9}{'-':>8}  ✗ {str(e)[:40]}")
        time.sleep(args.sleep)

    print("-"*60)
    print(f"resolved peer_median_pe for {len(results)}/{len(targets)} symbols")
    if apply and results:
        conn = psycopg2.connect(DB); cur = conn.cursor()
        n = 0
        for sym, pe in results.items():
            # GOLDEN RULE: only fill where it's still empty
            cur.execute("""UPDATE ipo_intelligence SET peer_median_pe = %s
                           WHERE nse_symbol = %s AND peer_median_pe IS NULL""", (pe, sym))
            n += cur.rowcount
        conn.commit(); conn.close()
        print(f"✓ wrote {n} new peer_median_pe values (existing values untouched).")
        print("  next: re-run build_ipo_consolidated_v2.py (valuation_premium auto-computes), then check_data_contract.py")
    elif results:
        print("dry-run — nothing written. Re-run with --apply once the numbers look right.")

if __name__ == "__main__":
    main()
