#!/usr/bin/env python3
"""
close_in_range.py — computes the listing-day (and early-session) "close-in-range"
strength proxy from candles we already store, writes it to the master, and
backtests whether it predicts d10 — pooled and WITHIN the MID bucket (the only
trade), to see if it's a usable confirmation filter.

close_in_range = (close - low) / (high - low)   [0=closed at low, 1=closed at high]
Listing-day CIR = buyers vs sellers won day 1. Also a 3-day avg CIR.

  python _scripts/close_in_range.py            # dry: compute + backtest, no write
  python _scripts/close_in_range.py --apply    # write cir columns to master
"""
import os, sys, argparse

def cir(o, h, l, c):
    try:
        h, l, c = float(h), float(l), float(c)
    except (TypeError, ValueError):
        return None
    if h <= l: return None
    v = (c - l) / (h - l)
    return max(0.0, min(1.0, v))

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0)/n*100, s[n//2], sum(rets)/n

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    cols = {r[0] for r in cur.fetchall()}

    # ensure columns exist (safe if already there)
    if a.apply:
        for c in ("listing_cir", "cir_3d_avg"):
            if c not in cols:
                cur.execute(f'ALTER TABLE ipo_intelligence ADD COLUMN {c} numeric')
        conn.commit()

    cur.execute("""
        SELECT i.id, i.listing_gap_pct, i.d10_best_pct,
               ARRAY_AGG(p.open ORDER BY p.date), ARRAY_AGG(p.high ORDER BY p.date),
               ARRAY_AGG(p.low ORDER BY p.date),  ARRAY_AGG(p.close ORDER BY p.date)
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
         AND p.date >= i.listing_date
        WHERE i.listing_date IS NOT NULL
        GROUP BY 1,2,3 HAVING COUNT(*) >= 1""")
    recs = []
    wrote = 0
    for pid, gap, d10, o, h, l, c in cur.fetchall():
        d1 = cir(o[0], h[0], l[0], c[0])
        avg3 = [cir(o[i], h[i], l[i], c[i]) for i in range(min(3, len(c)))]
        avg3 = [x for x in avg3 if x is not None]
        cir3 = round(sum(avg3)/len(avg3), 3) if avg3 else None
        if a.apply and d1 is not None:
            cur.execute("""UPDATE ipo_intelligence
                SET listing_cir=%s, cir_3d_avg=%s WHERE id=%s""",
                (round(d1, 3), cir3, pid))
            wrote += 1
        if d1 is not None and d10 is not None:
            recs.append((d1, float(gap) if gap is not None else None, float(d10)))
    if a.apply: conn.commit()
    print(f"{'wrote' if a.apply else 'computed'} listing_cir for {wrote if a.apply else len(recs)} IPOs\n")

    def band(v): return "closed WEAK <0.33" if v < 0.33 else ("closed MID 0.33-0.66" if v < 0.67 else "closed STRONG >=0.67")
    def gb(g):
        if g is None: return "?"
        return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")

    pooled, midonly = {}, {}
    for d1, gap, d10 in recs:
        pooled.setdefault(band(d1), []).append(d10)
        if gb(gap) == "MID":
            midonly.setdefault(band(d1), []).append(d10)

    print("=== close-in-range vs d10 (POOLED) ===")
    for k in ("closed WEAK <0.33", "closed MID 0.33-0.66", "closed STRONG >=0.67"):
        st = stats(pooled.get(k, []))
        if st: print(f"  {k:24} n={st[0]:<4} win={st[1]:5.1f}% med={st[2]:+6.1f} mean={st[3]:+6.1f}")

    print("\n=== within MID gap (the only trade — is CIR a confirmation?) ===")
    for k in ("closed WEAK <0.33", "closed MID 0.33-0.66", "closed STRONG >=0.67"):
        st = stats(midonly.get(k, []))
        if st: print(f"  {k:24} n={st[0]:<4} win={st[1]:5.1f}% med={st[2]:+6.1f} mean={st[3]:+6.1f}")
    print("\nRead: if MID + STRONG close beats MID + WEAK close by a real margin,")
    print("CIR earns a spot as a same-day confirmation on the trade you take.")

if __name__ == "__main__":
    main()
