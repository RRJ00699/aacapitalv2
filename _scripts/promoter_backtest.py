#!/usr/bin/env python3
"""
promoter_backtest.py — READ-ONLY: does ownership structure predict outcomes?
Hypothesis (Turtlemint pattern): promoter-light / VC-heavy IPOs behave worse
(exit-seeking supply) than founder-held ones.

Introspects ipo_intelligence for a post-issue promoter-holding column.
If coverage >= 100 rows: buckets <25% / 25-50% / >50% promoter holding
vs d10_best_pct (pooled, by era, by gap bucket).
If coverage is thin: says so and names the ingestion lane needed.

  python _scripts/promoter_backtest.py
"""
import os, sys

CANDIDATES = ["promoter_holding_post", "promoter_holding_post_pct", "promoter_post_pct",
              "post_issue_promoter_pct", "promoter_holding", "promoter_pct",
              "promoter_stake_post", "promoters_post_issue"]

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0)/n*100, s[n//2]

def main():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur = psycopg2.connect(DB, connect_timeout=20).cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    cols = {r[0] for r in cur.fetchall()}
    col = next((c for c in CANDIDATES if c in cols), None)
    fuzzy = sorted(c for c in cols if "promot" in c)
    print("promoter-ish columns in master:", fuzzy or "NONE")
    if not col and fuzzy: col = fuzzy[0]
    if not col:
        print("\nVERDICT: data lane missing. Needed: one number per IPO = post-issue "
              "promoter %. Best source: Chittorgarh IPO details (promoter holding "
              "pre/post issue) — probe its webnodejs report next session; fallback: "
              "Screener shareholding page via the PC quarterly ritual.")
        return
    cur.execute(f"SELECT COUNT({col}) FROM ipo_intelligence WHERE d10_best_pct IS NOT NULL")
    n = cur.fetchone()[0]
    print(f"using column: {col} | rows with holding + outcome: {n}")
    if n < 100:
        print("coverage too thin for SIGNAL — same ingestion lane needed as above.")
        return
    cur.execute(f"""SELECT {col}, listing_gap_pct, d10_best_pct,
                           EXTRACT(YEAR FROM listing_date)::int
                    FROM ipo_intelligence
                    WHERE {col} IS NOT NULL AND d10_best_pct IS NOT NULL""")
    def hb(p):
        try: p = float(p)
        except (TypeError, ValueError): return None
        if p > 100 or p < 0: return None
        return "<25% (VC-heavy)" if p < 25 else ("25-50%" if p < 50 else ">50% (founder-held)")
    def gb(g):
        try: g = float(g)
        except (TypeError, ValueError): return "?"
        return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")
    pooled, era, cross = {}, {}, {}
    for p, g, d10, yr in cur.fetchall():
        b = hb(p)
        if not b: continue
        d = float(d10)
        pooled.setdefault(b, []).append(d)
        era.setdefault((b, "pre-2022" if (yr or 0) < 2022 else "2022+"), []).append(d)
        cross.setdefault((b, gb(g)), []).append(d)
    print("\nPOOLED (d10 win% / med, n>=8):")
    for b in ("<25% (VC-heavy)", "25-50%", ">50% (founder-held)"):
        st = stats(pooled.get(b, []))
        if st: print(f"  {b:22} n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}")
    print("\nBY ERA:")
    for (b, e), v in sorted(era.items(), key=lambda t: (t[0][1], t[0][0])):
        st = stats(v)
        if st: print(f"  {e:8} {b:22} n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}"
                     f"  {'SIGNAL' if st[0]>=30 else 'HINT'}")
    print("\nBY GAP BUCKET:")
    for (b, g), v in sorted(cross.items(), key=lambda t: (t[0][1], t[0][0])):
        st = stats(v)
        if st: print(f"  {g:4} {b:22} n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}")
    print("\nREAD-ONLY. Bar for score entry: n>=30, win-gap >=8pts vs 72% baseline, "
          "era-consistent direction.")

if __name__ == "__main__":
    main()
