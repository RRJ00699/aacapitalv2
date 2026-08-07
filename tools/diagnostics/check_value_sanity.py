#!/usr/bin/env python3
"""
check_value_sanity.py — the VALUE-range layer of the health gate (Rule 1, "platinum move").
check_data_contract.py answers "is the column populated?". This answers "are the values
PLAUSIBLE?" — garbage that slipped past a writer (prices<=0, pct out of 0-100, dates out of
range, listing_open miles from issue_price, absurd P/E) is caught, not silently protected.
Schema-robust: a check whose columns don't exist is skipped (never crashes). NULLs are NOT
violations — only PRESENT values are judged.
  python tools/diagnostics/check_value_sanity.py                # report; exit 1 on any HARD violation
  python tools/diagnostics/check_value_sanity.py --fail-on-warn
  python tools/diagnostics/check_value_sanity.py --table ipo_consolidated
Needs DATABASE_URL.
"""
import os, sys, argparse
try: import psycopg2
except ImportError: sys.exit("pip install psycopg2-binary --break-system-packages")

CHECKS = [
    ("issue_price > 0",              ["issue_price"],
        "issue_price IS NOT NULL AND issue_price <= 0", "HARD"),
    ("listing_open > 0",             ["listing_open"],
        "listing_open IS NOT NULL AND listing_open <= 0", "HARD"),
    ("listing_gap_pct in [-100,500]",["listing_gap_pct"],
        "listing_gap_pct IS NOT NULL AND (listing_gap_pct < -100 OR listing_gap_pct > 500)", "HARD"),
    ("peer_median_pe in (0,500]",    ["peer_median_pe"],
        "peer_median_pe IS NOT NULL AND (peer_median_pe <= 0 OR peer_median_pe > 500)", "HARD"),
    ("ipo_pe sane (0,2000)",         ["ipo_pe"],
        "ipo_pe IS NOT NULL AND (ipo_pe < 0 OR ipo_pe > 2000)", "WARN"),
    ("roe in [-100,300]%",           ["roe"],
        "roe IS NOT NULL AND (roe < -100 OR roe > 300)", "WARN"),
    ("listing_date in range",        ["listing_date"],
        "listing_date IS NOT NULL AND (listing_date < DATE '2005-01-01' OR listing_date > CURRENT_DATE + 90)", "HARD"),
    ("open_date <= close_date",      ["open_date", "close_date"],
        "open_date IS NOT NULL AND close_date IS NOT NULL AND open_date > close_date", "HARD"),
    ("total_subscription_x >= 0",    ["total_subscription_x"],
        "total_subscription_x IS NOT NULL AND total_subscription_x < 0", "HARD"),
    ("listing_open near issue_price",["listing_open", "issue_price"],
        "listing_open IS NOT NULL AND issue_price IS NOT NULL AND issue_price > 0 "
        "AND (listing_open < 0.3*issue_price OR listing_open > 5*issue_price)", "WARN"),
]

def colset(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r[0] for r in cur.fetchall()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="ipo_intelligence")
    ap.add_argument("--fail-on-warn", action="store_true")
    ap.add_argument("--id-col", default="nse_symbol")
    a = ap.parse_args()
    u = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL.")
    conn = psycopg2.connect(u); cur = conn.cursor()
    cols = colset(cur, a.table)
    if not cols: sys.exit(f"table {a.table} not found.")
    idc = a.id_col if a.id_col in cols else None
    print(f"\nVALUE-SANITY  ({a.table})\n" + "="*72)
    print(f"{'CHECK':34}{'SEV':>6}{'BAD':>7}  examples")
    print("-"*72)
    hard_bad = warn_bad = skipped = 0
    for name, need, pred, sev in CHECKS:
        if not all(c in cols for c in need):
            print(f"{name[:33]:34}{'skip':>6}{'-':>7}  (missing {', '.join(c for c in need if c not in cols)})")
            skipped += 1; continue
        cur.execute(f"SELECT count(*) FROM {a.table} WHERE {pred}")
        bad = cur.fetchone()[0]; ex = ""
        if bad and idc:
            cur.execute(f"SELECT {idc} FROM {a.table} WHERE {pred} AND {idc} IS NOT NULL LIMIT 3")
            ex = ", ".join(str(r[0]) for r in cur.fetchall())
        print(f"{name[:33]:34}{sev:>6}{bad:>7}  {ex}")
        if bad:
            if sev == "HARD": hard_bad += 1
            else: warn_bad += 1
    conn.close()
    print("-"*72)
    print(f"{len(CHECKS)-skipped} checks run, {skipped} skipped | {hard_bad} HARD, {warn_bad} WARN with violations")
    if hard_bad or (a.fail_on_warn and warn_bad):
        print("\nFAIL — implausible values present. Fix the source/writer before trusting the data."); sys.exit(1)
    print("\nPASS — all present values are within sane ranges."); sys.exit(0)

if __name__ == "__main__":
    main()
