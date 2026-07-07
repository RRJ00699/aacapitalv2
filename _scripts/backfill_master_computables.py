#!/usr/bin/env python3
"""
backfill_master_computables.py — fills every ipo_intelligence column that is
DERIVABLE from tables we already own. Fill-empty only (Rule 1). Dry-run default.

From price_candles (per IPO, from listing_date):
  listing_high, listing_low, listing_close_price, listing_volume_val
  days_to_break_issue  (first session close < issue_price, within 90 sessions)
  days_to_new_high     (first session close > listing-day high, within 90)
From delivery_data:
  listing_delivery_pct (listing-day delivery %)
From ipo_gmp (company,date,gmp — matched by name):
  gmp_pct_t1/t3/t5/t7  (GMP as % of issue price, N days before listing, nearest +/-1d)

  python _scripts/backfill_master_computables.py [--apply]
"""
import os, re, sys, argparse

def norm(name):
    s = (name or "").lower()
    s = re.sub(r"\b(ltd|limited|pvt|private)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    cols = {r[0] for r in cur.fetchall()}
    TARGETS = ["listing_high","listing_low","listing_close_price","listing_volume_val",
               "days_to_break_issue","days_to_new_high","listing_delivery_pct",
               "gmp_pct_t1","gmp_pct_t3","gmp_pct_t5","gmp_pct_t7"]
    targets = [t for t in TARGETS if t in cols]

    def cov():
        q = ", ".join(f"COUNT({c})" for c in targets)
        cur.execute(f"SELECT {q} FROM ipo_intelligence WHERE listing_date IS NOT NULL")
        return dict(zip(targets, cur.fetchone()))
    before = cov()

    # --- candles-derived ---
    cur.execute("""SELECT i.id, i.issue_price,
                          ARRAY_AGG(p.date ORDER BY p.date), ARRAY_AGG(p.high ORDER BY p.date),
                          ARRAY_AGG(p.low ORDER BY p.date),  ARRAY_AGG(p.close ORDER BY p.date),
                          ARRAY_AGG(p.volume ORDER BY p.date)
                   FROM ipo_intelligence i JOIN price_candles p
                     ON UPPER(p.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
                    AND p.date >= i.listing_date AND p.date <= i.listing_date + 130
                   WHERE i.listing_date IS NOT NULL GROUP BY 1,2""")
    n_c = 0
    for pid, ip, dts, hi, lo, cl, vol in cur.fetchall():
        hi=[float(x) for x in hi]; lo=[float(x) for x in lo]; cl=[float(x) for x in cl]
        d1h, d1l, d1c = hi[0], lo[0], cl[0]
        d1v = int(vol[0]) if vol and vol[0] is not None else None
        dtb = dtnh = None
        try: ipf = float(ip) if ip else None
        except (TypeError, ValueError): ipf = None
        for i2 in range(1, min(len(cl), 90)):
            if dtb is None and ipf and cl[i2] < ipf: dtb = i2
            if dtnh is None and cl[i2] > d1h: dtnh = i2
            if dtb is not None and dtnh is not None: break
        if a.apply:
            cur.execute("""UPDATE ipo_intelligence SET
                listing_high=COALESCE(listing_high,%s), listing_low=COALESCE(listing_low,%s),
                listing_close_price=COALESCE(listing_close_price,%s),
                listing_volume_val=COALESCE(listing_volume_val,%s),
                days_to_break_issue=COALESCE(days_to_break_issue,%s),
                days_to_new_high=COALESCE(days_to_new_high,%s)
                WHERE id=%s""", (d1h, d1l, d1c, d1v, dtb, dtnh, pid))
        n_c += 1
    print(f"candles-derived rows processed: {n_c}")

    # --- delivery ---
    if "listing_delivery_pct" in targets:
        act = ("UPDATE ipo_intelligence i SET listing_delivery_pct = dd.delivery_percentage "
               "FROM delivery_data dd "
               "WHERE i.listing_delivery_pct IS NULL AND i.listing_date IS NOT NULL "
               "AND UPPER(dd.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol)) "
               "AND dd.date = i.listing_date")
        if a.apply:
            cur.execute(act); print(f"listing_delivery_pct filled: {cur.rowcount}")
        else:
            cur.execute("SELECT COUNT(*) FROM ipo_intelligence i JOIN delivery_data dd ON "
                        "UPPER(dd.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol)) "
                        "AND dd.date=i.listing_date WHERE i.listing_delivery_pct IS NULL")
            print(f"listing_delivery_pct fillable: {cur.fetchone()[0]}")

    # --- GMP T-minus snapshots (name-matched) ---
    gmps = {}
    cur.execute("SELECT company, date, gmp FROM ipo_gmp WHERE gmp IS NOT NULL")
    for co, dt, g in cur.fetchall():
        gmps.setdefault(norm(co), {})[dt] = float(g)
    cur.execute("""SELECT id, company_name, listing_date, issue_price FROM ipo_intelligence
                   WHERE listing_date IS NOT NULL AND issue_price > 0""")
    import datetime as dtmod
    n_g = 0
    for pid, nm, ld, ip in cur.fetchall():
        hist = gmps.get(norm(nm))
        if not hist: continue
        vals = {}
        for lbl, nd in (("gmp_pct_t1",1),("gmp_pct_t3",3),("gmp_pct_t5",5),("gmp_pct_t7",7)):
            if lbl not in targets: continue
            for off in (0, 1, -1):
                d0 = ld - dtmod.timedelta(days=nd) + dtmod.timedelta(days=off)
                if d0 in hist:
                    vals[lbl] = round(hist[d0] / float(ip) * 100, 2); break
        if vals and a.apply:
            sets = ", ".join(f"{k}=COALESCE({k},%s)" for k in vals)
            cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id=%s",
                        (*vals.values(), pid))
        if vals: n_g += 1
    print(f"GMP T-minus rows with any match: {n_g}")

    if a.apply:
        conn.commit()
        after = cov()
        print("\ncoverage (listed IPOs):")
        for t in targets:
            print(f"  {t:22} {before[t]:>4} -> {after[t]:>4}  (+{after[t]-before[t]})")
    else:
        print("\ncurrent coverage:", {t: before[t] for t in targets})
        print("DRY RUN — --apply to write (fill-empty only).")
    conn.close()

if __name__ == "__main__":
    main()
