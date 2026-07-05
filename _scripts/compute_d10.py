#!/usr/bin/env python3
"""
compute_d10.py — nightly precompute of the founding outcome per IPO:
d10_best_pct = (best close within 10 sessions − listing open) / open × 100.

Feeds the Post-Listing audit tab and the BRLM empirical table without any
per-request candle joins. DERIVED metric -> Rule-1 DO UPDATE. Adds the column
IF NOT EXISTS. Symbol match with company-name fallback (pre-symbol IPOs skip
cleanly — they have no candles yet anyway).

  venv/bin/python _scripts/compute_d10.py           # prints coverage, writes
"""
import os, sys
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HOLD = 10

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS d10_best_pct NUMERIC")
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
    cols = {r[0] for r in cur.fetchall()}
    sym = "symbol_final" if "symbol_final" in cols else "nse_symbol"
    open_col = next((c for c in ("listing_open", "listing_open_price") if c in cols), None)

    cur.execute(f"""SELECT UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$','')),
                           c.company_name, c.listing_date,
                           {f'c.{open_col}' if open_col else 'NULL'}
                    FROM ipo_consolidated c
                    WHERE c.listing_date IS NOT NULL AND c.listing_date < CURRENT_DATE
                      AND c.{sym} IS NOT NULL""")
    ipos = cur.fetchall()
    cur.execute(f"""SELECT UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$','')), p.date, p.open, p.close
                    FROM ipo_consolidated c JOIN price_candles p
                      ON UPPER(p.symbol)=UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$',''))
                     AND p.date>=c.listing_date AND p.date<=c.listing_date+30
                    WHERE c.listing_date IS NOT NULL ORDER BY 1, p.date""")
    cnd = {}
    for s, d, o, cl in cur.fetchall():
        cnd.setdefault(s, []).append((o, cl))

    upd = skip = 0
    for s, name, ldate, lopen in ipos:
        cs = cnd.get(s) or []
        if not cs:
            skip += 1; continue
        entry = float(lopen) if lopen else float(cs[0][0] or 0)
        closes = [float(c) for _, c in cs[:HOLD] if c]
        if entry <= 0 or len(closes) < 3:
            skip += 1; continue
        d10 = round((max(closes) - entry) / entry * 100, 2)
        cur.execute("""UPDATE ipo_intelligence SET d10_best_pct = %s
                       WHERE UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)) = %s""", (d10, s))
        if cur.rowcount == 0 and name:
            cur.execute("UPDATE ipo_intelligence SET d10_best_pct = %s WHERE company_name = %s",
                        (d10, name))
        upd += cur.rowcount
    conn.commit(); conn.close()
    print(f"d10_best_pct: {upd} rows written, {skip} skipped (no/thin candles). "
          f"Wins if > 0; the audit tab and BRLM 10s columns light up on next consolidated rebuild.")

if __name__ == "__main__":
    main()
