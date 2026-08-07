#!/usr/bin/env python3
"""ofs_backtest.py — READ-ONLY: does the fresh-vs-OFS split predict the d10
outcome? Two eras (pre-2022 golden-harvest vs 2022+), pooled + by gap bucket.
Buckets: 100% OFS · OFS-heavy (<50% fresh) · fresh-heavy (>=50%) · 100% fresh.
  python research/backtests/ofs_backtest.py"""
import os, sys

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0)/n*100, s[n//2]

def bucket_fresh(fresh, ofs):
    tot = (fresh or 0) + (ofs or 0)
    if tot <= 0: return None
    fp = (fresh or 0) / tot * 100
    if fp == 0: return "100% OFS"
    if fp < 50: return "OFS-heavy"
    if fp < 100: return "fresh-heavy"
    return "100% fresh"

def main():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur = psycopg2.connect(DB, connect_timeout=20).cursor()
    cur.execute("""SELECT fresh_cr, ofs_cr, listing_gap_pct, d10_best_pct,
                          EXTRACT(YEAR FROM listing_date)::int
                   FROM ipo_intelligence
                   WHERE d10_best_pct IS NOT NULL
                     AND (fresh_cr IS NOT NULL OR ofs_cr IS NOT NULL)""")
    rows = cur.fetchall()
    print(f"IPOs with split + outcome: {len(rows)}\n")
    def gb(g):
        try: g = float(g)
        except (TypeError, ValueError): return "?"
        return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")
    pooled, era, cross = {}, {}, {}
    for f, o, g, d10, yr in rows:
        b = bucket_fresh(f, o)
        if not b: continue
        d = float(d10)
        pooled.setdefault(b, []).append(d)
        era.setdefault((b, "pre-2022" if (yr or 0) < 2022 else "2022+"), []).append(d)
        cross.setdefault((b, gb(g)), []).append(d)
    print("POOLED (d10 win% / med, n>=8):")
    for b in ("100% OFS", "OFS-heavy", "fresh-heavy", "100% fresh"):
        st = stats(pooled.get(b, []))
        if st: print(f"  {b:12} n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}")
    print("\nBY ERA:")
    for (b, e), v in sorted(era.items(), key=lambda t: (t[0][1], t[0][0])):
        st = stats(v)
        if st: print(f"  {e:8} {b:12} n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}"
                     f"  {'SIGNAL' if st[0]>=30 else 'HINT'}")
    print("\nBY GAP BUCKET (pooled eras):")
    for (b, g), v in sorted(cross.items(), key=lambda t: (t[0][1], t[0][0])):
        st = stats(v)
        if st: print(f"  {g:4} {b:12} n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}")
    print("\nREAD-ONLY. Verdict bar: a bucket earns score entry only at n>=30, "
          "win-gap >=8pts vs baseline 72%, direction consistent across both eras.")

if __name__ == "__main__":
    main()
