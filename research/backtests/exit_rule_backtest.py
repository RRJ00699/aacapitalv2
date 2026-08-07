#!/usr/bin/env python3
"""
exit_rule_backtest.py — READ-ONLY: which exit rule maximizes return after
buying the listing open? Compares, on the same 370-IPO candle universe:

  FIXED    D1 / D2 / D3 / D5 / D10 close
  TARGET   first close >= +5% / +8% / +12% -> exit there, else D5 close
  STOP     first close down >3% vs prior close -> exit there, else D5 close
  ORACLE   best close <=5 / <=10 sessions (NOT executable — upper bound only)

Per rule: win%%, median, mean, p10 tail — overall and by gap bucket (n>=30
SIGNAL, else HINT). Zero writes. Context: SEBI's 144-IPO study shows ~54%% of
allotted shares are flipped within week 1 (NII 63%%) while institutions hold —
so days 1-5 are a retail-supply regime and day 30 (anchor unlock) is the first
institutional supply event. This measures how to harvest that window.

  venv/bin/python research/backtests/exit_rule_backtest.py
"""
import os, sys
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def stats(rets):
    n = len(rets)
    if not n: return None
    s = sorted(rets)
    return dict(n=n, win=sum(1 for r in rets if r > 0) / n * 100,
                med=s[n // 2], mean=sum(rets) / n, p10=s[max(0, int(n * 0.10) - 1)])

def apply_rules(closes, entry):
    """closes: list of session closes (1-indexed conceptually). Returns {rule: ret_pct}."""
    r = {}
    pct = lambda px: (px - entry) / entry * 100
    for d in (1, 2, 3, 5, 10):
        if len(closes) >= d: r[f"D{d} close"] = pct(closes[d - 1])
    if len(closes) >= 5:
        r["ORACLE best<=5"] = max(pct(c) for c in closes[:5])
        for tgt in (5, 8, 12):
            hit = next((pct(c) for c in closes[:5] if pct(c) >= tgt), None)
            r[f"target +{tgt}% else D5"] = hit if hit is not None else pct(closes[4])
        stop = None
        for i in range(1, 5):
            if (closes[i] - closes[i - 1]) / closes[i - 1] * 100 < -3:
                stop = pct(closes[i]); break
        r["stop -3%dc else D5"] = stop if stop is not None else pct(closes[4])
    if len(closes) >= 10:
        r["ORACLE best<=10"] = max(pct(c) for c in closes[:10])
    return r

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
    cols = {r[0] for r in cur.fetchall()}
    sym = "symbol_final" if "symbol_final" in cols else "nse_symbol"
    open_col = next((c for c in ("listing_open", "listing_open_price") if c in cols), None)
    cur.execute(f"""SELECT UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$','')), c.gap_bucket,
                           {f'c.{open_col}' if open_col else 'NULL'},
                           ARRAY_AGG(p.close ORDER BY p.date), ARRAY_AGG(p.open ORDER BY p.date)
                    FROM ipo_consolidated c JOIN price_candles p
                      ON UPPER(p.symbol)=UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$',''))
                     AND p.date>=c.listing_date AND p.date<=c.listing_date+30
                    WHERE c.listing_date IS NOT NULL
                    GROUP BY 1,2,3""")
    per_rule, per_bucket = {}, {}
    used = 0
    for s, gb, lopen, closes, opens in cur.fetchall():
        closes = [float(x) for x in closes if x is not None]
        entry = float(lopen) if lopen else (float(opens[0]) if opens and opens[0] else 0)
        if entry <= 0 or len(closes) < 5: continue
        used += 1
        for rule, ret in apply_rules(closes, entry).items():
            per_rule.setdefault(rule, []).append(ret)
            if gb: per_bucket.setdefault((gb.upper(), rule), []).append(ret)
    conn.close()
    print(f"EXIT-RULE BACKTEST — entry = listing open, n={used} IPOs with >=5 session closes\n")
    print(f"{'rule':22} {'n':>4} {'win%':>6} {'med%':>7} {'mean%':>7} {'p10 tail':>9}")
    print("-" * 62)
    order = ["D1 close","D2 close","D3 close","D5 close","D10 close",
             "target +5% else D5","target +8% else D5","target +12% else D5",
             "stop -3%dc else D5","ORACLE best<=5","ORACLE best<=10"]
    for rule in order:
        st = stats(per_rule.get(rule, []))
        if st:
            print(f"{rule:22} {st['n']:>4} {st['win']:>6.1f} {st['med']:>+7.1f} {st['mean']:>+7.1f} {st['p10']:>+9.1f}")
    for gb in ("LOW", "MID", "HIGH"):
        print(f"\n--- gap bucket {gb} ---")
        for rule in order:
            st = stats(per_bucket.get((gb, rule), []))
            if st and st['n'] >= 10:
                tag = "SIGNAL" if st['n'] >= 30 else "HINT  "
                print(f"{rule:22} {st['n']:>4} {st['win']:>6.1f} {st['med']:>+7.1f} {st['mean']:>+7.1f} {st['p10']:>+9.1f}  {tag}")
    print("\nREAD-ONLY. ORACLE rows are ceilings, not strategies. Executable winner = "
          "highest mean with acceptable p10 at n>=30, consistent across buckets.")

if __name__ == "__main__":
    main()
