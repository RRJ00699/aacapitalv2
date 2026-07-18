#!/usr/bin/env python3
"""
reconcile_mf_disclosures.py — keep the holdings time-series to REAL changes only.

Funds publish MONTHLY (authoritative, month-end) and optionally FORTNIGHTLY (interim, ~15th)
disclosures. Rule: a fortnight snapshot is kept only if it CHANGES the holdings vs the prior
snapshot. If a fortnight shows no change, the monthly (authoritative) overrides it and the
redundant fortnight is pruned — so initiation detection sees genuine moves, not cadence noise.

"No change" = the SET of ISINs held by that fund is identical to the immediately-prior
snapshot (membership is what the NEW-conviction signal keys on). Same-date monthly+fortnight
never both exist (they collide on the unique key — monthly, loaded last, wins automatically).

This handles the DIFFERENT-date case: a mid-month fortnight identical to the prior month-end.

Run AFTER load + canonicalize, BEFORE compute_mf_conviction_flags:
  python _scripts/mf/reconcile_mf_disclosures.py            # apply
  python _scripts/mf/reconcile_mf_disclosures.py --dry-run  # preview prunes only
Env:  DATABASE_URL
"""
import os, sys, argparse
import psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(URL); conn.autocommit = False
    cur = conn.cursor()

    # ensure disclosure_type exists (default MONTHLY for anything already loaded)
    cur.execute("""
        ALTER TABLE mf_scheme_holdings
        ADD COLUMN IF NOT EXISTS disclosure_type TEXT DEFAULT 'MONTHLY'
    """)
    conn.commit()

    # holdings SET per (scheme, date), plus the type of that snapshot
    cur.execute("""
        SELECT scheme_name, month, MAX(disclosure_type) AS dtype,
               ARRAY_AGG(DISTINCT nse_symbol ORDER BY nse_symbol) AS syms
        FROM mf_scheme_holdings
        WHERE nse_symbol IS NOT NULL AND nse_symbol <> ''
        GROUP BY scheme_name, month
        ORDER BY scheme_name, month
    """)
    rows = cur.fetchall()

    # walk each fund's snapshots; flag FORTNIGHT dates identical to the prior snapshot's set
    from collections import defaultdict
    by_fund = defaultdict(list)
    for scheme, month, dtype, syms in rows:
        by_fund[scheme].append((month, dtype, frozenset(syms or [])))

    prune = []   # (scheme, month) to drop
    for scheme, snaps in by_fund.items():
        snaps.sort(key=lambda x: x[0])
        for i in range(1, len(snaps)):
            month, dtype, syms = snaps[i]
            prev_syms = snaps[i - 1][2]
            if dtype == "FORTNIGHT" and syms == prev_syms:
                prune.append((scheme, month))

    print("RECONCILE — no-change FORTNIGHT snapshots (monthly overrides)")
    print("-" * 66)
    if not prune:
        print("  nothing to prune — every fortnight snapshot shows a real change.")
    for scheme, month in prune:
        print(f"  prune  {scheme:40s} {month}  (identical to prior)")

    if args.dry_run:
        print("\n[dry-run] no rows deleted."); conn.close(); return

    deleted = 0
    for scheme, month in prune:
        cur.execute("""
            DELETE FROM mf_scheme_holdings
            WHERE scheme_name = %s AND month = %s AND disclosure_type = 'FORTNIGHT'
        """, (scheme, month))
        deleted += cur.rowcount
    conn.commit()
    print(f"\npruned {len(prune)} redundant fortnight snapshots ({deleted} rows).")
    print("Series now reflects real holdings changes only. Next: compute_mf_conviction_flags.py")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
