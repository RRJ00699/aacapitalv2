#!/usr/bin/env python3
"""
null_triage.py — READ-ONLY. Sorts every ipo_intelligence column into ONE bucket
so we know what's actually fixable vs dead schema. Judged on LISTED IPOs only
(unlisted rows have legitimately-null outcome fields).

Buckets:
  BACKTEST-READY   >=70% filled  -> usable in a backtest now
  FIXABLE-PARTIAL  10-70% filled -> a source exists, worth topping up
  DEAD-SCHEMA      <10% filled   -> no writer ever ran; prune candidate
For each non-ready column, guesses the source lane from its name.

  python _scripts/null_triage.py
"""
import os, sys

def lane(col):
    c = col.lower()
    if any(k in c for k in ("promoter","pledge","dilution")): return "Chittorgarh promoter (JS-render/probe)"
    if any(k in c for k in ("anchor",)): return "anchor scrape (accumulating nightly)"
    if any(k in c for k in ("sub_day","bid_","day1","day2","day3")): return "intraday subscription capture (unbuilt)"
    if any(k in c for k in ("gmp",)): return "ipo_gmp history (thin, accumulating)"
    if any(k in c for k in ("fresh","ofs","offer_for")): return "Chittorgarh list API (PR#29 half)"
    if any(k in c for k in ("roe","roce","pat","ebitda","margin","debt","revenue","profit","cagr")): return "annual_financials (quarterly ritual)"
    if any(k in c for k in ("score_","prob_","feature","vector","ml_","pred")): return "derived/ML (compute or DEAD)"
    if any(k in c for k in ("listing","gain_","return_","d10","days_to")): return "candles-derived (backfill_computables)"
    if any(k in c for k in ("delivery",)): return "delivery_data"
    if any(k in c for k in ("peer","pe_")): return "compute_peer_pe"
    return "unknown source"

def main():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur = psycopg2.connect(DB, connect_timeout=20).cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='ipo_intelligence' ORDER BY ordinal_position""")
    cols = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM ipo_intelligence WHERE listing_date IS NOT NULL")
    base = cur.fetchone()[0]
    q = ", ".join(f"COUNT({c})" for c in cols)
    cur.execute(f"SELECT {q} FROM ipo_intelligence WHERE listing_date IS NOT NULL")
    counts = cur.fetchone()
    ready, partial, dead = [], [], []
    for c, n in zip(cols, counts):
        pct = n / base * 100 if base else 0
        (ready if pct >= 70 else partial if pct >= 10 else dead).append((c, pct))
    print(f"listed IPOs: {base}\n")
    print(f"=== BACKTEST-READY ({len(ready)}) — >=70% filled ===")
    print("   " + ", ".join(c for c, _ in ready))
    print(f"\n=== FIXABLE-PARTIAL ({len(partial)}) — 10-70%, source exists ===")
    for c, p in sorted(partial, key=lambda x: -x[1]):
        print(f"   {c:32} {p:4.0f}%   <- {lane(c)}")
    print(f"\n=== DEAD-SCHEMA ({len(dead)}) — <10%, no writer, PRUNE candidates ===")
    for c, p in sorted(dead, key=lambda x: -x[1]):
        print(f"   {c:32} {p:4.0f}%   ({lane(c)})")
    print(f"\nSUMMARY: {len(ready)} ready | {len(partial)} fixable | {len(dead)} dead")
    print("Backtests should draw ONLY from BACKTEST-READY. Fixable = topping-up targets. "
          "Dead = prune (a lean schema is honest; nulls that can never fill are noise).")

if __name__ == "__main__":
    main()
