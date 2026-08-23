#!/usr/bin/env python3
"""Deterministic source-report -> Wrangler local D1 reconciliation."""
import argparse, json, sqlite3, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; CONFIG=ROOT/"d1/wrangler.jsonc"
TABLES=("ipo","ipo_issue","financial_statements","subscription_snapshots","anchor_allocations",
        "market_bars","listing_observations","documents","source_facts","raw_objects","migration_quarantine")

def reconcile(conn: sqlite3.Connection, source: dict|None=None) -> dict:
    out={table:{"destination_rows":conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]} for table in TABLES}
    out["ipo"].update({"unique_isins":conn.execute("SELECT count(DISTINCT isin) FROM ipo WHERE isin IS NOT NULL").fetchone()[0],
      "null_isin":conn.execute("SELECT count(*) FROM ipo WHERE isin IS NULL").fetchone()[0],
      "duplicate_name_norm":conn.execute("SELECT count(*) FROM (SELECT name_norm FROM ipo GROUP BY name_norm HAVING count(*)>1)").fetchone()[0]})
    for interval in ("1d","15m","5m"):
        row=conn.execute("SELECT count(*),min(ts),max(ts),sum(open_rs IS NULL),sum(close_rs IS NULL) FROM market_bars WHERE interval=?",(interval,)).fetchone()
        out[f"market_{interval}"]={"destination_rows":row[0],"min_timestamp":row[1],"max_timestamp":row[2],"null_open":row[3] or 0,"null_close":row[4] or 0}
    row=conn.execute("SELECT count(*),min(observed_at),max(observed_at),sum(price_rs IS NULL) FROM listing_observations WHERE observation_type='preopen'").fetchone()
    out["preopen"]={"destination_rows":row[0],"min_timestamp":row[1],"max_timestamp":row[2],"null_price":row[3] or 0}
    out["critical_checks"]={"orphan_market_bars":conn.execute("SELECT count(*) FROM market_bars b LEFT JOIN ipo i ON i.id=b.ipo_id WHERE i.id IS NULL").fetchone()[0],
      "quarantined_rows":out["migration_quarantine"]["destination_rows"],"duplicate_fingerprints":conn.execute("SELECT count(*) FROM (SELECT content_fingerprint FROM market_bars GROUP BY content_fingerprint HAVING count(*)>1)").fetchone()[0]}
    if source:
        comparisons={
          "ipo":{"source":source.get("source_ipo",0),"destination":out["ipo"]["destination_rows"]},
          "ipo_issue":{"source":source.get("source_ipo_issue",0),"destination_or_quarantine":out["ipo_issue"]["destination_rows"]+source.get("quarantined_ipo_issue",0)},
          "financial_statements":{"source":source.get("source_financial_statements",0),"destination":out["financial_statements"]["destination_rows"]},
          "subscription_categories":{"source":source.get("mapped_subscription_snapshots",0),"destination":out["subscription_snapshots"]["destination_rows"]},
          "market_daily":{"source":source.get("source_market_daily",0),"destination":out["market_1d"]["destination_rows"]},
          "market_15m":{"source":source.get("source_market_15m",0),"destination":out["market_15m"]["destination_rows"]},
          "listing_observations":{"source":source.get("source_listing_observations",0),"destination":out["listing_observations"]["destination_rows"]},
          "documents":{"source":source.get("source_documents",0),"destination":out["documents"]["destination_rows"]},
          "source_facts":{"source":source.get("source_source_facts",0),"destination":out["source_facts"]["destination_rows"]},
          "ipomatrix_raw":{"source":source.get("source_ipomatrix",0),"destination":out["raw_objects"]["destination_rows"]},
        }
        for key,value in comparisons.items():
            actual=value.get("destination",value.get("destination_or_quarantine"))
            value["equal"]=(actual>=value["source"]) if key=="ipo" else (actual==value["source"])
        out["source_comparisons"]=comparisons;out["zero_silent_loss"]=all(x["equal"] for x in comparisons.values())
    return out

def export_local(path: Path):
    subprocess.run(["npx","wrangler","d1","export","DB","--local","--config",str(CONFIG),"--output",str(path)],cwd=ROOT,check=True,text=True,capture_output=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("db",type=Path,nargs="?");ap.add_argument("--wrangler-local",action="store_true");ap.add_argument("--source-report",type=Path);ap.add_argument("--output",type=Path);a=ap.parse_args()
    if bool(a.db)==a.wrangler_local:ap.error("provide exactly one of db or --wrangler-local")
    source=json.loads(a.source_report.read_text()) if a.source_report else None
    if a.wrangler_local:
        with tempfile.TemporaryDirectory() as td:
            dump=Path(td)/"dump.sql";export_local(dump);conn=sqlite3.connect(":memory:");conn.executescript(dump.read_text());result=reconcile(conn,source);conn.close()
    else:
        with sqlite3.connect(a.db) as conn:result=reconcile(conn,source)
    text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text)
    print(text,end="")
if __name__=="__main__":main()
