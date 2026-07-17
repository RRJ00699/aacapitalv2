#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lineage_registry.py — PILLAR 2: declare Source -> Parser -> DB for every
tracked field, and compute freshness. Run after schema_sync in the pipeline.
The LINEAGE dict is the single source of truth for data provenance; extend it
when a new field is added (same discipline as schema_sync for columns).
"""
import os, psycopg2

# (table, column, source, parser_script, freshness_sla_hours)
LINEAGE = [
    ("ipo_consolidated", "ipo_open_date",  "nse-api",       "fetch_nse_ipos.py",        24),
    ("ipo_consolidated", "ipo_close_date", "nse-api",       "fetch_nse_ipos.py",        24),
    ("ipo_consolidated", "listing_date",   "nse-api",       "fetch_nse_ipos.py",        24),
    ("ipo_intelligence", "ipo_score",      "derived",       "ipo_score.py",             24),
    ("ipo_intelligence", "score_band",     "derived",       "ipo_score.py",             24),
    ("ipo_intelligence", "score_expected_win", "backtest",  "ipo_score.py",             None),
    ("ipo_intelligence", "peer_median_pe", "ipomatrix",     "ipomatrix_ingest.py",      168),
    ("ipo_intelligence", "eps_post",       "derived",       "backfill_eps_post.py",     168),
    ("ipo_verdicts",     "verdict",        "derived",       "compute_verdicts.py",      24),
    ("ipo_rhp_intel",    "verdict",        "sonnet-rhp",    "rhp_sonnet.py",            None),
    ("ipo_research_notes","full_json",     "haiku-sbi",     "sbi_haiku_extract.py",     None),
    ("ipo_preopen_book", "discovery_price","nse-preopen",   "nse_preopen_capture.py",   None),
    ("ipo_tick_feed",    "ltp",           "kite",          "kite_ticker_ipo.py",       1),
    ("ipo_gmp",          "gmp",           "investorgain",  "scrape_investorgain_gmp.py",24),
]

# domain -> (table, timestamp_column) for freshness snapshots
FRESHNESS = [
    ("ipo_dates",    "ipo_consolidated", None),          # no ts col: use row count only
    ("verdicts",     "ipo_verdicts",     None),
    ("ticks",        "ipo_tick_feed",    "recorded_at"),
    ("preopen",      "ipo_preopen_book", None),
]

def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); conn.autocommit = True
    cur = conn.cursor()
    for t, c, src, parser, sla in LINEAGE:
        cur.execute("""INSERT INTO data_lineage
            (table_name, column_name, source, parser, freshness_sla_hours, last_verified)
            VALUES (%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (table_name, column_name) DO UPDATE SET
              source=EXCLUDED.source, parser=EXCLUDED.parser,
              freshness_sla_hours=EXCLUDED.freshness_sla_hours, last_verified=NOW()""",
            (t, c, src, parser, sla))
    # freshness snapshot
    for domain, table, tscol in FRESHNESS:
        try:
            if tscol:
                cur.execute(f"SELECT max({tscol}), count(*) FROM {table}")
            else:
                cur.execute(f"SELECT NULL::timestamptz, count(*) FROM {table}")
            last, cnt = cur.fetchone()
            cur.execute("""INSERT INTO data_freshness (domain, last_write, row_count, updated_at)
                VALUES (%s,%s,%s,NOW()) ON CONFLICT (domain) DO UPDATE SET
                  last_write=EXCLUDED.last_write, row_count=EXCLUDED.row_count, updated_at=NOW()""",
                (domain, last, cnt))
        except Exception as e:
            print(f"  freshness {domain}: {str(e)[:60]}")
    print(f"lineage: {len(LINEAGE)} fields declared · {len(FRESHNESS)} freshness domains snapshotted")
    conn.close()

if __name__ == "__main__":
    main()
