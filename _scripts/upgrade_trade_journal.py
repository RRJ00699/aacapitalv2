#!/usr/bin/env python3
"""
upgrade_trade_journal.py — make the EXISTING trade_journal table serve the
reflective-journal layer that app/api/journal/base-rate + BaseRatePanel already
query (they expect: symbol, company_name, pnl_pct, outcome, entry_date, thesis).

The table today is an execution ledger (broker_order_id, tradingsymbol, trade_date...).
This migration is ADDITIVE + fill-empty only — the ledger insert keeps working:
  1. ADD COLUMN IF NOT EXISTS: symbol, company_name, entry_date, pnl_pct,
     outcome, thesis, notes
  2. Backfill (WHERE col IS NULL only): symbol <- tradingsymbol,
     entry_date <- trade_date; company_name <- join ipo_intelligence on symbol.
pnl_pct / outcome / thesis stay NULL until you record them (that's the point —
your read vs the base rate). Dry-run default; --apply writes.

  venv/bin/python _scripts/upgrade_trade_journal.py --apply
"""
import os, sys, argparse
try:
    import psycopg2
except ImportError:
    sys.exit("use venv/bin/python")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not DB:
    sys.exit("DATABASE_URL not set (run: set -a && . ./.env && set +a)")

ADD_COLS = [
    ("symbol",       "TEXT"),
    ("company_name", "TEXT"),
    ("entry_date",   "DATE"),
    ("pnl_pct",      "NUMERIC"),
    ("outcome",      "TEXT"),      # e.g. 'win' / 'loss' / 'scratch'
    ("thesis",       "TEXT"),      # why you took the trade (gap bucket, valuation...)
    ("notes",        "TEXT"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='trade_journal'")
    have = {c for (c,) in cur.fetchall()}
    if not have:
        sys.exit("trade_journal table not found — nothing to migrate.")
    print(f"trade_journal has {len(have)} columns")

    todo = [(c, t) for c, t in ADD_COLS if c not in have]
    print(f"columns to add: {[c for c, _ in todo] or 'none (already migrated)'}")

    fills = []
    if "tradingsymbol" in have:
        fills.append(("symbol <- tradingsymbol",
                      "UPDATE trade_journal SET symbol = UPPER(tradingsymbol) "
                      "WHERE symbol IS NULL AND tradingsymbol IS NOT NULL"))
    if "trade_date" in have:
        fills.append(("entry_date <- trade_date",
                      "UPDATE trade_journal SET entry_date = trade_date::date "
                      "WHERE entry_date IS NULL AND trade_date IS NOT NULL"))
    fills.append(("company_name <- ipo_intelligence join",
                  "UPDATE trade_journal j SET company_name = i.company_name "
                  "FROM ipo_intelligence i "
                  "WHERE j.company_name IS NULL AND j.symbol IS NOT NULL "
                  "AND UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol)) = UPPER(j.symbol)"))

    if not a.apply:
        print("DRY-RUN — add --apply to run the ALTERs + fill-empty backfills above.")
        return
    for c, t in todo:
        cur.execute(f"ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS {c} {t}")
        print(f"  added {c} {t}")
    for label, q in fills:
        cur.execute(q)
        print(f"  backfill {label}: {cur.rowcount} rows")
    conn.commit()
    print("APPLIED. /dashboard/journal + BaseRatePanel now have their columns; "
          "fill pnl_pct/outcome/thesis per trade to activate the base-rate loop.")

if __name__ == "__main__":
    main()
