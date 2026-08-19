#!/usr/bin/env python3
"""Owner-applied, exact-identity repair for the known Cube Highways INVIT row."""
import argparse, json, os

IPO_ID = 11
ISIN = "INE0NR623014"
PROVENANCE = "owner_repair:cube-invit-classification:v1"


def repair(conn, *, write=False):
    cur = conn.cursor()
    cur.execute("SELECT id,isin,is_mainboard,in_backtest_universe FROM ipo WHERE id=%s AND isin=%s", (IPO_ID, ISIN))
    row = cur.fetchone()
    if not row:
        return {"status": "identity_not_found", "changed": False, "id": IPO_ID, "isin": ISIN}
    if row[2] is False and row[3] is False:
        return {"status": "already_repaired", "changed": False, "id": IPO_ID, "isin": ISIN}
    if not write:
        return {"status": "would_repair", "changed": False, "id": IPO_ID, "isin": ISIN}
    cur.execute("""UPDATE ipo SET is_mainboard=FALSE,in_backtest_universe=FALSE
                   WHERE id=%s AND isin=%s
                     AND (is_mainboard IS DISTINCT FROM FALSE OR in_backtest_universe IS DISTINCT FROM FALSE)""", (IPO_ID, ISIN))
    changed = cur.rowcount == 1
    if changed:
        from fill_v2 import log_source_fact
        log_source_fact(conn, IPO_ID, "canonical_classification", "INVIT/excluded", PROVENANCE, commit=False)
        conn.commit()
    return {"status": "repaired" if changed else "already_repaired", "changed": changed, "id": IPO_ID, "isin": ISIN,
            "provenance": PROVENANCE if changed else None}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try: result = repair(conn, write=args.write)
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    print(json.dumps(result, sort_keys=True))
    return result

if __name__ == "__main__": main()
