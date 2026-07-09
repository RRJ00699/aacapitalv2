#!/usr/bin/env python3
"""
real_return_analysis.py — re-verify the validated strategy on current data.

The trade: MID gap (+4..15% listing open vs issue) -> buy open, sell D1 close.
Benchmark to beat/hold: 65% win / +3.3% median (validated 2026-07).

v2 rewrite (2026-07-09): the old version grouped by play_recommendation (the
repudiated playbook era) and read pruned columns (return_day7/30/day1_close).
This one computes the outcome the honest way — D1 open->close from
price_candles — and buckets by the traded band (LOW<4 / MID 4-15 / HIGH>15,
same as gap_bucket since the 4/15 alignment).

Read-only. Run whenever data changes (e.g. after the symbol-mismap repairs):
  python _scripts/real_return_analysis.py
  python _scripts/real_return_analysis.py --selftest   # no DB
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, argparse

BENCH = {"win": 65.0, "med": 3.3}

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
        print(f"  {tag:22} n<5 — not printable"); return
    print(f"  {tag:22} n={st[0]:<4} win={st[1]:5.1f}% med={st[2]:+6.2f} mean={st[3]:+6.2f}")

def run(recs):
    buckets = {}
    for gap, ret in recs:
        b = gapband(gap)
        if b: buckets.setdefault(b, []).append(ret)
        buckets.setdefault("ALL", []).append(ret)
    print("REAL RETURNS — buy listing open, sell D1 close (from candles)\n")
    for b in ("LOW", "MID", "HIGH", "ALL"):
        line(b, stats(buckets.get(b, [])))
    mid = stats(buckets.get("MID", []))
    print()
    if mid:
        dwin, dmed = mid[1] - BENCH["win"], mid[2] - BENCH["med"]
        print(f"MID vs validated benchmark (65%/+3.3): win {dwin:+.1f}pts, median {dmed:+.2f}")
        if mid[1] >= 55 and mid[2] > 0:
            print("VERDICT: edge HOLDS on current data.")
        else:
            print("VERDICT: edge DEGRADED — investigate before the next trade.")
    else:
        print("MID bucket too thin to verify (n<5) — check gap coverage.")

def fetch():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    # gap from master (open vs issue); outcome strictly from the day-1 candle
    cur.execute("""
        SELECT i.listing_gap_pct, ARRAY_AGG(p.open ORDER BY p.date), ARRAY_AGG(p.close ORDER BY p.date)
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
         AND p.date >= i.listing_date
        WHERE i.listing_date IS NOT NULL
          AND COALESCE(i.is_sme, FALSE) = FALSE
        GROUP BY i.id, i.listing_gap_pct""")
    recs = []
    for gap, o, c in cur.fetchall():
        ret = pct(c[0], o[0])
        if ret is not None and gap is not None:
            recs.append((float(gap), ret))
    conn.close()
    print(f"usable IPOs (mainboard, gap + d1 candle): {len(recs)}\n")
    return recs

def selftest():
    assert gapband(3.9) == "LOW" and gapband(4) == "MID" and gapband(15) == "MID" and gapband(15.1) == "HIGH"
    assert gapband(None) is None
    assert abs(pct(103.3, 100) - 3.3) < 1e-9 and pct(100, 0) is None
    recs = [(8.0, 3.3)] * 13 + [(8.0, -2.0)] * 7 + [(2.0, 1.0)] * 6 + [(20.0, -1.5)] * 6
    run(recs)  # MID: n=20, win 65%, med +3.3 -> HOLDS
    print("\nSELFTEST OK")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    run(fetch())

if __name__ == "__main__":
    main()
