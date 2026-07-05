#!/usr/bin/env python3
"""compute_journal_outcomes.py (v2) — derive pnl_pct/outcome/entry_date nightly.
Real schema: symbol, action (BUY/SELL), quantity, price, timestamp.
SELL rows get FIFO pnl (derived -> DO UPDATE); thesis auto-snapshot fill-empty only.
  venv/bin/python _scripts/compute_journal_outcomes.py [--apply]"""
import os, sys, argparse
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def fifo_pair(rows):
    lots, out = [], {}
    for rid, side, qty, price, d in rows:
        try:
            qty = float(qty or 0); price = float(price or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0 or price <= 0:
            continue
        if side == "BUY":
            lots.append([qty, price, d])
        elif side == "SELL":
            need, cost, first_date = qty, 0.0, None
            for lot in lots:
                if need <= 0: break
                take = min(lot[0], need)
                cost += take * lot[1]; lot[0] -= take; need -= take
                if first_date is None: first_date = lot[2]
            matched = qty - need
            if matched > 0 and cost > 0:
                avg = cost / matched
                out[rid] = (round((price - avg) / avg * 100, 2), first_date)
            lots = [l for l in lots if l[0] > 1e-9]
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
    cur.execute("""SELECT id, UPPER(symbol), UPPER(action), quantity, price,
                          COALESCE(entry_date, timestamp::date)
                   FROM trade_journal
                   WHERE symbol IS NOT NULL AND action IS NOT NULL
                   ORDER BY timestamp NULLS LAST, id""")
    by_sym = {}
    for rid, sym, side, qty, price, d in cur.fetchall():
        by_sym.setdefault(sym, []).append((rid, side, qty, price, d))
    if not by_sym:
        print("trade_journal is empty — nothing to compute (expected until your first synced trade).")
    upd = 0
    for sym, rows in sorted(by_sym.items()):
        for rid, (pnl, entry) in fifo_pair(rows).items():
            outcome = "scratch" if abs(pnl) < 0.25 else ("win" if pnl > 0 else "loss")
            print(f"  {sym:12} sell id={rid}: pnl={pnl:+.2f}% -> {outcome} (entry {entry})")
            if a.apply:
                cur.execute("""UPDATE trade_journal SET pnl_pct=%s, outcome=%s,
                               entry_date=COALESCE(entry_date,%s) WHERE id=%s""",
                            (pnl, outcome, entry, rid))
                upd += cur.rowcount
    thesis_sql = """
        UPDATE trade_journal j SET thesis =
          'auto: bucket=' || COALESCE(c.gap_bucket,'?')
          || ' gap=' || COALESCE(ROUND(c.listing_gap_pct::numeric,1)::text,'?') || '%%'
          || ' peerPE=' || COALESCE(ROUND(c.ipo_pe::numeric,1)::text,'?')
          || '/' || COALESCE(ROUND(c.peer_median_pe::numeric,1)::text,'?')
        FROM ipo_consolidated c
        WHERE j.thesis IS NULL AND j.symbol IS NOT NULL
          AND UPPER(REGEXP_REPLACE(COALESCE(c.symbol_final, c.nse_symbol, c.symbol),'\\.NS$','')) = UPPER(j.symbol)"""
    if a.apply:
        cur.execute(thesis_sql); print(f"thesis auto-snapshots: {cur.rowcount}")
        conn.commit(); print(f"APPLIED: {upd} sell rows updated.")
    else:
        print("DRY-RUN — add --apply to write.")
    conn.close()

if __name__ == "__main__":
    main()
