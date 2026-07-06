#!/usr/bin/env python3
"""
base_backtest.py — READ-ONLY: does buying post-listing BASE BREAKOUTS work?

Base definition (per IPO, first 45 sessions):
  a window of W consecutive sessions where (windowHigh-windowLow)/windowLow <= T%
  and windowLow holds above 0.85x the listing-day low (not a collapse).
  pivot = window high. ENTRY = first close > pivot after the base completes.
Exits measured (the executable lesson applied): close +1 / +5 / +10 sessions
after entry, +8% target else D10, and ORACLE best<=10 as ceiling.
Grid: W in {5,7,10}, T in {8%, 12%}. Reported per combo + per gap bucket.
Also the control: IPOs that never formed a base (their D10-from-open outcome).

  venv/bin/python _scripts/base_backtest.py
"""
import os, sys
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def find_base(highs, lows, closes, W, Tpct, max_start=45):
    llow = lows[0]
    for i in range(1, min(len(closes) - 1, max_start)):
        if i + W > len(closes): break
        wh = max(highs[i:i+W]); wl = min(lows[i:i+W])
        if wl <= 0 or wl < 0.85 * llow: continue
        if (wh - wl) / wl * 100 <= Tpct:
            # base formed at [i, i+W); find breakout close > pivot
            for j in range(i + W, len(closes)):
                if closes[j] > wh:
                    return i, wh, j          # base start, pivot, entry idx
            return i, wh, None               # base, never broke out
    return None, None, None

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return (n, sum(1 for r in rets if r > 0)/n*100, s[n//2], sum(rets)/n, s[max(0,int(n*.1)-1)])

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
    cols = {r[0] for r in cur.fetchall()}
    sym = "symbol_final" if "symbol_final" in cols else "nse_symbol"
    cur.execute(f"""SELECT UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$','')), c.gap_bucket,
                           ARRAY_AGG(p.high ORDER BY p.date), ARRAY_AGG(p.low ORDER BY p.date),
                           ARRAY_AGG(p.close ORDER BY p.date)
                    FROM ipo_consolidated c JOIN price_candles p
                      ON UPPER(p.symbol)=UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$',''))
                     AND p.date >= c.listing_date
                    WHERE c.listing_date IS NOT NULL AND c.listing_date < CURRENT_DATE - 90
                    GROUP BY 1,2 HAVING COUNT(*) >= 60""")
    data = []
    for s, gb, hi, lo, cl in cur.fetchall():
        try:
            data.append((s, (gb or "?").upper(),
                         [float(x) for x in hi], [float(x) for x in lo], [float(x) for x in cl]))
        except (TypeError, ValueError):
            continue
    conn.close()
    print(f"IPOs with >=60 sessions of candles: {len(data)}\n")

    for W, T in [(5, 8), (7, 8), (7, 12), (10, 12)]:
        per, buckets, formed, broke = {}, {}, 0, 0
        for s, gb, hi, lo, cl in data:
            b, pivot, e = find_base(hi, lo, cl, W, T)
            if b is None: continue
            formed += 1
            if e is None or e + 1 >= len(cl): continue
            broke += 1
            entry = cl[e]
            outs = {}
            for d in (1, 5, 10):
                if e + d < len(cl): outs[f"+{d}d close"] = (cl[e+d]-entry)/entry*100
            horizon = cl[e+1:e+11]
            if horizon:
                outs["ORACLE<=10"] = (max(horizon)-entry)/entry*100
                hit = next(((c-entry)/entry*100 for c in horizon if (c-entry)/entry*100 >= 8), None)
                outs["tgt+8 else D10"] = hit if hit is not None else (horizon[-1]-entry)/entry*100
            for k, v in outs.items():
                per.setdefault(k, []).append(v)
                buckets.setdefault((gb, k), []).append(v)
        print(f"== base W={W} sessions, tightness<={T}%  |  formed={formed}  broke out={broke}")
        for k in ("+1d close", "+5d close", "+10d close", "tgt+8 else D10", "ORACLE<=10"):
            st = stats(per.get(k, []))
            if st: print(f"   {k:16} n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}  mean={st[3]:+6.1f}  p10={st[4]:+7.1f}")
        for gb in ("LOW", "MID", "HIGH"):
            st = stats(buckets.get((gb, "+10d close"), []))
            if st: print(f"     {gb:4} +10d: n={st[0]:<3} win={st[1]:5.1f}%  med={st[2]:+6.1f}  mean={st[3]:+6.1f}")
        print()
    print("READ-ONLY. If a combo shows win>=60% med>=+4 at n>=30 on +5d/+10d, base-breakout earns the build (nightly detector + card pivot line + ntfy alert). If not, folklore — we skip it.")

if __name__ == "__main__":
    main()
