#!/usr/bin/env python3
"""
_scripts/ipo/dedup_ipos.py
─────────────────────────────────────────────────────────────────────────────
Collapses duplicate company rows in ipo_intelligence.

The backtest exposed the same company appearing 2-3 times with inconsistent,
partial data (e.g. Ola Electric scored BUY_AT_OPEN on one row and AVOID on a
near-empty duplicate). That inflates the tab counts and produces contradictory
recommendations. This keeps ONE row per company — the most-populated one — and
(optionally) backfills that row's NULLs from its duplicates before deleting them.

SAFE BY DEFAULT: dry-run prints the plan and writes nothing. Use --apply to
execute inside a single transaction. Use --merge to coalesce NULLs from dupes
into the survivor first.

Usage:
  python _scripts/ipo/dedup_ipos.py                  # dry-run report
  python _scripts/ipo/dedup_ipos.py --merge          # dry-run, show merges too
  python _scripts/ipo/dedup_ipos.py --merge --apply  # actually do it

Install: pip install psycopg2-binary python-dotenv
"""

import os
import re
import sys
import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local" if Path(".env.local").exists() else ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

_NULLISH = {"", "nan", "none", "null", "-", "--"}
# fields where two different non-null values across dupes are worth flagging
KEY_FIELDS = ["issue_price", "listing_open", "listing_date", "is_sme"]


def norm_name(name: str) -> str:
    """Normalise a company name so 'X Ltd.' and 'X Limited' group together."""
    s = (name or "").lower().strip()
    s = re.sub(r"[.,]", "", s)
    s = re.sub(r"\b(ltd|limited|pvt|private|the|india|co|corp|corporation|inc)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_populated(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip().lower() not in _NULLISH
    return True


def richness(row: dict) -> int:
    """Count populated columns — the survivor is the richest row."""
    return sum(1 for v in row.values() if is_populated(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    ap.add_argument("--merge", action="store_true", help="coalesce NULLs from dupes into survivor")
    args = ap.parse_args()

    if not DATABASE_URL:
        print("ERROR: set DATABASE_URL (or NEON_DATABASE_URL)", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM ipo_intelligence")
    rows = cur.fetchall()

    groups = {}
    for r in rows:
        groups.setdefault(norm_name(r.get("company_name")), []).append(r)
    dupes = {k: v for k, v in groups.items() if len(v) > 1 and k}

    print(f"\n{len(rows)} rows -> {len(groups)} unique companies; "
          f"{len(dupes)} have duplicates.\n")
    if not dupes:
        print("Nothing to dedup.")
        conn.close()
        return

    to_delete, merges = [], []
    for key, grp in sorted(dupes.items()):
        grp_sorted = sorted(grp, key=richness, reverse=True)
        survivor = grp_sorted[0]
        losers = grp_sorted[1:]
        names = " | ".join(f"#{g['id']}({richness(g)} cols)" for g in grp_sorted)
        print(f"  {survivor.get('company_name','?')[:34]:34s}  keep #{survivor['id']}  "
              f"drop {[l['id'] for l in losers]}   [{names}]")

        # flag conflicting key values
        for f in KEY_FIELDS:
            vals = {str(g.get(f)) for g in grp if is_populated(g.get(f))}
            if len(vals) > 1:
                print(f"        ! conflicting {f}: {sorted(vals)}")

        if args.merge:
            fill = {}
            for f in survivor.keys():
                if f in ("id", "company_name"):
                    continue
                if not is_populated(survivor.get(f)):
                    for l in losers:
                        if is_populated(l.get(f)):
                            fill[f] = l[f]
                            break
            if fill:
                merges.append((survivor["id"], fill))
        to_delete.extend(l["id"] for l in losers)

    print(f"\nPlan: keep {len(dupes)} survivors, delete {len(to_delete)} duplicate rows"
          + (f", backfill {len(merges)} survivors" if args.merge else "") + ".")

    if not args.apply:
        print("\nDRY-RUN — nothing changed. Re-run with --apply"
              + (" --merge" if args.merge else "") + " to execute.")
        conn.close()
        return

    try:
        if args.merge:
            for sid, fill in merges:
                sets = ", ".join(f"{k} = %s" for k in fill)
                cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id = %s",
                            list(fill.values()) + [sid])
        if to_delete:
            cur.execute("DELETE FROM ipo_intelligence WHERE id = ANY(%s)", (to_delete,))
        conn.commit()
        print(f"\nApplied: deleted {len(to_delete)} rows"
              + (f", backfilled {len(merges)} survivors" if args.merge else "") + ".")
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print(f"ERROR (rolled back): {e}", file=sys.stderr)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
