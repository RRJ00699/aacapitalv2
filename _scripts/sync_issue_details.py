#!/usr/bin/env python3
"""
sync_issue_details.py — fill ipo_intelligence identity/financial fields from
ipo_issue_details (the Chittorgarh scrape target) via STRONG KEY (isin).

Why: ipo_issue_details has clean nse_symbol / industry / eps_post, but those were
never propagated into ipo_intelligence — so peer P/E + fair value silently failed
for IPOs with a NULL sector/symbol (root cause found 2026-07-15).

Rules honored:
  - STRONG KEY only: join on isin (exact). Never fuzzy name matching.
  - FILL-EMPTY-ONLY: COALESCE — never overwrites an existing good value.
  - Fixes the SOURCE (ipo_intelligence); build_ipo_consolidated_v2 then carries
    it into ipo_consolidated (what the app reads).
  - Runs nightly BEFORE build_ipo_consolidated_v2, so new IPOs self-heal and any
    backlog is mopped up automatically.

  venv/bin/python _scripts/sync_issue_details.py            # DRY RUN (counts only)
  venv/bin/python _scripts/sync_issue_details.py --apply    # write
"""
import os, sys, argparse
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (else dry run)")
    a = ap.parse_args()
    if not DB:
        sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=20)
    cur = conn.cursor()

    # guard: both tables must exist (per SCHEMA rules — verify, don't assume)
    cur.execute("""SELECT COUNT(*) FROM information_schema.tables
                   WHERE table_schema='public'
                     AND table_name IN ('ipo_intelligence','ipo_issue_details')""")
    if cur.fetchone()[0] < 2:
        sys.exit("ipo_intelligence or ipo_issue_details missing — nothing to sync")

    # DRY-RUN counts: how many rows each field would fill (strong-key isin join)
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE ii.nse_symbol IS NULL AND d.nse_symbol IS NOT NULL) AS fill_symbol,
          COUNT(*) FILTER (WHERE (ii.sector IS NULL OR ii.sector = 'Unknown')
                                  AND d.industry IS NOT NULL)                          AS fill_sector,
          COUNT(*) FILTER (WHERE ii.eps_post IS NULL AND d.eps_post IS NOT NULL)       AS fill_eps
        FROM ipo_intelligence ii
        JOIN ipo_issue_details d ON d.isin = ii.isin AND ii.isin IS NOT NULL
    """)
    fs, fsec, fe = cur.fetchone()
    print(f"sync_issue_details (isin strong-key, fill-empty-only):")
    print(f"  would fill  nse_symbol={fs}  sector={fsec}  eps_post={fe}")

    if not a.apply:
        print("DRY RUN — pass --apply to write.")
        conn.close()
        return

    # WRITE — fill-empty-only via COALESCE; only rows where something is missing.
    cur.execute("""
        UPDATE ipo_intelligence ii SET
          nse_symbol = COALESCE(ii.nse_symbol, d.nse_symbol),
          sector     = COALESCE(NULLIF(ii.sector, 'Unknown'), d.industry),
          eps_post   = COALESCE(ii.eps_post, d.eps_post)
        FROM ipo_issue_details d
        WHERE d.isin = ii.isin AND ii.isin IS NOT NULL
          AND ( ii.nse_symbol IS NULL
             OR ii.sector IS NULL OR ii.sector = 'Unknown'
             OR ii.eps_post IS NULL )
    """)
    n = cur.rowcount
    conn.commit()
    print(f"applied — {n} ipo_intelligence row(s) updated.")
    conn.close()

if __name__ == "__main__":
    main()
