#!/usr/bin/env python3
"""
compute_sector_rotation.py — populates the sector_rotation table that the Sector
Leadership panel reads (app/api/sector-rotation). Aggregates stock_fundamentals by
industry_group and scores each sector 0-100.

Self-defending: it introspects which columns stock_fundamentals actually has, so a
missing column can't crash it. Full rebuild each run (DELETE + INSERT).

Run:  python _scripts/engines/compute_sector_rotation.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, json, psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

# candidate metric columns → the aggregate alias the UI expects
CANDIDATES = {
    "return_3m": "AVG(NULLIF({c},0))",
    "return_6m": "AVG(NULLIF({c},0))",
    "roce": "AVG(NULLIF({c},0))",
    "sales_growth_3y": "AVG(NULLIF({c},0))",
    "pat_growth": "AVG(NULLIF({c},0))",
    "pe": "AVG(NULLIF({c},0))",
    "pe_ratio": "AVG(NULLIF({c},0))",
    "pbv": "AVG(NULLIF({c},0))",
    "pb_ratio": "AVG(NULLIF({c},0))",
    "market_cap": "SUM(COALESCE({c},0))",
}

def cols_present(cur):
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='stock_fundamentals'""")
    return {r[0] for r in cur.fetchall()}

def main():
    conn = psycopg2.connect(URL); conn.autocommit = True; cur = conn.cursor()
    have = cols_present(cur)
    if "industry_group" not in have:
        sys.exit("stock_fundamentals has no industry_group column — cannot compute sectors")

    # map each present candidate to the alias the UI selects
    alias = {"return_3m":"return_3m","return_6m":"return_6m","roce":"avg_roce",
             "sales_growth_3y":"avg_sales_growth_3y","pat_growth":"avg_pat_growth",
             "pe":"avg_pe","pe_ratio":"avg_pe","pbv":"avg_pbv","pb_ratio":"avg_pbv",
             "market_cap":"total_mcap_cr"}
    selects, seen = [], set()
    for col, agg in CANDIDATES.items():
        a = alias[col]
        if col in have and a not in seen:
            selects.append(f"{agg.format(c=col)} AS {a}")
            seen.add(a)
    for a in ["return_3m","return_6m","avg_roce","avg_sales_growth_3y","avg_pat_growth",
              "avg_pe","avg_pbv","total_mcap_cr"]:
        if a not in seen:
            selects.append(f"NULL::numeric AS {a}")

    q = f"""
        SELECT industry_group, COUNT(*) AS stock_count, {", ".join(selects)}
        FROM stock_fundamentals
        WHERE industry_group IS NOT NULL AND industry_group <> ''
        GROUP BY industry_group
        HAVING COUNT(*) >= 2
    """
    cur.execute(q)
    rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]

    # top 3 stocks per sector by business_dna_score (if present)
    tops = {}
    if "business_dna_score" in have and "nse_symbol" in have:
        cur.execute("""
            SELECT industry_group, nse_symbol FROM (
              SELECT industry_group, nse_symbol,
                     ROW_NUMBER() OVER (PARTITION BY industry_group
                       ORDER BY business_dna_score DESC NULLS LAST) rn
              FROM stock_fundamentals
              WHERE industry_group IS NOT NULL) t
            WHERE rn <= 3""")
        for ig, sym in cur.fetchall():
            tops.setdefault(ig, []).append(sym)

    def f(v): return float(v) if v is not None else 0.0
    def score(r):
        s = 50 + 0.45*f(r["return_6m"]) + 0.25*f(r["return_3m"]) \
              + 0.6*(f(r["avg_roce"]) - 12) + 0.15*f(r["avg_pat_growth"])
        return max(0, min(100, round(s)))
    def signal(sc): return ("Strong Rotate In" if sc>=75 else "Rotate In" if sc>=60
                            else "Neutral" if sc>=40 else "Rotate Out" if sc>=25 else "Avoid")
    def trend(r):  return "Accelerating" if f(r["return_3m"]) >= f(r["return_6m"])/2 else "Decelerating"

    # rebuild table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_rotation (
            industry_group TEXT PRIMARY KEY, stock_count INT,
            return_3m NUMERIC, return_6m NUMERIC, avg_roce NUMERIC,
            avg_sales_growth_3y NUMERIC, avg_pat_growth NUMERIC,
            avg_pe NUMERIC, avg_pbv NUMERIC, total_mcap_cr NUMERIC,
            rotation_score INT, rotation_signal TEXT, rotation_trend TEXT,
            top_stocks JSONB, updated_at TIMESTAMPTZ DEFAULT now())
    """)
    for c,t in [("rotation_trend","TEXT"),("top_stocks","JSONB"),("updated_at","TIMESTAMPTZ DEFAULT now()")]:
        cur.execute(f"ALTER TABLE sector_rotation ADD COLUMN IF NOT EXISTS {c} {t}")
    cur.execute("DELETE FROM sector_rotation")

    for r in rows:
        sc = score(r)
        cur.execute("""
            INSERT INTO sector_rotation
              (industry_group, stock_count, return_3m, return_6m, avg_roce,
               avg_sales_growth_3y, avg_pat_growth, avg_pe, avg_pbv, total_mcap_cr,
               rotation_score, rotation_signal, rotation_trend, top_stocks, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        """, (r["industry_group"], r["stock_count"], r["return_3m"], r["return_6m"], r["avg_roce"],
              r["avg_sales_growth_3y"], r["avg_pat_growth"], r["avg_pe"], r["avg_pbv"], r["total_mcap_cr"],
              sc, signal(sc), trend(r), json.dumps(tops.get(r["industry_group"], []))))

    print(f"sector_rotation rebuilt: {len(rows)} sectors")
    for r in sorted(rows, key=score, reverse=True)[:5]:
        sc = score(r)
        print(f"  {r['industry_group'][:28]:28s} score={sc:3d} {signal(sc):16s} 6m={f(r['return_6m']):5.1f}%")
    conn.close()

if __name__ == "__main__":
    main()
