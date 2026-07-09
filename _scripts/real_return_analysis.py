#!/usr/bin/env python3
"""
real_return_analysis.py — re-verify the validated strategy, DECOMPOSED.

The trade: MID gap (+4..15% listing open vs issue) -> buy open, sell D1 close.
Benchmark: 65% win / +3.3% median.

v3 (2026-07-09): the first clean-data run said DEGRADED (MID 52.1%/+0.76,
n=48) and HIGH looked positive — contradicting every prior backtest. Two
artifacts could manufacture that, so this version separates them:

  A) GAP-LABEL CONTAMINATION — the old ipo_candle_backfill filled
     listing_gap_pct with day-1 CLOSE vs issue (not OPEN vs issue). Wrong
     gap -> wrong bucket. Here the gap is computed from the d1 candle OPEN
     vs issue_price; we also report how many stored labels disagree.
  B) ERA SKEW — candles only cover the synced era (mostly 2021+). The
     master-field universe (listing_open/listing_day_close columns, no
     candle needed) reaches further back. Both universes are reported,
     split by era (<=2022 vs >=2023), so regime decay is visible separately
     from data artifacts.

Read the grid: if full-history master MID ~= benchmark but recent-era rows
sit ~52%, the edge is REGIME-DEPENDENT (act accordingly). If every cut sits
~52%, the 65/+3.3 benchmark itself was inflated by bad labels.

  python _scripts/real_return_analysis.py
  python _scripts/real_return_analysis.py --selftest
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, argparse

BENCH = {"win": 65.0, "med": 3.3}
ERA_SPLIT = 2023   # <= 2022 = "old era", >= 2023 = "new era"

def pct(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if b <= 0: return None
    return (a / b - 1.0) * 100.0

def gapband(g):
    if g is None: return None
    g = float(g)
    return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")

def stats(rets):
    n = len(rets)
    if n < 5: return None
    s = sorted(rets)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return n, sum(1 for r in rets if r > 0) / n * 100, med, sum(rets) / n

def line(tag, st):
    if not st:
        print(f"  {tag:30} n<5 — not printable"); return
    print(f"  {tag:30} n={st[0]:<4} win={st[1]:5.1f}% med={st[2]:+6.2f} mean={st[3]:+6.2f}")

def report(title, recs):
    """recs: (gap, ret, year)"""
    print("=" * 66); print(title); print("=" * 66)
    for era, cond in (("ALL YEARS", lambda y: True),
                      (f"<= {ERA_SPLIT-1}", lambda y: y is not None and y < ERA_SPLIT),
                      (f">= {ERA_SPLIT}", lambda y: y is not None and y >= ERA_SPLIT)):
        for b in ("LOW", "MID", "HIGH"):
            sub = [r for g, r, y in recs if gapband(g) == b and cond(y)]
            line(f"{era:9} {b}", stats(sub))
        print()

def run(candle_recs, master_recs, relabeled):
    report("A) CANDLE universe — gap from d1 candle OPEN vs issue (clean labels)",
           candle_recs)
    print(f"stored listing_gap_pct bucket disagreed with candle-open gap on "
          f"{relabeled} of {len(candle_recs)} rows (old close-based fills)\n")
    report("B) MASTER-FIELD universe — listing_open/listing_day_close columns "
           "(wider history)", master_recs)
    mid_all = stats([r for g, r, y in master_recs if gapband(g) == "MID"])
    if mid_all:
        print(f"Master full-history MID vs benchmark (65/+3.3): "
              f"win {mid_all[1]-BENCH['win']:+.1f}pts, med {mid_all[2]-BENCH['med']:+.2f}")
    print("\nRead: A-recent ~52% AND B-old ~65% -> regime decay (real).")
    print("      every cut ~52% -> the benchmark was label-inflated (artifact).")

def fetch():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()

    # A) candle universe: gap AND outcome both from the d1 candle + issue_price
    cur.execute("""
        SELECT i.issue_price, i.listing_gap_pct, EXTRACT(YEAR FROM i.listing_date)::int,
               ARRAY_AGG(p.open ORDER BY p.date), ARRAY_AGG(p.close ORDER BY p.date)
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
         AND p.date >= i.listing_date
        WHERE i.listing_date IS NOT NULL AND COALESCE(i.is_sme, FALSE) = FALSE
          AND i.issue_price > 0
        GROUP BY i.id, i.issue_price, i.listing_gap_pct, 3""")
    candle_recs, relabeled = [], 0
    for ip, stored_gap, yr, o, c in cur.fetchall():
        gap = pct(o[0], ip)            # OPEN vs issue — the honest gap
        ret = pct(c[0], o[0])
        if gap is None or ret is None: continue
        candle_recs.append((gap, ret, yr))
        if stored_gap is not None and gapband(float(stored_gap)) != gapband(gap):
            relabeled += 1

    # B) master-field universe: no candle requirement, wider history
    cur.execute("""
        SELECT issue_price, listing_open, listing_day_close,
               EXTRACT(YEAR FROM listing_date)::int
        FROM ipo_intelligence
        WHERE listing_date IS NOT NULL AND COALESCE(is_sme, FALSE) = FALSE
          AND issue_price > 0 AND listing_open > 0 AND listing_day_close > 0""")
    master_recs = []
    for ip, lo, lc, yr in cur.fetchall():
        gap, ret = pct(lo, ip), pct(lc, lo)
        if gap is not None and ret is not None:
            master_recs.append((gap, ret, yr))
    conn.close()
    print(f"universes: candle={len(candle_recs)}  master-field={len(master_recs)}\n")
    return candle_recs, master_recs, relabeled

def selftest():
    assert gapband(3.9) == "LOW" and gapband(4) == "MID" and gapband(15) == "MID" and gapband(15.1) == "HIGH"
    assert abs(pct(103.3, 100) - 3.3) < 1e-9 and pct(100, 0) is None
    old = [(8.0, 3.3, 2018)] * 13 + [(8.0, -2.0, 2018)] * 7          # old era MID: 65%
    new = [(8.0, 0.8, 2024)] * 10 + [(8.0, -1.0, 2024)] * 10         # new era MID: 50%
    run(old + new, old + new, relabeled=3)
    print("\nSELFTEST OK")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    run(*fetch())

if __name__ == "__main__":
    main()
