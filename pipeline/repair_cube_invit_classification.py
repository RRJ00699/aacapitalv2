#!/usr/bin/env python3
"""Owner-applied exact-identity repairs for verified structured securities."""
import argparse, json, os

REPAIRS = (
    {"id": 11, "identity_field": "isin", "identity": "INE0NR623014", "type": "INVIT",
     "provenance": "owner_repair:cube-invit-classification:v1"},
    {"id": 746, "identity_field": "symbol", "identity": "BAGMANE", "type": "REIT",
     "provenance": "owner_live_cron:2026-08-19:bagmane-reit:v1"},
)
IPO_ID, ISIN, PROVENANCE = REPAIRS[0]["id"], REPAIRS[0]["identity"], REPAIRS[0]["provenance"]

class IdentityMismatch(RuntimeError): pass

def repair_one(conn, spec, *, write=False):
    cur = conn.cursor()
    cur.execute("SELECT id,isin,symbol,is_mainboard,in_backtest_universe FROM ipo WHERE id=%s", (spec["id"],))
    row = cur.fetchone()
    if not row:
        raise IdentityMismatch(f"expected canonical id={spec['id']} is absent")
    actual = row[1] if spec["identity_field"] == "isin" else str(row[2] or "").upper()
    if actual != spec["identity"]:
        raise IdentityMismatch(f"canonical id={spec['id']} {spec['identity_field']} mismatch")
    if row[3] is False and row[4] is False:
        return {"status":"already_repaired","changed":False,"id":spec["id"],"identity":actual}
    if not write:
        return {"status":"would_repair","changed":False,"id":spec["id"],"identity":actual}
    cur.execute("""UPDATE ipo SET is_mainboard=FALSE,in_backtest_universe=FALSE
      WHERE id=%s AND %s=%s AND (is_mainboard IS DISTINCT FROM FALSE OR in_backtest_universe IS DISTINCT FROM FALSE)"""
      % ("%s", spec["identity_field"], "%s"), (spec["id"], spec["identity"]))
    changed = cur.rowcount == 1
    if not changed: raise IdentityMismatch(f"guarded update rejected id={spec['id']}")
    from fill_v2 import log_source_fact
    log_source_fact(conn,spec["id"],"canonical_classification",f"{spec['type']}/excluded",spec["provenance"],commit=False)
    conn.commit()
    return {"status":"repaired","changed":True,"id":spec["id"],"identity":actual,"provenance":spec["provenance"]}

def repair(conn, *, write=False):
    """Backward-compatible Cube-only repair seam."""
    return repair_one(conn, REPAIRS[0], write=write)

def repair_all(conn, *, write=False):
    return [repair_one(conn, spec, write=write) for spec in REPAIRS]

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--write",action="store_true"); args=parser.parse_args(argv)
    import psycopg2
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=25,options="-c statement_timeout=30000 -c lock_timeout=5000")
    try: result=repair_all(conn,write=args.write)
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    print(json.dumps(result,sort_keys=True)); return result

if __name__ == "__main__": main()
