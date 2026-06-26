#!/usr/bin/env python3
"""
find_missing_financials.py — coverage report for annual_financials vs the company_master
universe. Tells you which symbols still have no 10-yr fundamentals and writes a targeted
re-fetch list for the Screener pipeline.

Categories per universe symbol:
  OK              — >= --min-years of annual data loaded
  SHALLOW         — loaded but fewer years (newly listed, or thin history)
  FILE_NOT_LOADED — an .xlsx exists in --dir but nothing made it into the DB (parse/load failed)
  MISSING         — no file and no data → needs downloading

Outputs:
  <out>.csv              — every non-OK symbol with status, years, file flag
  <out>_to_fetch.txt     — symbols to (re)download: MISSING + FILE_NOT_LOADED, one per line

Usage:
  python _scripts/find_missing_financials.py --dir "C:\\aacapital-v2\\data\\fundamental_raw"
  python _scripts/find_missing_financials.py --dir ./data/fundamental_raw --min-years 5 --out coverage
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, csv, glob, argparse

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")


def main():
    if not URL:
        sys.exit("DATABASE_URL not set")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="fundamental_raw dir, to detect files that exist but didn't load")
    ap.add_argument("--min-years", type=int, default=5)
    ap.add_argument("--out", default="missing_financials")
    ap.add_argument("--active-only", action="store_true", help="restrict to company_master.is_active = TRUE")
    args = ap.parse_args()

    import psycopg2
    conn = psycopg2.connect(URL)
    cur = conn.cursor()

    where = "WHERE symbol IS NOT NULL" + (" AND is_active = TRUE" if args.active_only else "")
    cur.execute(f"SELECT symbol, company_name, sector FROM company_master {where}")
    universe = {r[0].upper(): (r[1], r[2]) for r in cur.fetchall() if r[0]}

    cur.execute("SELECT symbol, COUNT(DISTINCT fiscal_year) FROM annual_financials GROUP BY symbol")
    loaded = {r[0].upper(): r[1] for r in cur.fetchall()}
    cur.close(); conn.close()

    files = set()
    if args.dir and os.path.isdir(args.dir):
        for p in glob.glob(os.path.join(args.dir, "*.xlsx")):
            base = os.path.basename(p)
            files.add(base.replace("_10yr.xlsx", "").replace(".xlsx", "").upper())

    rows, to_fetch, counts = [], [], {"OK": 0, "SHALLOW": 0, "FILE_NOT_LOADED": 0, "MISSING": 0}
    for sym in sorted(universe):
        name, sector = universe[sym]
        yrs = loaded.get(sym, 0)
        has_file = sym in files
        if yrs >= args.min_years:
            status = "OK"
        elif yrs > 0:
            status = "SHALLOW"
        elif has_file:
            status = "FILE_NOT_LOADED"
        else:
            status = "MISSING"
        counts[status] += 1
        if status != "OK":
            rows.append([sym, name, sector, status, yrs, "yes" if has_file else "no"])
        if status in ("MISSING", "FILE_NOT_LOADED"):
            to_fetch.append(sym)

    # symbols that have data but aren't in the universe (orphans) — informational
    orphans = sorted(set(loaded) - set(universe))

    csv_path = f"{args.out}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "company_name", "sector", "status", "years_loaded", "file_present"])
        w.writerows(rows)

    fetch_path = f"{args.out}_to_fetch.txt"
    with open(fetch_path, "w", encoding="utf-8") as f:
        f.write("\n".join(to_fetch) + ("\n" if to_fetch else ""))

    total = len(universe)
    print(f"Universe (company_master): {total:,} symbols")
    print(f"  OK (>= {args.min_years}yr)   : {counts['OK']:,}")
    print(f"  SHALLOW (<{args.min_years}yr) : {counts['SHALLOW']:,}")
    print(f"  FILE_NOT_LOADED  : {counts['FILE_NOT_LOADED']:,}  (file exists, re-run importer / inspect)")
    print(f"  MISSING          : {counts['MISSING']:,}  (no file — needs download)")
    if orphans:
        print(f"  (orphans: {len(orphans)} symbols in annual_financials not in company_master)")
    print(f"\nWrote {csv_path} ({len(rows):,} non-OK rows)")
    print(f"Wrote {fetch_path} ({len(to_fetch):,} symbols to (re)fetch)")


if __name__ == "__main__":
    main()
