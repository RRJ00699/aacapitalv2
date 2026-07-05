#!/usr/bin/env python3
"""
sync_trade_journal.py — pull TODAY's completed Kite orders into trade_journal (VM-side).

Why: the web route (app/api/trade-journal) only syncs when you open the page;
Kite's orders() only returns TODAY — an unvisited day is lost forever. This runs
in the 16:00 IST nightly (post-close), so every trading day is captured whether
or not you open the app. Idempotent: ON CONFLICT (broker_order_id) DO NOTHING.

  venv/bin/python _scripts/sync_trade_journal.py            # writes (safe/idempotent)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not DB:
    sys.exit("DATABASE_URL not set")

def main():
    import psycopg2
    from kite_connect import get_kite
    kite = get_kite()
    orders = kite.orders() or []
    done = [o for o in orders if o.get("status") == "COMPLETE"]
    print(f"kite orders today: {len(orders)} total, {len(done)} COMPLETE")
    if not done:
        print("nothing to sync."); return
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
    ins = 0
    for o in done:
        cur.execute("""
            INSERT INTO trade_journal (broker_order_id, tradingsymbol, exchange,
                transaction_type, quantity, price, trade_date, product, order_type,
                status, symbol, entry_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'COMPLETE',UPPER(%s),%s::date)
            ON CONFLICT (broker_order_id) DO NOTHING""",
            (str(o.get("order_id")), o.get("tradingsymbol"), o.get("exchange"),
             o.get("transaction_type"), o.get("filled_quantity"),
             o.get("average_price"), str(o.get("order_timestamp")),
             o.get("product"), o.get("order_type"),
             o.get("tradingsymbol"), str(o.get("order_timestamp"))[:10]))
        ins += cur.rowcount
    conn.commit(); conn.close()
    print(f"synced {ins} new order(s) into trade_journal.")

if __name__ == "__main__":
    main()
