#!/usr/bin/env python3
"""match_anchor_deals.py — anchor-conviction signal: joins NSE bulk/block deals
(institutional_large_deals) against each IPO's anchor names in the listing->+75d
window. ANCHOR SELL below issue = distributing at a loss; silence under issue =
holding with conviction. Writes anchor_deal_signals (derived -> DO UPDATE ok).
  venv/bin/python _scripts/match_anchor_deals.py [--apply]"""
import os, sys, json, argparse
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
THRESH = 86

def anchors_of(raw):
    if not raw:
        return []
    s = str(raw).strip()
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except (ValueError, TypeError):
        pass
    return [p.strip() for p in s.split(",") if p.strip()]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    from rapidfuzz import fuzz
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS anchor_deal_signals (
                     id SERIAL PRIMARY KEY, symbol TEXT NOT NULL, company_name TEXT,
                     deal_date DATE, client_name TEXT, matched_anchor TEXT,
                     match_score INT, deal_type TEXT, side TEXT,
                     quantity BIGINT, trade_price NUMERIC, issue_price NUMERIC,
                     below_issue BOOLEAN, created_at TIMESTAMPTZ DEFAULT now(),
                     UNIQUE (symbol, deal_date, client_name, side, quantity))""")
    cur.execute("""SELECT UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)), company_name,
                          anchor_names, issue_price, listing_date
                   FROM ipo_intelligence
                   WHERE anchor_names IS NOT NULL
                     AND COALESCE(NULLIF(nse_symbol,''), symbol) IS NOT NULL
                     AND listing_date IS NOT NULL""")
    ipos = cur.fetchall()
    print(f"IPOs with anchor names: {len(ipos)}")
    found = wrote = 0
    for sym, name, raw_anchors, issue_px, ldate in ipos:
        anchors = anchors_of(raw_anchors)
        if not anchors:
            continue
        cur.execute("""SELECT deal_date, client_name, deal_type, transaction_type,
                              quantity, trade_price
                       FROM institutional_large_deals
                       WHERE UPPER(ticker) = %s
                         AND deal_date BETWEEN %s AND %s::date + 75""",
                    (sym, ldate, ldate))
        for ddate, client, dtype, side, qty, px in cur.fetchall():
            best, best_a = 0, None
            for anc in anchors:
                sc = fuzz.partial_ratio((client or "").upper(), anc.upper())
                if sc > best:
                    best, best_a = sc, anc
            if best < THRESH:
                continue
            found += 1
            below = (px is not None and issue_px is not None and float(px) < float(issue_px))
            tag = "DISTRIBUTING-AT-LOSS" if (side == "SELL" and below) else \
                  ("PROFIT-TAKING" if side == "SELL" else "ADDING")
            print(f"  {sym:12} {ddate} {side:4} {qty:>10} @ {px}  "
                  f"{(client or '')[:28]:28} ~ {best_a[:24]} ({best})  [{tag}]")
            if a.apply:
                cur.execute("""INSERT INTO anchor_deal_signals
                               (symbol, company_name, deal_date, client_name, matched_anchor,
                                match_score, deal_type, side, quantity, trade_price,
                                issue_price, below_issue)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (symbol, deal_date, client_name, side, quantity)
                               DO UPDATE SET match_score = EXCLUDED.match_score,
                                             below_issue = EXCLUDED.below_issue""",
                            (sym, name, ddate, client, best_a, best, dtype, side,
                             qty, px, issue_px, below))
                wrote += cur.rowcount
    if a.apply:
        conn.commit(); print(f"anchor_deal_signals: {wrote} rows written/updated.")
    else:
        print(f"{found} anchor-matched deals found. DRY-RUN — add --apply to write.")
    conn.close()

if __name__ == "__main__":
    main()
