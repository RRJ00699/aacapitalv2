#!/usr/bin/env python3
"""Deterministic reconciliation of a Wrangler local D1 export."""
import argparse, json, sqlite3
from pathlib import Path

TABLES=("ipo","ipo_issue","financial_statements","subscription_snapshots","anchor_allocations",
        "market_bars","listing_observations","source_facts","raw_objects","migration_quarantine")

def reconcile(conn: sqlite3.Connection) -> dict:
    out={}
    for table in TABLES:
        count=conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        out[table]={"destination_rows":count}
    out["ipo"].update({"unique_isins":conn.execute("SELECT count(DISTINCT isin) FROM ipo WHERE isin IS NOT NULL").fetchone()[0],
                       "null_isin":conn.execute("SELECT count(*) FROM ipo WHERE isin IS NULL").fetchone()[0],
                       "duplicate_name_norm":conn.execute("SELECT count(*) FROM (SELECT name_norm FROM ipo GROUP BY name_norm HAVING count(*)>1)").fetchone()[0]})
    for interval in ("1d","15m","5m"):
        row=conn.execute("SELECT count(*),min(ts),max(ts) FROM market_bars WHERE interval=?",(interval,)).fetchone()
        out[f"market_{interval}"]={"destination_rows":row[0],"min_timestamp":row[1],"max_timestamp":row[2]}
    row=conn.execute("SELECT count(*),min(observed_at),max(observed_at) FROM listing_observations WHERE observation_type='preopen'").fetchone()
    out["preopen"]={"destination_rows":row[0],"min_timestamp":row[1],"max_timestamp":row[2]}
    out["critical_checks"]={"orphan_market_bars":conn.execute("SELECT count(*) FROM market_bars b LEFT JOIN ipo i ON i.id=b.ipo_id WHERE i.id IS NULL").fetchone()[0],
                            "quarantined_rows":out["migration_quarantine"]["destination_rows"]}
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("db",type=Path); ap.add_argument("--output",type=Path); a=ap.parse_args()
    with sqlite3.connect(a.db) as conn: result=reconcile(conn)
    text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.output: a.output.write_text(text)
    print(text,end="")
if __name__ == "__main__": main()
