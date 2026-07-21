#!/usr/bin/env python3
"""consolidate_master.py — THE golden-table job (owner architecture 2026-07-22).

ipo_master (VIEW) is the ONE object every screen and backtest reads:
ipo_consolidated (rebuilt each run) LEFT JOIN ipo_golden (durable — this
table survives rebuilds; see test_no_columns_on_rebuilt_tables for the
incident that mandates it). This job fills ipo_golden, fill-empty-only
(COALESCE — a confirmed value is never overwritten), strong keys only:

  1. scalars from ipo_intelligence (IPOMatrix-fed primary source)
  2. research copies: latest RHP Sonnet full_json + SBI Haiku full_json
     from ipo_research_notes -> rhp_sonnet_json / sbi_haiku_json
  3. street article (real rows only) -> street_headline/publisher/url
  4. CANDLES: price_candles listing..lock-in window -> candles_json
     (ordered daily OHLCV array — backtests read the golden table only)

Automated: runs in the lean pipeline every cycle and as admin job
'consolidate'. PC-runnable for the owner's local backfill:
  python _scripts\\consolidate_master.py --apply     (DATABASE_URL = Neon)
Default is a dry-run report. NSE fallback fills land here as their scrapers
arrive (docs/DETAILS_AND_REVIEW.md precedence: IPOMatrix -> NSE -> Chittorgarh).
"""
import argparse
import os
import sys

# column type map for the text->typed cast in the fill query
COLTYPE = {
    "isin": "text", "lot_size": "int", "face_value": "numeric",
    "allotment_date": "date", "anchor_amount_cr": "numeric",
    "anchor_lock30_date": "date", "anchor_lock90_date": "date",
    "sub_day1_x": "numeric", "sub_day2_x": "numeric", "sub_day3_x": "numeric",
    "total_applications": "bigint", "promoter_pre_pct": "numeric",
    "promoter_post_pct": "numeric", "mcap_cr": "numeric", "ronw": "numeric",
    "price_to_book": "numeric", "final_retail": "numeric", "debt_equity": "numeric",
}

# scalar fills: golden column -> intelligence expression (fill-empty-only)
SCALARS = {
    "isin": "i.isin",
    "lot_size": "i.lot_size",
    "face_value": "i.face_value",
    "allotment_date": "i.allotment_date",
    "anchor_amount_cr": "i.anchor_amount_cr",
    "anchor_lock30_date": "i.anchor_lock30_date",
    "anchor_lock90_date": "i.anchor_lock90_date",
    "sub_day1_x": "i.sub_day1_x",
    "sub_day2_x": "i.sub_day2_x",
    "sub_day3_x": "i.sub_day3_x",
    "total_applications": "i.total_applications",
    "promoter_pre_pct": "i.promoter_pre_pct",
    "promoter_post_pct": "i.promoter_post_pct",
    "mcap_cr": "i.mcap_cr",
    "ronw": "i.ronw",
    "price_to_book": "i.price_to_book",
}

STRONG = "UPPER(COALESCE(NULLIF(btrim(c.symbol_final),''), NULLIF(btrim(c.nse_symbol),''), btrim(c.symbol)))"
NORM = "regexp_replace(lower({}),'(ltd|limited|and|&)|[^a-z0-9]','','g')"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not db:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(db, connect_timeout=25)
    conn.autocommit = False
    cur = conn.cursor()

    # seed golden rows for every consolidated company (idempotent)
    cur.execute("""INSERT INTO ipo_golden (company_key, company_name, nse_symbol)
        SELECT DISTINCT regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g'),
               c.company_name,
               COALESCE(NULLIF(btrim(c.symbol_final),''), NULLIF(btrim(c.nse_symbol),''), btrim(c.symbol))
        FROM ipo_consolidated c WHERE c.company_name IS NOT NULL
        ON CONFLICT (company_key) DO NOTHING""")
    seeded = cur.rowcount

    # only columns BOTH tables actually have (information_schema — never assume)
    cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                   WHERE table_name IN ('ipo_golden','ipo_intelligence')""")
    have = {(t, c) for t, c in cur.fetchall()}
    filled = {}

    # 1) scalars, fill-empty-only, strong-name join (intelligence keys on name)
    for col, expr in SCALARS.items():
        src = expr.split(".")[1]
        if ("ipo_golden", col) not in have or ("ipo_intelligence", src) not in have:
            filled[col] = "skip (column absent)"
            continue
        q = f"""UPDATE ipo_golden g SET {col} = COALESCE(g.{col}, sub.v::{cast})
                FROM (SELECT {NORM.format('i.company_name')} AS k, MAX({expr}::text) AS v
                      FROM ipo_intelligence i WHERE {expr} IS NOT NULL GROUP BY 1) sub
                WHERE g.{col} IS NULL AND sub.v IS NOT NULL AND g.company_key = sub.k"""
        # cast back from the MAX(text) funnel to the column's own type
        q = q.replace("{cast}", COLTYPE.get(col, "text"))
        cur.execute(q)
        filled[col] = cur.rowcount

    # 2) research JSON copies (latest per company, source-tagged rows)
    for col, source in (("rhp_sonnet_json", "RHP_SONNET"), ("sbi_haiku_json", "SBI")):
        cur.execute(f"""UPDATE ipo_golden g SET {col} = sub.fj
            FROM (SELECT DISTINCT ON ({NORM.format('n.company')}) {NORM.format('n.company')} AS k, n.full_json AS fj
                  FROM ipo_research_notes n
                  WHERE n.source = %s AND n.full_json IS NOT NULL
                  ORDER BY {NORM.format('n.company')}, n.stored_at DESC NULLS LAST) sub
            WHERE g.{col} IS NULL AND g.company_key = sub.k""", (source,))
        filled[col] = cur.rowcount

    # 3) street article (sanity-guarded rows only; manual wins upstream)
    cur.execute(f"""UPDATE ipo_golden g
        SET street_headline = sub.h, street_publisher = sub.p, street_url = sub.u
        FROM (SELECT DISTINCT ON (n.company_name) n.company_name AS k, n.headline h, n.publisher p, n.url u
              FROM ipo_news n
              WHERE n.is_current AND n.fetch_status = 'ok' AND n.url ~* '^https?://'
                AND n.headline NOT LIKE '<%%'
              ORDER BY n.company_name, (n.source = 'manual') DESC, n.created_at DESC) sub
        WHERE g.street_url IS DISTINCT FROM sub.u
          AND g.company_key = regexp_replace(lower(sub.k),'(ltd|limited|and|&)|[^a-z0-9]','','g')""")
    filled["street_*"] = cur.rowcount

    # 4) CANDLES -> candles_json: listing .. lock-in (45d clamp), ordered OHLCV.
    #    Refreshes whenever the window gains rows (candle count differs) so the
    #    listing week auto-materialises day by day; never shrinks a series.
    cur.execute(f"""UPDATE ipo_golden g
        SET candles_json = sub.cj, golden_filled_at = NOW()
        FROM (
          SELECT {STRONG} AS k,
                 json_agg(json_build_object('d', p.date, 'o', p.open, 'h', p.high,
                                            'l', p.low, 'c', p.close, 'v', p.volume)
                          ORDER BY p.date) AS cj,
                 COUNT(*) AS n
          FROM ipo_consolidated c
          JOIN price_candles p
            ON UPPER(p.symbol) = {STRONG}
           AND p.date >= c.listing_date
           AND p.date <= LEAST(COALESCE(c.anchor_lock30_date, (c.listing_date + INTERVAL '30 days')::date),
                               (c.listing_date + INTERVAL '45 days')::date)
          WHERE c.listing_date IS NOT NULL
          GROUP BY 1
        ) sub
        WHERE UPPER(COALESCE(g.nse_symbol, '')) = sub.k
          AND COALESCE(json_array_length(g.candles_json), 0) < sub.n""")
    filled["candles_json"] = cur.rowcount

    filled["golden rows seeded"] = seeded
    width = max(len(k) for k in filled)
    print(f"GOLDEN TABLE CONSOLIDATION ({'APPLY' if a.apply else 'DRY-RUN'})")
    for k, v in filled.items():
        print(f"  {k:{width}}  {v}")
    if a.apply:
        conn.commit()
        print("COMMITTED")
    else:
        conn.rollback()
        print("rolled back — rerun with --apply")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
