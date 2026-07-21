#!/usr/bin/env python3
"""data_quality_audit.py — Phase 10 step 1: measure before backtesting.

READ-ONLY. Scores the IPO master data (ipo_intelligence + ipo_consolidated +
price_candles) so 'clean the data' is a number, not a feeling. Prints per-field
coverage for the backtest-critical columns, plus the specific anomaly classes
we've actually been bitten by (blank symbols on listing morning, REIT/InvIT
rows, sub-200 rows, dupes, missing candle windows, impossible OHLC).

Run (VM):  venv/bin/python _scripts/data_quality_audit.py
Exit code 0 always — this is a report, not a gate (the gate comes when the
numbers are good enough to pin).
"""
import os
import sys


# Two-table design (owner, 2026-07-22): ipo_consolidated = THE serving table
# (UI/routes read it, jobs backfill it); ipo_intelligence = the source table.
# Each field is scored against the table that owns it; existence is verified
# via information_schema first — the audit never assumes a column.
CRITICAL = [  # (table, column, why the backtest needs it)
    ("ipo_intelligence", "company_name", "identity"),
    ("ipo_intelligence", "nse_symbol", "strong key (ticker/candles)"),
    ("ipo_intelligence", "listing_date", "window anchor"),
    ("ipo_intelligence", "issue_price", "return base"),
    ("ipo_intelligence", "listing_open", "gap rule / entry"),
    ("ipo_intelligence", "issue_size_cr", "eligibility + mega rule"),
    ("ipo_intelligence", "anchor_count", "anchor rules"),
    ("ipo_intelligence", "anchor_lock30_date", "exit window bound"),
    ("ipo_consolidated", "final_qib", "demand rules (serving)"),
    ("ipo_consolidated", "final_total", "demand rules (serving)"),
    ("ipo_consolidated", "ipo_pe", "valuation rules (serving)"),
    ("ipo_consolidated", "listing_gap_pct", "outcome label (serving)"),
]


def main() -> int:
    import psycopg2
    db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not db:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(db, connect_timeout=20)
    cur = conn.cursor()

    cur.execute("""SELECT COUNT(*) FROM ipo_intelligence
        WHERE COALESCE(is_sme,false)=false AND (issue_size_cr IS NULL OR issue_size_cr>=200)
          AND company_name !~* '\\y(REIT|InvIT)\\y'""")
    n = cur.fetchone()[0]
    print(f"ELIGIBLE UNIVERSE (intelligence): {n} IPOs\n")
    # column existence from information_schema — never assume
    cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                   WHERE table_name IN ('ipo_intelligence','ipo_consolidated')""")
    have = {(t, c) for t, c in cur.fetchall()}
    denom = {}
    for tbl in ("ipo_intelligence", "ipo_consolidated"):
        cur.execute(f"""SELECT COUNT(*) FROM {tbl}
            WHERE COALESCE(is_sme,false)=false AND (issue_size_cr IS NULL OR issue_size_cr>=200)
              AND company_name !~* '\\y(REIT|InvIT)\\y'""")
        denom[tbl] = cur.fetchone()[0]
    print(f"{'table.field':40} {'coverage':>10}  purpose")
    worst = []
    for tbl, col, why in CRITICAL:
        label = f"{tbl}.{col}"
        if (tbl, col) not in have:
            print(f"{label:40} {'ABSENT':>10}  {why} — column not in information_schema")
            worst.append((0.0, label))
            continue
        cur.execute(f"""SELECT COUNT(*) FROM {tbl}
            WHERE COALESCE(is_sme,false)=false AND (issue_size_cr IS NULL OR issue_size_cr>=200)
              AND company_name !~* '\\y(REIT|InvIT)\\y'
              AND {col} IS NOT NULL AND btrim({col}::text) <> ''""")
        c = cur.fetchone()[0]
        d = denom[tbl] or 1
        pctv = 100.0 * c / d
        print(f"{label:40} {pctv:9.1f}%  {why}")
        if pctv < 99.9:
            worst.append((pctv, label))

    print("\nANOMALY CLASSES (each burned us once):")
    checks = [
        ("blank BOTH symbol columns", """SELECT COUNT(*) FROM ipo_intelligence
            WHERE COALESCE(NULLIF(btrim(nse_symbol),''), NULLIF(btrim(symbol),'')) IS NULL
              AND listing_date IS NOT NULL"""),
        ("REIT/InvIT rows present", """SELECT COUNT(*) FROM ipo_intelligence
            WHERE company_name ~* '\\y(REIT|InvIT)\\y'"""),
        ("duplicate company rows", """SELECT COUNT(*) FROM (SELECT company_name FROM ipo_intelligence
            GROUP BY company_name HAVING COUNT(*)>1) d"""),
        ("listed but ZERO candles in listing..lock30", """SELECT COUNT(*) FROM ipo_intelligence i
            WHERE COALESCE(is_sme,false)=false AND (issue_size_cr IS NULL OR issue_size_cr>=200)
              AND i.listing_date IS NOT NULL AND i.listing_date <= CURRENT_DATE - 2
              AND NOT EXISTS (SELECT 1 FROM price_candles p
                    WHERE UPPER(p.symbol)=UPPER(COALESCE(NULLIF(btrim(i.nse_symbol),''), btrim(i.symbol)))
                      AND p.date BETWEEN i.listing_date
                          AND COALESCE(i.anchor_lock30_date,(i.listing_date+INTERVAL '30 days')::date))"""),
        ("impossible OHLC candles", """SELECT COUNT(*) FROM price_candles
            WHERE NOT (open>0 AND high>=GREATEST(open,close) AND low<=LEAST(open,close) AND high>=low)"""),
        ("listing_open present but issue_price missing", """SELECT COUNT(*) FROM ipo_intelligence
            WHERE listing_open IS NOT NULL AND issue_price IS NULL"""),
    ]
    for label, q in checks:
        cur.execute(q)
        c = cur.fetchone()[0]
        print(f"  {'✓' if c == 0 else '!'} {label}: {c}")

    if worst:
        print("\nBACKFILL PRIORITY (worst coverage first):")
        for pctv, label in sorted(worst):
            print(f"  {label}: {pctv:.1f}% -> NSE archive / official docs (see docs/DETAILS_AND_REVIEW.md matrix)")
    print("\nCandle gaps -> run: venv/bin/python _scripts/backfill_listing_window_candles.py --apply")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
