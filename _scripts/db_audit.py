#!/usr/bin/env python3
"""
db_audit.py — READ-ONLY: the mess map. Per core table: row count, exact-duplicate
groups, and (for ipo_intelligence) fuzzy name duplicates with ids + listing dates
so dedupe decisions are made on evidence.

  python _scripts/db_audit.py
"""
import os, re, sys

def norm(name):
    s = (name or "").lower()
    s = re.sub(r"\b(ltd|limited|pvt|private)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

CHECKS = [
    # (table, natural-key columns for exact-dup check)
    ("ipo_intelligence",          None),  # fuzzy handled specially
    ("ipo_gmp",                   "company,date"),
    ("ipo_subscription_history",  None),
    ("price_candles",             "symbol,date"),
    ("annual_financials",         "symbol,fiscal_year"),
    ("stock_fundamentals",        "nse_symbol"),
    ("institutional_large_deals", None),
    ("delivery_data",             "symbol,date"),
    ("ipo_consolidated",          None),
]

def main():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur = psycopg2.connect(DB, connect_timeout=20).cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = {r[0] for r in cur.fetchall()}
    for t, key in CHECKS:
        if t not in tables:
            print(f"{t:28} MISSING"); continue
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        total = cur.fetchone()[0]
        line = f"{t:28} rows={total:>8}"
        if key:
            cur.execute(f"""SELECT COUNT(*) FROM (
                SELECT {key} FROM {t} GROUP BY {key} HAVING COUNT(*) > 1) d""")
            dup_groups = cur.fetchone()[0]
            line += f"  exact-dup groups on ({key}): {dup_groups}"
        print(line)
        if t == "ipo_subscription_history":
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (t,))
            print(f"    columns: {[r[0] for r in cur.fetchall()][:12]}")
        if t == "institutional_large_deals":
            cur.execute("""SELECT COUNT(*) FROM (
                SELECT ticker, deal_date, transaction_type, quantity, trade_price, COUNT(*)
                FROM institutional_large_deals
                GROUP BY 1,2,3,4,5 HAVING COUNT(*) > 1) d""")
            print(f"    exact-dup groups (ticker,date,type,qty,price): {cur.fetchone()[0]}")

    # ---- ipo_intelligence fuzzy duplicates ----
    print("\nipo_intelligence — fuzzy name-duplicate groups (same normalized name, listing within 400d):")
    cur.execute("""SELECT id, company_name, listing_date,
                          COALESCE(NULLIF(nse_symbol,''), symbol), issue_size_cr
                   FROM ipo_intelligence""")
    groups = {}
    for pid, nm, ld, sym, size in cur.fetchall():
        groups.setdefault(norm(nm), []).append((pid, nm, ld, sym, size))
    n = 0
    for k, v in sorted(groups.items()):
        if len(v) < 2: continue
        n += 1
        print(f"  [{n}] {k}")
        for pid, nm, ld, sym, size in v:
            print(f"       id={pid:<6} sym={str(sym):<12} listed={ld}  size={size}  name='{nm}'")
        if n >= 25:
            print("  ... (truncated at 25 groups)"); break
    if n == 0: print("  none 🎉")
    print("\nREAD-ONLY. Next step: targeted dedupe scripts per finding — each snapshots "
          "the affected rows to CSV before any delete, keeps the most-complete row, "
          "and requires --apply.")

if __name__ == "__main__":
    main()
