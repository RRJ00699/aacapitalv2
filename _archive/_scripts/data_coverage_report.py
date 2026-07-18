#!/usr/bin/env python3
"""data_coverage_report.py — the truth button. Prints row counts + freshness for every
core table so 'do we actually have it?' is answered from the phone, not from memory.
Read-only.  venv/bin/python _scripts/data_coverage_report.py"""
import os, sys
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

CHECKS = [
    ("price_candles",            "COUNT(DISTINCT symbol)", "MAX(date)"),
    ("stock_fundamentals",       "COUNT(*)",               "MAX(updated_at)::date"),
    ("annual_financials",        "COUNT(DISTINCT nse_symbol)", "MAX(fy)"),
    ("financial_dna",            "COUNT(*)",               "NULL"),
    ("delivery_data",            "COUNT(DISTINCT date)",   "MAX(date)"),
    ("institutional_large_deals","COUNT(*)",               "MAX(deal_date)"),
    ("convergence_ranking",      "COUNT(*)",               "MAX(computed_at)::date"),
    ("ipo_consolidated",         "COUNT(*)",               "NULL"),
    ("ipo_gmp",                  "COUNT(*)",               "MAX(date)"),
    ("trade_journal",            "COUNT(*)",               "NULL"),
    ("anchor_deal_signals",      "COUNT(*)",               "MAX(deal_date)"),
]

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = {r[0] for r in cur.fetchall()}
    print(f"{'table':26} {'count':>10}  freshest")
    print("-" * 55)
    for t, cnt, fresh in CHECKS:
        if t not in tables:
            print(f"{t:26} {'MISSING':>10}"); continue
        try:
            cur.execute(f"SELECT {cnt}, {fresh} FROM {t}")
            c, f = cur.fetchone()
            print(f"{t:26} {c:>10}  {f if f is not None else ''}")
        except Exception as e:
            conn.rollback(); print(f"{t:26} {'ERR':>10}  {str(e)[:40]}")
    conn.close()
    print("\nfreshest should move daily for candles/delivery/deals/convergence.")

if __name__ == "__main__":
    main()
