#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_eps_post.py — fill eps_post where our sources allow (Build plan #6).

Rakesh's spec (2026-07-16, Screener dropped): when EPS is unavailable from a
source, use the standard formula WITH A CAUTION MARK:
    EPS = (Net Income − Preferred Dividends) / Weighted Avg Shares Outstanding
Sources of truth, in trust order:
  1. eps_post already present            -> leave untouched (fill-empty rule)
  2. IPOMatrix implied                   -> issue_price / ipo_pe  (their own P/E,
     so price/PE is their EPS by identity)          eps_source='ipomatrix_pe'
  3. Standard formula from fundamentals  -> pat_cr / (market_cap / issue_price)
     (shares = mcap/price; preferred dividends not tracked -> assumed 0 and
     SAID SO in the source tag)                      eps_source='derived_std*'
Never overwrites a non-null eps_post. Writes eps_source beside every fill so
the CAUTION mark survives to the UI (fair_note already stars derived EPS).

Run:  python _scripts/backfill_eps_post.py            # preview
      python _scripts/backfill_eps_post.py --apply
"""
import argparse, os, sys
import psycopg2

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); conn.autocommit = False
    cur = conn.cursor()

    cur.execute("""ALTER TABLE ipo_intelligence
                   ADD COLUMN IF NOT EXISTS eps_source TEXT""")

    # candidates: eps_post missing, and at least one source computable
    cur.execute("""
        SELECT id, company_name, issue_price, ipo_pe, pat_cr, market_cap
        FROM ipo_intelligence
        WHERE eps_post IS NULL
          AND issue_price IS NOT NULL AND issue_price > 0
          AND ( (ipo_pe IS NOT NULL AND ipo_pe > 0)
             OR (pat_cr IS NOT NULL AND pat_cr > 0
                 AND market_cap IS NOT NULL AND market_cap > 0) )
        ORDER BY id""")
    rows = cur.fetchall()
    print(f"candidates: {len(rows)} | mode = {'APPLY' if a.apply else 'PREVIEW'}")

    n_pe = n_std = 0
    for pid, name, price, pe, pat, mcap in rows:
        price, pe = float(price), float(pe or 0)
        pat, mcap = float(pat or 0), float(mcap or 0)
        if pe > 0:
            eps, src = price / pe, "ipomatrix_pe"
            n_pe += 1
        else:
            # standard: NI / shares; shares = mcap/price; pref div assumed 0
            eps, src = pat * price / mcap, "derived_std*"
            n_std += 1
        if eps <= 0 or eps > price:      # sanity: EPS above price = garbage input
            continue
        if a.apply:
            cur.execute("""UPDATE ipo_intelligence
                           SET eps_post = %s, eps_source = %s WHERE id = %s""",
                        (round(eps, 2), src, pid))
        if n_pe + n_std <= 12:
            print(f"  {pid:>5} {name[:34]:<34} eps={eps:.2f}  [{src}]")

    if a.apply:
        conn.commit(); print(f"COMMITTED: {n_pe} via ipomatrix_pe, {n_std} via derived_std*")
    else:
        conn.rollback(); print(f"preview: {n_pe} would fill via ipomatrix_pe, {n_std} via derived_std* — rerun with --apply")
    cur.execute("SELECT COUNT(*) FROM ipo_intelligence WHERE eps_post IS NOT NULL")
    print("eps_post coverage now:", cur.fetchone()[0])
    conn.close()

if __name__ == "__main__":
    main()
