#!/usr/bin/env python3
"""
compute_convergence_ranking.py — scores every stock's 5-factor convergence and writes
a ranked convergence_ranking table that the Today screen's "Top Convergence" panel reads
(via /api/convergence/ranking). Until now that panel showed the technical screener; this
makes it show the SAME convergence score users see when they open a stock in the workbook.

Formula (identical to /api/investment-command-center):
    convergence = business*0.28 + earnings*0.22 + technical*0.25 + smart*0.15 + sector*0.10
  business  = business_dna_score | business_score | 55
  earnings  = es.score | es.earnings_momentum_score | f.earnings_score | 50
  technical = (ts.score | ts.convergence_score | w.technical_score | 50) + nr7(10) + breakout(8)
  smart     = f.smart_money_score | sm.smart_money_score | 50
  sector    = f.sector_rotation_score | sector_rotation.rotation_score | 50

Full rebuild each run (DROP+CREATE, so a stale schema can't shadow it).
Run:  python _scripts/engines/compute_convergence_ranking.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, psycopg2, psycopg2.extras

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")


def num(v, fb=0.0):
    try:
        if v is None:
            return fb
        return float(v)
    except (TypeError, ValueError):
        return fb


def pick(*vals):
    """First non-null/non-empty numeric, else the last arg as default."""
    default = vals[-1]
    for v in vals[:-1]:
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return float(default)


def load_table(cur, q):
    """Run a query, return list of dict rows. Empty list if the table/column is missing."""
    try:
        cur.execute(q)
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def main():
    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Base universe + per-table snapshots, keyed by symbol. SELECT * so a missing
    # column never crashes us — we read with .get() and fall back to formula defaults.
    fund = {r["nse_symbol"]: r for r in load_table(cur,
            "SELECT * FROM stock_fundamentals WHERE nse_symbol IS NOT NULL")}
    tech = {r["symbol"]: r for r in load_table(cur,
            "SELECT * FROM technical_signals WHERE symbol IS NOT NULL")}
    wdna = {r["tradingsymbol"]: r for r in load_table(cur,
            "SELECT * FROM weekly_dna WHERE tradingsymbol IS NOT NULL")}
    smart = {r["nse_symbol"]: r for r in load_table(cur,
            "SELECT * FROM smart_money_summary WHERE nse_symbol IS NOT NULL")}
    # latest earnings-acceleration row per symbol
    earn = {}
    for r in load_table(cur, """SELECT DISTINCT ON (symbol) * FROM earnings_acceleration_scores
                                WHERE symbol IS NOT NULL ORDER BY symbol, scored_at DESC NULLS LAST"""):
        earn[r["symbol"]] = r
    # sector rotation score by industry_group
    sect = {r["industry_group"]: r for r in load_table(cur,
            "SELECT industry_group, rotation_score FROM sector_rotation")}

    if not fund:
        sys.exit("stock_fundamentals empty — cannot rank convergence")

    def clamp(x):
        return max(0.0, min(100.0, x))

    out = []
    for sym, f in fund.items():
        ts = tech.get(sym, {})
        w  = wdna.get(sym, {})
        es = earn.get(sym, {})
        sm = smart.get(sym, {})
        ig = f.get("industry_group")
        sr = sect.get(ig, {}) if ig else {}

        business = clamp(pick(f.get("business_dna_score"), f.get("business_score"), 55))
        earnings = clamp(pick(es.get("score"), es.get("earnings_momentum_score"), f.get("earnings_score"), 50))
        tech_base = pick(ts.get("score"), ts.get("convergence_score"), w.get("technical_score"), 50)
        technical = clamp(tech_base + (10 if w.get("is_nr7") else 0) + (8 if w.get("breakout_ready") else 0))
        smartm = clamp(pick(f.get("smart_money_score"), sm.get("smart_money_score"), 50))
        sector = clamp(pick(f.get("sector_rotation_score"), sr.get("rotation_score"), 50))

        convergence = round(clamp(business*0.28 + earnings*0.22 + technical*0.25 + smartm*0.15 + sector*0.10))
        action = "BUY" if convergence >= 70 else "WATCH" if convergence >= 55 else "HOLD"
        name = f.get("name") or sym
        out.append((sym, name, convergence, round(business), round(earnings),
                    round(technical), round(smartm), round(sector), action))

    # rebuild table
    cur.execute("DROP TABLE IF EXISTS convergence_ranking")
    cur.execute("""
        CREATE TABLE convergence_ranking (
            symbol      TEXT PRIMARY KEY,
            name        TEXT,
            convergence INT,
            business    INT,
            earnings    INT,
            technical   INT,
            smart_money INT,
            sector      INT,
            action      TEXT,
            updated_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    psycopg2.extras.execute_values(cur, """
        INSERT INTO convergence_ranking
          (symbol, name, convergence, business, earnings, technical, smart_money, sector, action)
        VALUES %s
    """, out)

    print(f"convergence_ranking rebuilt: {len(out)} stocks")
    for row in sorted(out, key=lambda r: r[2], reverse=True)[:10]:
        print(f"  {row[0]:14s} conv={row[2]:3d}  biz={row[3]:3d} earn={row[4]:3d} tech={row[5]:3d} sm={row[6]:3d} sec={row[7]:3d}  {row[8]}")
    conn.close()


if __name__ == "__main__":
    main()
