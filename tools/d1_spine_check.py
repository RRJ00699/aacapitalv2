#!/usr/bin/env python3
"""Read-only integrity checker for a local SQLite export of the production D1 DB.

This program never opens the database writable.  A missing table/column is reported
as a failed contract rather than being silently skipped.
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass


ISO_DATE = r"[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
FRESH_OFS_SQL = """SELECT ipo_id,fresh_cr,ofs_cr,issue_size_cr FROM ipo_issue
WHERE fresh_cr IS NOT NULL AND ofs_cr IS NOT NULL AND issue_size_cr IS NOT NULL
  AND ABS(CAST(fresh_cr AS REAL)+CAST(ofs_cr AS REAL)-CAST(issue_size_cr AS REAL))
      > MAX(1.0, ABS(CAST(issue_size_cr AS REAL))*0.02)"""


@dataclass(frozen=True)
class Check:
    name: str
    sql: str


CHECKS = (
    Check("duplicate ISIN", "SELECT isin,COUNT(*) n FROM ipo WHERE isin IS NOT NULL GROUP BY isin HAVING n>1"),
    Check("duplicate name_norm", "SELECT name_norm,COUNT(*) n FROM ipo WHERE name_norm IS NOT NULL GROUP BY name_norm HAVING n>1"),
    Check("duplicate nse_symbol", "SELECT nse_symbol,COUNT(*) n FROM ipo WHERE nse_symbol IS NOT NULL GROUP BY nse_symbol HAVING n>1"),
    Check("malformed ISIN", "SELECT id,isin FROM ipo WHERE isin IS NOT NULL AND (LENGTH(isin)<>12 OR isin GLOB '*[^A-Z0-9]*' OR SUBSTR(isin,1,2) GLOB '*[^A-Z]*' OR SUBSTR(isin,12,1) GLOB '*[^0-9]*')"),
    Check("ipo_issue orphans", "SELECT x.ipo_id FROM ipo_issue x LEFT JOIN ipo i ON i.id=x.ipo_id WHERE i.id IS NULL"),
    Check("outcome orphans", "SELECT x.ipo_id FROM listing_outcomes x LEFT JOIN ipo i ON i.id=x.ipo_id WHERE i.id IS NULL"),
    Check("subscription orphans", "SELECT x.ipo_id FROM subscription_snapshots x LEFT JOIN ipo i ON i.id=x.ipo_id WHERE i.id IS NULL"),
    Check("band/price integrity", "SELECT ipo_id,band_lo_rs,band_hi_rs,issue_price_rs FROM ipo_issue WHERE CAST(band_lo_rs AS REAL)<0 OR CAST(band_hi_rs AS REAL)<0 OR CAST(band_lo_rs AS REAL)>CAST(band_hi_rs AS REAL) OR CAST(issue_price_rs AS REAL)<CAST(band_lo_rs AS REAL) OR CAST(issue_price_rs AS REAL)>CAST(band_hi_rs AS REAL)"),
    Check("gap sanity", "SELECT ipo_id,gap_pct FROM listing_outcomes WHERE ABS(CAST(gap_pct AS REAL))>300"),
    Check("allowed statuses", "SELECT id,status FROM ipo WHERE status NOT IN ('ANNOUNCED','UPCOMING','OPEN','CLOSED','ALLOTTED','LISTED','WITHDRAWN') OR status IS NULL"),
    Check("fresh+OFS reconciliation", FRESH_OFS_SQL),
    Check("raw object floor", "SELECT COUNT(*) n FROM raw_objects HAVING n<968"),
    Check("allowed security_kind", "SELECT id,security_kind FROM ipo WHERE security_kind NOT IN ('EQUITY','REIT','INVIT','FPO') OR security_kind IS NULL"),
)


def date_checks(conn: sqlite3.Connection) -> list[Check]:
    checks: list[Check] = []
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
    for table in tables:
        for col in conn.execute(f'PRAGMA table_info("{table}")'):
            name, declared = col[1], (col[2] or "").upper()
            if "DATE" in declared or name == "d" or name.endswith("_date"):
                checks.append(Check(f"non-ISO date {table}.{name}",
                    f'SELECT rowid,"{name}" FROM "{table}" WHERE "{name}" IS NOT NULL AND "{name}" NOT GLOB \'{ISO_DATE}\''))
    return checks


def run(path: str) -> int:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    failures = 0
    for check in (*CHECKS, *date_checks(conn)):
        try:
            rows = conn.execute(check.sql).fetchmany(21)
        except sqlite3.Error as exc:
            failures += 1
            print(f"FAIL {check.name}: contract unavailable: {exc}")
            continue
        if rows:
            failures += 1
            suffix = " (first 20)" if len(rows) > 20 else ""
            print(f"FAIL {check.name}: {len(rows[:20])} row(s){suffix}: {rows[:20]}")
        else:
            print(f"PASS {check.name}")
    conn.close()
    print(f"SUMMARY failures={failures}")
    return int(bool(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", help="path to one bulk D1 SQLite export")
    return run(parser.parse_args().database)


if __name__ == "__main__":
    raise SystemExit(main())
