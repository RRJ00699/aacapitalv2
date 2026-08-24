#!/usr/bin/env python3
"""Deterministic source-report -> Wrangler local D1 reconciliation."""
import argparse, json, os, platform, sqlite3, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; CONFIG=ROOT/"d1/wrangler.jsonc"
BINDING="DB";REMOTE=False
TABLES=("ipo","ipo_issue","company_profile","ownership","objects_of_issue","financial_statements",
        "reservations","subscription_snapshots","anchor_summary","anchor_allocations","peer_comparisons",
        "documents","research_findings","gmp_observations","market_bars","listing_observations",
        "valuation_runs","decision_history","source_facts","raw_objects","migration_quarantine","migration_checkpoints")
CORE_TABLES=("ipo","ipo_issue","company_profile","ownership","objects_of_issue","financial_statements",
  "reservations","subscription_snapshots","anchor_summary","anchor_allocations","peer_comparisons",
  "documents","source_facts","raw_objects","migration_quarantine","migration_checkpoints")
MARKET_TABLES=("market_bars","listing_observations")
NON_CORE_TABLES=tuple(table for table in TABLES if table not in CORE_TABLES)

def _reconcile_core(conn: sqlite3.Connection, source: dict|None) -> dict:
    out={"scope":"core",**{table:{"destination_rows":conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]} for table in CORE_TABLES}}
    out.update({table:{"status":"DEFERRED"} for table in NON_CORE_TABLES})
    out["deferred_tables"]={table:"DEFERRED" for table in NON_CORE_TABLES}
    out["local_d1_logical_size_bytes"]=conn.execute("PRAGMA page_count").fetchone()[0]*conn.execute("PRAGMA page_size").fetchone()[0]
    out["ipo"].update({"unique_isins":conn.execute("SELECT count(DISTINCT isin) FROM ipo WHERE isin IS NOT NULL").fetchone()[0],
      "null_isin":conn.execute("SELECT count(*) FROM ipo WHERE isin IS NULL").fetchone()[0],
      "duplicate_name_norm":conn.execute("SELECT count(*) FROM (SELECT name_norm FROM ipo GROUP BY name_norm HAVING count(*)>1)").fetchone()[0]})
    fk=[row for row in conn.execute("PRAGMA foreign_key_check") if row[0] in CORE_TABLES]
    out["critical_checks"]={"core_foreign_key_violations":len(fk),
      "quarantined_rows":out["migration_quarantine"]["destination_rows"]}
    out["quarantine_by_reason"]={row[0]:row[1] for row in conn.execute("SELECT reason_code,count(*) FROM migration_quarantine GROUP BY reason_code ORDER BY reason_code")}
    out["quarantine_by_dataset"]={row[0]:row[1] for row in conn.execute("SELECT dataset,count(*) FROM migration_quarantine GROUP BY dataset ORDER BY dataset")}
    if not source:return out
    def bounds(neon: int, matrix: int=0):return {"source_rows":neon+matrix,"minimum_unique":max(neon,matrix),"maximum_unique":neon+matrix}
    comparisons={
      "ipo":{**bounds(source.get("source_ipo",0),source.get("mapped_ipomatrix_identity",0)),"destination":out["ipo"]["destination_rows"]},
      "ipo_issue":{**bounds(source.get("source_ipo_issue",0)-source.get("quarantined_ipo_issue",0),source.get("ipomatrix_rows_ipo_issue",0)),"destination":out["ipo_issue"]["destination_rows"]},
      "financial_statements":{**bounds(source.get("source_financial_statements",0),source.get("ipomatrix_rows_financial_statements",0)),"destination":out["financial_statements"]["destination_rows"]},
      "subscription_snapshots":{**bounds(source.get("mapped_subscription_snapshots",0),source.get("ipomatrix_rows_subscription_snapshots",0)),"destination":out["subscription_snapshots"]["destination_rows"]},
      "documents":{**bounds(source.get("source_documents",0),source.get("ipomatrix_rows_documents",0)),"destination":out["documents"]["destination_rows"]},
      "source_facts":{"source":source.get("source_source_facts",0)+source.get("ipomatrix_fact_rows",0)+source.get("derived_source_fact_rows",0),"destination":out["source_facts"]["destination_rows"]},
      "ipomatrix_raw":{"source":source.get("source_ipomatrix",0),"destination":out["raw_objects"]["destination_rows"]},
    }
    for table in ("company_profile","ownership","objects_of_issue","reservations","anchor_summary","anchor_allocations","peer_comparisons"):
        comparisons[f"ipomatrix_{table}"]={"source":source.get(f"ipomatrix_rows_{table}",0),"destination":out[table]["destination_rows"]}
    for key,value in comparisons.items():
        actual=value["destination"]
        if "minimum_unique" in value:
            value["equal"]=value["minimum_unique"]<=actual<=value["maximum_unique"]
            value["resolution"]="EXACT" if actual==value["source_rows"] else "RECONCILED_COALESCENCE"
        else:value["equal"]=actual==value["source"]
    out["source_comparisons"]=comparisons
    column_map={"ipo.isin":("ipo","isin"),"ipo.name_display":("ipo","name"),
      "ipo_issue.band_lo":("ipo_issue","band_lo_rs"),"ipo_issue.band_hi":("ipo_issue","band_hi_rs"),
      "ipo_issue.issue_price":("ipo_issue","issue_price_rs"),"ipo_issue.face_value":("ipo_issue","face_value_rs"),
      "financial_statements.revenue":("financial_statements","revenue_cr"),"financial_statements.pat":("financial_statements","pat_cr")}
    nonnull={}
    for source_key,(table,column) in column_map.items():
        report_key=f"source_nonnull_{source_key}"
        if report_key in source:
            destination=conn.execute(f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL").fetchone()[0]
            expected=source[report_key];nonnull[source_key]={"source_non_null":expected,"destination_non_null":destination,"equal":expected==destination}
    out["per_column_non_null"]=nonnull
    out["zero_silent_loss"]=not fk and all(x["equal"] for x in comparisons.values()) and all(x["equal"] for x in nonnull.values())
    return out

def _reconcile_market(conn: sqlite3.Connection, source: dict|None) -> dict:
    out={"scope":"market",**{table:{"destination_rows":conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]} for table in MARKET_TABLES}}
    out["deferred_tables"]={table:"DEFERRED" for table in CORE_TABLES+tuple(t for t in NON_CORE_TABLES if t not in MARKET_TABLES)}
    for table in out["deferred_tables"]:out[table]={"status":"DEFERRED"}
    if source:
        daily=conn.execute("SELECT count(*) FROM market_bars WHERE interval='1d'").fetchone()[0]
        intraday=conn.execute("SELECT count(*) FROM market_bars WHERE interval='15m'").fetchone()[0]
        comparisons={"market_daily":{"source":source.get("source_market_daily",0),"destination":daily},
          "market_15m":{"source":source.get("source_market_15m",0),"destination":intraday},
          "listing_observations":{"source":source.get("source_listing_observations",0),"destination":out["listing_observations"]["destination_rows"]}}
        for value in comparisons.values():value["equal"]=value["source"]==value["destination"]
        out["source_comparisons"]=comparisons;out["zero_silent_loss"]=all(x["equal"] for x in comparisons.values())
    return out

def reconcile(conn: sqlite3.Connection, source: dict|None=None, scope: str|None=None) -> dict:
    scope=scope or (source or {}).get("scope")
    if scope=="core":return _reconcile_core(conn,source)
    if scope=="market":return _reconcile_market(conn,source)
    out={table:{"destination_rows":conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]} for table in TABLES}
    out["local_d1_logical_size_bytes"]=conn.execute("PRAGMA page_count").fetchone()[0]*conn.execute("PRAGMA page_size").fetchone()[0]
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
    out["quarantine_by_reason"]={row[0]:row[1] for row in conn.execute("SELECT reason_code,count(*) FROM migration_quarantine GROUP BY reason_code ORDER BY reason_code")}
    out["quarantine_by_dataset"]={row[0]:row[1] for row in conn.execute("SELECT dataset,count(*) FROM migration_quarantine GROUP BY dataset ORDER BY dataset")}
    if source:
        comparisons={
          "ipo":{"source":source.get("source_ipo",0),"destination_or_quarantine":out["ipo"]["destination_rows"]+source.get("quarantined_ipo_structural",0)},
          "ipo_issue":{"source":source.get("source_ipo_issue",0),"destination_or_quarantine":out["ipo_issue"]["destination_rows"]+source.get("quarantined_ipo_issue",0)},
          "financial_statements":{"source":source.get("source_financial_statements",0)+source.get("ipomatrix_rows_financial_statements",0),"destination":out["financial_statements"]["destination_rows"]},
          "subscription_categories":{"source":source.get("mapped_subscription_snapshots",0)+source.get("ipomatrix_rows_subscription_snapshots",0),"destination":out["subscription_snapshots"]["destination_rows"]},
          "market_daily":{"source":source.get("source_market_daily",0),"destination":out["market_1d"]["destination_rows"]},
          "market_15m":{"source":source.get("source_market_15m",0),"destination":out["market_15m"]["destination_rows"]},
          "listing_observations":{"source":source.get("source_listing_observations",0),"destination":out["listing_observations"]["destination_rows"]},
          "documents":{"source":source.get("source_documents",0)+source.get("ipomatrix_rows_documents",0),"destination":out["documents"]["destination_rows"]},
          "source_facts":{"source":source.get("source_source_facts",0)+source.get("ipomatrix_fact_rows",0)+source.get("derived_source_fact_rows",0),"destination":out["source_facts"]["destination_rows"]},
          "ipomatrix_raw":{"source":source.get("source_ipomatrix",0),"destination":out["raw_objects"]["destination_rows"]},
        }
        for key,value in comparisons.items():
            actual=value.get("destination",value.get("destination_or_quarantine"))
            value["equal"]=(actual>=value["source"]) if key=="ipo" else (actual==value["source"])
        out["source_comparisons"]=comparisons;out["zero_silent_loss"]=all(x["equal"] for x in comparisons.values())
        for table in ("company_profile","ownership","objects_of_issue","reservations","anchor_summary","anchor_allocations","peer_comparisons"):
            expected=source.get(f"ipomatrix_rows_{table}",0);destination=out[table]["destination_rows"]
            quarantined=out["quarantine_by_dataset"].get(table,0)
            comparisons[f"ipomatrix_{table}"]={"source_mapped_rows":expected,"destination_rows":destination,
              "quarantined_rows":quarantined,"equal":destination+quarantined==expected}
        # Re-evaluate only after every normalized Matrix home has been registered.
        out["zero_silent_loss"]=all(x["equal"] for x in comparisons.values())
        column_map={
          "ipo.isin":("ipo","isin"),"ipo.name_display":("ipo","name"),
          "ipo_issue.band_lo":("ipo_issue","band_lo_rs"),"ipo_issue.band_hi":("ipo_issue","band_hi_rs"),
          "ipo_issue.issue_price":("ipo_issue","issue_price_rs"),"ipo_issue.face_value":("ipo_issue","face_value_rs"),
          "financial_statements.revenue":("financial_statements","revenue_cr"),
          "financial_statements.pat":("financial_statements","pat_cr"),
          "market_daily.o":("market_bars","open_rs","interval='1d'"),"market_daily.c":("market_bars","close_rs","interval='1d'"),
          "market_15m.o":("market_bars","open_rs","interval='15m'"),"market_15m.c":("market_bars","close_rs","interval='15m'"),
          "listing_observations.ltp":("listing_observations","price_rs"),
        };nonnull={}
        for source_key,target in column_map.items():
            report_key=f"source_nonnull_{source_key}"
            if report_key not in source:continue
            table,column,*where=target;clause=f" AND {where[0]}" if where else ""
            destination=conn.execute(f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL{clause}").fetchone()[0]
            expected=source[report_key];nonnull[source_key]={"source_non_null":expected,"destination_non_null":destination,"equal":expected==destination}
        out["per_column_non_null"]=nonnull
        matrix_critical={
          "company_profile":("business_description",),"ownership":("holder_category",),
          "objects_of_issue":("row_order","purpose_raw"),"financial_statements":("period","basis"),
          "reservations":("category",),"subscription_snapshots":("captured_at","category"),
          "anchor_summary":("ipo_id",),"anchor_allocations":("allocation_row","investor_name_raw","document_sha256"),
          "peer_comparisons":("peer_name_raw","document_sha256"),"documents":("sha256","doc_type"),
          "source_facts":("target_field","source_name","observation_fingerprint"),"raw_objects":("sha256","payload_json"),
        }
        for table,columns in matrix_critical.items():
            for column in columns:
                destination=conn.execute(f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL").fetchone()[0]
                key=f"ipomatrix_{table}.{column}";expected=source.get(key)
                nonnull[key]={"source_non_null":expected,"destination_non_null":destination,
                  "equal":True if expected is None else destination>=expected}
        out["zero_silent_loss"] = out["zero_silent_loss"] and all(x["equal"] for x in nonnull.values())
    return out

def export_local(path: Path):
    npx="npx.cmd" if platform.system()=="Windows" else "npx";target="--remote" if REMOTE else "--local"
    subprocess.run([npx,"wrangler","d1","export",BINDING,target,"--config",str(CONFIG),"--output",str(path)],cwd=ROOT,check=True,text=True,encoding="utf-8",errors="replace",capture_output=True)

def main():
    global CONFIG,BINDING,REMOTE
    ap=argparse.ArgumentParser();ap.add_argument("db",type=Path,nargs="?");ap.add_argument("--wrangler-local",action="store_true");ap.add_argument("--wrangler-staging",action="store_true")
    ap.add_argument("--wrangler-config",type=Path);ap.add_argument("--binding",default="DB");ap.add_argument("--scope",choices=("core","market"));ap.add_argument("--source-report",type=Path);ap.add_argument("--output",type=Path);a=ap.parse_args()
    if sum((bool(a.db),a.wrangler_local,a.wrangler_staging))!=1:ap.error("provide exactly one D1 source")
    if a.wrangler_staging:
        if not a.wrangler_config:ap.error("--wrangler-staging requires --wrangler-config")
        if os.environ.get("AACAPITAL_D1_STAGING_CONFIRM")!="YES":ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES")
        CONFIG=a.wrangler_config.resolve();BINDING=a.binding;REMOTE=True
    source=json.loads(a.source_report.read_text(encoding="utf-8")) if a.source_report else None
    scope=a.scope or (source or {}).get("scope")
    if not scope:ap.error("--scope is required when the source report has no scope")
    if source and source.get("scope") and source["scope"]!=scope:ap.error("--scope does not match source report")
    if a.wrangler_local or a.wrangler_staging:
        with tempfile.TemporaryDirectory() as td:
            dump=Path(td)/"dump.sql";export_local(dump);conn=sqlite3.connect(":memory:");conn.executescript(dump.read_text());result=reconcile(conn,source,scope);conn.close()
    else:
        with sqlite3.connect(a.db) as conn:result=reconcile(conn,source,scope)
    text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding="utf-8")
    print(text,end="")
if __name__=="__main__":main()
