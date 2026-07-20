#!/usr/bin/env python3
"""
compute_convergence_ranking.py — rebuilds the Today screen's Top Convergence list.
(The original was VM-only and died in a nightly git reset; the table froze. This is
the permanent, in-repo replacement. snapshot_convergence.py runs right after it.)

Five factors, each 0-100 percentile-ranked across the universe, weights renormalized
over whichever sources exist (introspected at runtime — missing table = factor skipped,
never a crash):
  BUSINESS   stock_fundamentals: roce, roe, low debt_to_equity
  EARNINGS   financial_dna.dna_score (10-yr financial quality engine)
  TECHNICAL  price_candles: 20d return, 60d return, proximity to 60d high
  SMART      institutional_large_deals 30d net buy value + delivery% trend (20d vs 60d)
  SECTOR     industry-average 20d return (via stock_fundamentals.industry)

Universe: stock_fundamentals symbols with candles fresh within 10 days and >=40 rows.
Writes convergence_ranking (symbol + nse_symbol both populated; action by percentile).
  venv/bin/python _scripts/compute_convergence_ranking.py
"""
import os, sys, datetime as dt
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def pct_rank(vals):
    """dict sym->value  ->  dict sym->0..100 percentile (None-safe)."""
    items = [(s, v) for s, v in vals.items() if v is not None]
    if not items: return {}
    items.sort(key=lambda x: x[1])
    n = len(items)
    return {s: round(i / max(1, n - 1) * 100, 1) for i, (s, _) in enumerate(items)}

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = {r[0] for r in cur.fetchall()}
    need = "stock_fundamentals" in tables and "price_candles" in tables
    if not need: sys.exit("stock_fundamentals/price_candles missing — nothing to rank")

    cur.execute("""SELECT UPPER(nse_symbol), name, industry, roce, roe, debt_to_equity
                   FROM stock_fundamentals WHERE nse_symbol IS NOT NULL""")
    fund = {r[0]: r[1:] for r in cur.fetchall()}
    print(f"fundamentals: {len(fund)} symbols")

    cur.execute("""SELECT UPPER(symbol), ARRAY_AGG(close ORDER BY date) closes, MAX(date)
                   FROM price_candles WHERE date >= CURRENT_DATE - 130
                   GROUP BY 1 HAVING COUNT(*) >= 40""")
    tech_raw, uni = {}, []
    today = dt.date.today()
    for sym, closes, mx in cur.fetchall():
        if sym not in fund or (today - mx).days > 10: continue
        c = [float(x) for x in closes if x]
        if len(c) < 40: continue
        uni.append(sym)
        r20 = (c[-1] / c[-21] - 1) * 100 if len(c) > 21 else None
        r60 = (c[-1] / c[-61] - 1) * 100 if len(c) > 61 else (c[-1] / c[0] - 1) * 100
        hi60 = max(c[-60:]); prox = (c[-1] / hi60 - 1) * 100 if hi60 else None
        tech_raw[sym] = (0.4 * (r20 or 0) + 0.4 * (r60 or 0) + 0.2 * (prox or 0))
        fund[sym] = fund[sym] + (r20,)   # keep r20 for sector factor
    print(f"universe (fresh candles): {len(uni)}")
    if len(uni) < 20: sys.exit("universe too small — check candle coverage")

    # BUSINESS
    biz = pct_rank({s: ((float(fund[s][2] or 0)) + (float(fund[s][3] or 0))
                        - min(float(fund[s][4] or 0), 3) * 5) for s in uni})
    # EARNINGS via financial_dna
    earn = {}
    if "financial_dna" in tables:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='financial_dna'")
        cols = {r[0] for r in cur.fetchall()}
        symc = "nse_symbol" if "nse_symbol" in cols else ("symbol" if "symbol" in cols else None)
        if symc and "dna_score" in cols:
            cur.execute(f"SELECT UPPER({symc}), dna_score FROM financial_dna WHERE dna_score IS NOT NULL")
            dna = {r[0]: float(r[1]) for r in cur.fetchall()}
            earn = pct_rank({s: dna.get(s) for s in uni})
    # TECHNICAL
    tech = pct_rank(tech_raw)
    # SMART MONEY
    smart = {}
    sm_raw = {s: 0.0 for s in uni}; have_sm = False
    if "institutional_large_deals" in tables:
        cur.execute("""SELECT UPPER(ticker),
                              SUM(CASE WHEN UPPER(transaction_type) LIKE 'B%%' THEN quantity*trade_price
                                       ELSE -quantity*trade_price END)
                       FROM institutional_large_deals
                       WHERE deal_date >= CURRENT_DATE - 30 GROUP BY 1""")
        for sym, net in cur.fetchall():
            if sym in sm_raw and net is not None:
                sm_raw[sym] += float(net) / 1e7; have_sm = True
    if "delivery_data" in tables:
        cur.execute("""SELECT UPPER(symbol),
                              AVG(delivery_percentage) FILTER (WHERE date >= CURRENT_DATE-20)
                            - AVG(delivery_percentage) FILTER (WHERE date < CURRENT_DATE-20)
                       FROM delivery_data WHERE date >= CURRENT_DATE-60 GROUP BY 1""")
        for sym, trend in cur.fetchall():
            if sym in sm_raw and trend is not None:
                sm_raw[sym] += float(trend) * 2; have_sm = True
    if have_sm: smart = pct_rank(sm_raw)
    # SECTOR
    ind_ret = {}
    for s in uni:
        ind = fund[s][1]; r20 = fund[s][5] if len(fund[s]) > 5 else None
        if ind and r20 is not None: ind_ret.setdefault(ind, []).append(r20)
    ind_avg = {i: sum(v) / len(v) for i, v in ind_ret.items() if len(v) >= 3}
    sector = pct_rank({s: ind_avg.get(fund[s][1]) for s in uni})

    factors = [("business", biz, .22), ("earnings", earn, .22), ("technical", tech, .26),
               ("smart_money", smart, .18), ("sector", sector, .12)]
    active = [(n, d, w) for n, d, w in factors if d]
    wsum = sum(w for _, _, w in active)
    print("factors active:", [n for n, _, _ in active])

    rows = []
    for s in uni:
        parts = {n: d.get(s) for n, d, _ in active}
        if sum(1 for v in parts.values() if v is not None) < 2: continue
        conv = sum((parts[n] or 0) * w for n, _, w in active) / wsum
        rows.append((s, fund[s][0], round(conv, 1),
                     parts.get("business"), parts.get("earnings"), parts.get("technical"),
                     parts.get("smart_money"), parts.get("sector")))
    rows.sort(key=lambda r: -r[2])
    n = len(rows)
    cur.execute("DROP TABLE IF EXISTS convergence_ranking")
    cur.execute("""CREATE TABLE convergence_ranking (
        symbol TEXT PRIMARY KEY, nse_symbol TEXT, name TEXT, convergence NUMERIC,
        business NUMERIC, earnings NUMERIC, technical NUMERIC, smart_money NUMERIC,
        sector NUMERIC, action TEXT, computed_at TIMESTAMPTZ DEFAULT now())""")
    for i, r in enumerate(rows):
        action = "STRONG" if i < n * 0.03 else ("RESEARCH" if i < n * 0.12 else "WATCH")
        cur.execute("""INSERT INTO convergence_ranking
            (symbol, nse_symbol, name, convergence, business, earnings, technical,
             smart_money, sector, action) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (r[0], r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], action))
    conn.commit(); conn.close()
    print(f"convergence_ranking: {n} rows rebuilt. Top 5:")
    for r in rows[:5]:
        print(f"  {r[0]:14} conv={r[2]:5}  biz={r[3]} earn={r[4]} tech={r[5]} smart={r[6]} sect={r[7]}")

if __name__ == "__main__":
    main()
