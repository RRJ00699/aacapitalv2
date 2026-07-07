#!/usr/bin/env python3
"""
compute_peer_pe.py — self-computed peer valuation. Kills the SBI-note dependence.

For every industry: median PE of its listed members, where
  PE = stock_fundamentals.market_cap / latest-FY PAT (annual_financials),
  requiring PAT > 0 and >= 4 members.
Then fills ipo_intelligence.peer_median_pe (NULL only, Rule 1) by matching the
IPO's sector string against industry names (exact-normalized, then containment).

  python _scripts/compute_peer_pe.py            # dry run
  python _scripts/compute_peer_pe.py --apply
"""
import os, re, sys, argparse, statistics

def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()

    cur.execute("""
        SELECT sf.industry, sf.market_cap, af.pat
        FROM stock_fundamentals sf
        JOIN LATERAL (
            SELECT pat FROM annual_financials af
            WHERE af.symbol = sf.nse_symbol AND af.pat IS NOT NULL
            ORDER BY af.fy DESC LIMIT 1
        ) af ON TRUE
        WHERE sf.industry IS NOT NULL AND sf.market_cap > 0""")
    by_ind = {}
    for ind, mcap, pat in cur.fetchall():
        try:
            mcap, pat = float(mcap), float(pat)
        except (TypeError, ValueError):
            continue
        if pat > 0 and 0 < mcap / pat < 500:
            by_ind.setdefault(ind, []).append(mcap / pat)
    med = {ind: round(statistics.median(v), 1) for ind, v in by_ind.items() if len(v) >= 4}
    print(f"industries with computable median PE (n>=4): {len(med)}")
    nmed = {norm(k): v for k, v in med.items()}

    cur.execute("""SELECT id, sector FROM ipo_intelligence
                   WHERE peer_median_pe IS NULL AND sector IS NOT NULL""")
    rows = cur.fetchall()
    filled = miss = 0
    unmatched = {}
    for pid, sec in rows:
        ns = norm(sec)
        val = nmed.get(ns)
        if val is None:
            cands = [v for k, v in nmed.items() if ns and (ns in k or k in ns)]
            val = round(statistics.median(cands), 1) if cands else None
        if val is None:
            miss += 1; unmatched[sec] = unmatched.get(sec, 0) + 1; continue
        filled += 1
        if a.apply:
            cur.execute("UPDATE ipo_intelligence SET peer_median_pe=%s WHERE id=%s AND peer_median_pe IS NULL",
                        (val, pid))
    if a.apply: conn.commit()
    print(f"IPOs {'filled' if a.apply else 'fillable'}: {filled} | no industry match: {miss}")
    top = sorted(unmatched.items(), key=lambda t: -t[1])[:8]
    if top: print("top unmatched sectors:", top)
    if not a.apply: print("DRY RUN — --apply to write (fill-empty only).")
    conn.close()

if __name__ == "__main__":
    main()
