#!/usr/bin/env python3
"""sync_trade_journal.py (v2) — pull TODAY's completed Kite orders into trade_journal.
Real schema: symbol, action, quantity, price, timestamp, broker, broker_order_id,
entry_date. Verifies columns first, FAILS LOUDLY on mismatch. SELECT-before-INSERT
on broker_order_id = idempotent. Runs in the 16:00 IST nightly.
  venv/bin/python _scripts/sync_trade_journal.py"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
NEED = {"broker_order_id", "symbol", "exchange", "action", "quantity",
        "price", "timestamp", "broker", "entry_date"}

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    from kite_connect import get_kite
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='trade_journal'")
    have = {c for (c,) in cur.fetchall()}
    missing = NEED - have
    if missing:
        sys.exit(f"SCHEMA MISMATCH — trade_journal lacks {sorted(missing)}. Refusing to guess.")
    kite = get_kite()
    orders = kite.orders() or []
    done = [o for o in orders if o.get("status") == "COMPLETE"]
    print(f"kite orders today: {len(orders)} total, {len(done)} COMPLETE")
    ins = skip = 0
    for o in done:
        oid = str(o.get("order_id") or "").strip()
        if not oid: continue
        cur.execute("SELECT 1 FROM trade_journal WHERE broker_order_id = %s", (oid,))
        if cur.fetchone():
            skip += 1; continue
        ts = str(o.get("order_timestamp") or "")
        cur.execute("""INSERT INTO trade_journal
                         (broker_order_id, symbol, exchange, action, quantity,
                          price, timestamp, broker, entry_date)
                       VALUES (%s, UPPER(%s), %s, UPPER(%s), %s, %s, %s, 'zerodha', %s::date)
                       ON CONFLICT (broker_order_id) DO NOTHING""",
                    (oid, o.get("tradingsymbol"), o.get("exchange"),
                     o.get("transaction_type"), o.get("filled_quantity"),
                     o.get("average_price"), ts, ts[:10] or None))
        ins += 1
    conn.commit(); conn.close()
    print(f"synced {ins} new, {skip} already present.")

if __name__ == "__main__":
    main()
