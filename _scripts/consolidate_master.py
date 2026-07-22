#!/usr/bin/env python3
"""consolidate_master.py — THE golden-table job (owner architecture 2026-07-22).

ipo_gold (VIEW) is the ONE object every screen and backtest reads:
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
    "price_to_book": "numeric", "registrar_name": "text", "ebitda_margin": "numeric",
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
    # names below are the REAL ipo_intelligence columns (owner --raw evidence
    # 2026-07-23: mapped-field list) — not the golden names.
    "promoter_post_pct": "i.promoter_holding_post",
    "mcap_cr": "i.mcap_offer",
    "ronw": "i.ronw",
    "price_to_book": "i.ipo_pb",
    "registrar_name": "i.registrar",
    "ebitda_margin": "i.ebitda_margin",
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
    # bounded worst-case: no statement may hold Neon compute > 3 minutes;
    # a timeout fails the step loudly and the next run resumes (fill-empty).
    cur.execute("SET statement_timeout = '180s'")

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
        cast = COLTYPE.get(col, "text")  # text->typed from the MAX(text) funnel
        q = f"""UPDATE ipo_golden g SET {col} = COALESCE(g.{col}, sub.v::{cast})
                FROM (SELECT {NORM.format('i.company_name')} AS k, MAX({expr}::text) AS v
                      FROM ipo_intelligence i WHERE {expr} IS NOT NULL GROUP BY 1) sub
                WHERE g.{col} IS NULL AND sub.v IS NOT NULL AND g.company_key = sub.k"""
        cur.execute(q)
        filled[col] = cur.rowcount

    # 2) research JSON copies (latest per company, source-tagged rows).
    #    Recency column INTROSPECTED — prod's ipo_research_notes predates the
    #    stored_at column some writers use (never assume; UndefinedColumn
    #    incident 2026-07-22).
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'ipo_research_notes'""")
    note_cols = {r[0] for r in cur.fetchall()}
    recency = next((c for c in ("stored_at", "created_at", "updated_at", "id") if c in note_cols), None)
    order_tail = f", n.{recency} DESC NULLS LAST" if recency else ""
    # SBI Haiku lives in ipo_research_notes (source='SBI'); RHP Sonnet lives in
    # its OWN table ipo_rhp_intel (rhp_sonnet_store.py) — owner evidence
    # 2026-07-22: research_notes contains only SBI/Hem, zero RHP_SONNET rows.
    cur.execute(f"""UPDATE ipo_golden g SET sbi_haiku_json = sub.fj
        FROM (SELECT DISTINCT ON ({NORM.format('n.company')}) {NORM.format('n.company')} AS k, n.full_json AS fj
              FROM ipo_research_notes n
              WHERE n.source = 'SBI' AND n.full_json IS NOT NULL
              ORDER BY {NORM.format('n.company')}{order_tail}) sub
        WHERE g.sbi_haiku_json IS NULL AND g.company_key = sub.k""")
    filled["sbi_haiku_json"] = cur.rowcount
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'ipo_rhp_intel'""")
    rhp_cols = {r[0] for r in cur.fetchall()}
    if "full_json" in rhp_cols:
        name_col = next((c for c in ("company_name", "company", "name") if c in rhp_cols), None)
        rec2 = next((c for c in ("stored_at", "created_at", "updated_at", "id") if c in rhp_cols), None)
        tail2 = f", r.{rec2} DESC NULLS LAST" if rec2 else ""
        if name_col:
            cur.execute(f"""UPDATE ipo_golden g SET rhp_sonnet_json = sub.fj
                FROM (SELECT DISTINCT ON ({NORM.format('r.'+name_col)}) {NORM.format('r.'+name_col)} AS k, r.full_json AS fj
                      FROM ipo_rhp_intel r WHERE r.full_json IS NOT NULL
                      ORDER BY {NORM.format('r.'+name_col)}{tail2}) sub
                WHERE g.rhp_sonnet_json IS NULL AND g.company_key = sub.k""")
            filled["rhp_sonnet_json"] = cur.rowcount
        else:
            filled["rhp_sonnet_json"] = "skip (no name column in ipo_rhp_intel)"
    else:
        filled["rhp_sonnet_json"] = "skip (ipo_rhp_intel absent/legacy shape)"

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

    # 3b) DERIVED lock dates (audit 2026-07-23: 44.2% coverage was the worst
    #     row). SEBI anchor lock-in = 30/90 days; where the vendor never
    #     supplied a date, derive from listing_date. Fill-empty only, and the
    #     45d candle clamp already bounds any approximation error.
    cur.execute("""UPDATE ipo_golden g SET anchor_lock30_date = (c.listing_date + INTERVAL '30 days')::date
        FROM ipo_consolidated c
        WHERE g.anchor_lock30_date IS NULL AND c.listing_date IS NOT NULL
          AND g.company_key = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')""")
    filled["anchor_lock30_date (derived)"] = cur.rowcount
    cur.execute("""UPDATE ipo_golden g SET anchor_lock90_date = (c.listing_date + INTERVAL '90 days')::date
        FROM ipo_consolidated c
        WHERE g.anchor_lock90_date IS NULL AND c.listing_date IS NOT NULL
          AND g.company_key = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')""")
    filled["anchor_lock90_date (derived)"] = cur.rowcount

    # 4) CANDLES -> candles_json: listing .. lock-in (45d clamp), ordered OHLCV.
    #    Refreshes whenever the window gains rows (candle count differs) so the
    #    listing week auto-materialises day by day; never shrinks a series.
    cur.execute(f"""UPDATE ipo_golden g
        SET candles_json = sub.cj, golden_filled_at = NOW()
        FROM (
          SELECT {STRONG} AS k,
                 jsonb_agg(jsonb_build_object('d', p.date, 'o', p.open, 'h', p.high,
                                            'l', p.low, 'c', p.close, 'v', p.volume)
                          ORDER BY p.date) AS cj,
                 COUNT(*) AS n
          FROM ipo_consolidated c
          JOIN price_candles p
            ON UPPER(p.symbol) = {STRONG}
           AND p.date >= c.listing_date
           AND p.date <= LEAST(COALESCE(c.anchor_lock30_date, (c.listing_date + INTERVAL '30 days')::date),
                               (c.listing_date + INTERVAL '45 days')::date)
           -- audit anomaly class: impossible OHLC (8 rows) never enters golden
           AND p.high >= p.low AND p.open BETWEEN p.low AND p.high
           AND p.close BETWEEN p.low AND p.high AND p.low > 0
          WHERE c.listing_date IS NOT NULL
          GROUP BY 1
        ) sub
        WHERE UPPER(COALESCE(g.nse_symbol, '')) = sub.k
          AND COALESCE(jsonb_array_length(g.candles_json), 0) < sub.n""")
    filled["candles_json"] = cur.rowcount

    # 5) NSE MINING (source doctrine 2026-07-23: NSE = every IPO detail;
    #    DECADE LOCK: 2016+). Parses banked nse_issue_info payloads:
    #    metaInfo (isin/listingDate/industry) + activeCat category table
    #    (QIB '1', NII '2', bNII '2.1', sNII '2.2', Retail '3', Total) +
    #    broadened anchor extraction. Fill-empty; anchor_amount_cr derived
    #    from shares * issue_price.
    import json as _json
    import re as _re
    RX2 = _re.compile(r"Anchor[^\d]{0,60}?([\d,]{6,})\s+Equity", _re.I)
    cur.execute("""SELECT n.symbol, n.raw_json, n.anchor_portion_shares
                   FROM nse_issue_info n JOIN ipo_golden g ON g.nse_symbol = n.symbol
                   WHERE n.raw_json IS NOT NULL""")
    mined = {"nse_meta": 0, "nse_finals": 0, "nse_anchor_amount": 0}
    for sym, raw, shares in cur.fetchall():
        try:
            d = raw if isinstance(raw, dict) else _json.loads(raw)
        except Exception:
            continue
        meta = d.get("metaInfo") or {}
        upd, args = [], []
        for col, val in (("isin", meta.get("isin")), ("industry", meta.get("industry")),
                         ("nse_listing_date", meta.get("listingDate"))):
            if val:
                upd.append(f"{col} = COALESCE(g.{col}, %s)"); args.append(val)
        cats = {str(r.get("srNo", "")).strip(): r
                for r in ((d.get("activeCat") or {}).get("dataList") or []) if isinstance(r, dict)}
        def x(key):
            v = (cats.get(key) or {}).get("noOfTotalMeant") or ""
            try:
                return round(float(v), 4)
            except Exception:
                return None
        for col, key in (("final_qib", "1"), ("final_nii", "2"), ("bnii_x", "2.1"),
                         ("snii_x", "2.2"), ("final_retail", "3")):
            v = x(key)
            if v is not None:
                upd.append(f"{col} = COALESCE(g.{col}, %s)"); args.append(v)
        tot = x("Total") or x("total")
        if tot is not None:
            upd.append("final_total = COALESCE(g.final_total, %s)"); args.append(tot)
        if not shares:
            m = RX2.search(_json.dumps(d))
            if m:
                shares = int(m.group(1).replace(",", ""))
        if shares:
            upd.append("""anchor_amount_cr = COALESCE(g.anchor_amount_cr,
                (SELECT ROUND(%s * c.issue_price / 1e7, 2) FROM ipo_consolidated c
                 WHERE UPPER(COALESCE(NULLIF(btrim(c.symbol_final),''), NULLIF(btrim(c.nse_symbol),''), btrim(c.symbol))) = g.nse_symbol
                   AND c.issue_price > 0 LIMIT 1))""")
            args.append(shares)
        if upd:
            cur.execute(f"UPDATE ipo_golden g SET {', '.join(upd)} WHERE g.nse_symbol = %s", (*args, sym))
            mined["nse_meta"] += 1
            if any("final_" in u or "nii_x" in u for u in upd):
                mined["nse_finals"] += 1
            if any("anchor_amount" in u for u in upd):
                mined["nse_anchor_amount"] += 1
    filled.update(mined)

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
