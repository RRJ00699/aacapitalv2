#!/usr/bin/env python3
"""
import_bulk_block_history.py — bulk-load historical NSE bulk & block deal CSVs into
institutional_large_deals (the SAME table the daily fetch_institutional_deals.py writes).

WHY: fetch_institutional_deals.py only captures *today's* deals. This backfills the full
history (the BulkandBlockDealData/*.csv exports, 2016→2026) so the smart-money score and
any deal-based backtest have a real multi-year base to work from.

Point DATABASE_URL at wherever you want the history to live. The 10-year load is large,
so the intended target is your LOCAL Postgres (same place the candle history lives); Neon
stays lean and holds only the recent rolling window (see purge_old_deals.py).

CSV shape (NSE export, both bulk & block share it):
  "Date ","Symbol ","Security Name ","Client Name ","Buy / Sell ",
  "Quantity Traded ","Trade Price / Wght. Avg. Price ","Remarks "
Quirks handled: UTF-8 BOM, trailing spaces in headers/values, Indian comma grouping
(5,07,111), DD-MON-YYYY dates, BULK vs BLOCK inferred from the filename.

Run:
  python _scripts/import_bulk_block_history.py --dir data/bulk_block           # load
  python _scripts/import_bulk_block_history.py --dir data/bulk_block --dry-run  # parse only
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, csv, glob, argparse
from datetime import datetime

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")


def clean(s):
    return (s or "").strip()


def to_int(s):
    s = clean(s).replace(",", "")
    if not s or s in ("-", "NA"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def to_price(s):
    s = clean(s).replace(",", "")
    if not s or s in ("-", "NA"):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_date(s):
    s = clean(s)
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def deal_type_from_name(path):
    n = os.path.basename(path).lower()
    if "block" in n:
        return "BLOCK"
    if "bulk" in n:
        return "BULK"
    return None


def parse_file(path):
    """Yield normalized deal tuples from one CSV. Returns (rows, skipped)."""
    dtype = deal_type_from_name(path)
    if not dtype:
        print(f"  ! skip (can't tell bulk/block from name): {os.path.basename(path)}")
        return [], 0
    rows, skipped = [], 0
    # utf-8-sig strips the BOM; normalize header keys by stripping whitespace
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        reader.fieldnames = [clean(h) for h in (reader.fieldnames or [])]
        for raw in reader:
            r = {clean(k): v for k, v in raw.items()}
            d = parse_date(r.get("Date"))
            sym = clean(r.get("Symbol")).upper()
            side = clean(r.get("Buy / Sell")).upper()
            qty = to_int(r.get("Quantity Traded"))
            price = to_price(r.get("Trade Price / Wght. Avg. Price"))
            if not d or not sym or side not in ("BUY", "SELL"):
                skipped += 1
                continue
            rows.append((d, sym, clean(r.get("Client Name")), dtype, side, qty, price))
    return rows, skipped


def dedupe(rows):
    """Drop in-batch duplicates on the table's UNIQUE key so a single INSERT is clean."""
    seen, out = set(), []
    for t in rows:
        key = (t[0], t[1], t[2], t[4], t[5], t[6])  # date,ticker,client,txn,qty,price
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS institutional_large_deals (
            id SERIAL PRIMARY KEY,
            deal_date DATE NOT NULL,
            ticker TEXT NOT NULL,
            client_name TEXT,
            deal_type TEXT,
            transaction_type TEXT,
            quantity BIGINT,
            trade_price NUMERIC(14,2),
            UNIQUE (deal_date, ticker, client_name, transaction_type, quantity, trade_price)
        )
    """)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/bulk_block", help="folder of Bulk-/Block-Deals CSVs")
    ap.add_argument("--dry-run", action="store_true", help="parse + report, no DB writes")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.csv")))
    if not files:
        sys.exit(f"No CSVs found in {args.dir}")

    all_rows, total_skipped = [], 0
    for f in files:
        rows, skipped = parse_file(f)
        total_skipped += skipped
        all_rows += rows
        print(f"  {os.path.basename(f):<48} parsed {len(rows):>7,}  skipped {skipped}")

    all_rows = dedupe(all_rows)
    if all_rows:
        dmin = min(r[0] for r in all_rows)
        dmax = max(r[0] for r in all_rows)
        tickers = len({r[1] for r in all_rows})
        print(f"\nTotal: {len(all_rows):,} unique deals · {tickers:,} tickers · {dmin} → {dmax} · skipped {total_skipped}")
    else:
        print("\nNo valid rows parsed.")
        return

    if args.dry_run:
        print("\n--dry-run: no rows written. Sample (first 3):")
        for t in all_rows[:3]:
            print("  ", t)
        return

    if not URL:
        sys.exit("DATABASE_URL not set")
    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(URL); conn.autocommit = False
    cur = conn.cursor()
    ensure_table(cur); conn.commit()

    # True insert count via COUNT before/after — execute_values' cur.rowcount only reflects
    # its last internal page (page_size), so summing it massively under-reports. Don't trust it.
    cur.execute("SELECT COUNT(*) FROM institutional_large_deals"); before = cur.fetchone()[0]

    CHUNK = 5000
    for i in range(0, len(all_rows), CHUNK):
        batch = all_rows[i:i + CHUNK]
        try:
            execute_values(cur, """
                INSERT INTO institutional_large_deals
                  (deal_date, ticker, client_name, deal_type, transaction_type, quantity, trade_price)
                VALUES %s
                ON CONFLICT (deal_date, ticker, client_name, transaction_type, quantity, trade_price)
                DO NOTHING
            """, batch, page_size=len(batch))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"  ! chunk {i//CHUNK} failed: {e}")

    cur.execute("SELECT COUNT(*) FROM institutional_large_deals"); after = cur.fetchone()[0]
    cur.close(); conn.close()
    print(f"\ninstitutional_large_deals: {after - before:,} new rows inserted; "
          f"table now holds {after:,} total ({len(all_rows):,} parsed this run, dups ignored).")


if __name__ == "__main__":
    main()
