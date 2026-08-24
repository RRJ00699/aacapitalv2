from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import subprocess
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parents[1]


def name_norm(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def json_path(payload: Any, path: str | None):
    if not path:
        return None
    cur = payload
    text = path[2:] if path.startswith("$.") else path
    if not text:
        return cur
    for part in text.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def norm_value(value: Any, unit: str | None = None, normalized_unit: str | None = None):
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    text = str(value).strip()
    if unit and normalized_unit and unit != normalized_unit:
        if unit == "rs" and normalized_unit == "cr":
            try:
                return format(Decimal(text.replace(",", "")) / Decimal(10_000_000), "f")
            except InvalidOperation:
                return text
    return text


def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"


def d1_query(config: Path, binding: str, remote: bool, sql: str) -> list[dict[str, Any]]:
    target = "--remote" if remote else "--local"
    cmd = [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding, target, "--command", sql, "--json"]
    cp = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    payload=json.loads(cp.stdout)
    if isinstance(payload,list):
        for item in payload:
            if isinstance(item,dict) and isinstance(item.get("results"),list): return item["results"]
    if isinstance(payload,dict) and isinstance(payload.get("results"),list): return payload["results"]
    return []


def neon_rows(url: str):
    conn = psycopg2.connect(url, connect_timeout=20)
    conn.set_session(readonly=True, autocommit=False)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
          SELECT i.id AS ipo_id,i.ipomatrix_id,i.isin,i.name_norm,i.name_display,
                 x.open_date,x.close_date,x.allotment_date,i.listing_date,
                 x.band_lo,x.band_hi,x.issue_price,x.face_value,x.lot_size,
                 x.issue_size_cr,x.fresh_cr,x.ofs_cr,x.registrar
          FROM ipo i LEFT JOIN ipo_issue x ON x.ipo_id=i.id
        """)
        issue = [dict(r) for r in cur.fetchall()]
        cur.execute("""
          SELECT ipo_id,period,basis,revenue,total_income,ebitda,pat,net_worth,total_debt,total_assets
          FROM financial_statements
        """)
        fin = [dict(r) for r in cur.fetchall()]
        return issue, fin
    finally:
        conn.close()


def choose(d1v, neonv, matrixv):
    if d1v not in (None, ""):
        if neonv not in (None, "") and str(d1v) != str(neonv): return "CONFLICT_KEEP_D1", None
        if matrixv not in (None, "") and str(d1v) != str(matrixv): return "CONFLICT_KEEP_D1", None
        return "PRESENT", None
    if neonv not in (None, "") and matrixv not in (None, ""):
        if str(neonv) == str(matrixv): return "MISSING_D1_AGREE", str(neonv)
        return "MISSING_D1_SOURCE_CONFLICT", str(neonv)
    if neonv not in (None, ""): return "MISSING_D1_NEON", str(neonv)
    if matrixv not in (None, ""): return "MISSING_D1_MATRIX", str(matrixv)
    return "ABSENT_ALL", None


def main() -> int:
    ap=argparse.ArgumentParser(description="Compare D1 core fields with Neon + IPO Matrix and emit review CSV")
    ap.add_argument("--ipomatrix",action="append",type=Path,required=True)
    ap.add_argument("--ipomatrix-map",type=Path,required=True)
    ap.add_argument("--wrangler-config",type=Path,default=ROOT/"d1/wrangler.jsonc")
    ap.add_argument("--binding",default="DB")
    target=ap.add_mutually_exclusive_group(required=True); target.add_argument("--local",action="store_true"); target.add_argument("--staging",action="store_true")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    url=os.environ.get("NEON_READONLY_DATABASE_URL")
    if not url: ap.error("NEON_READONLY_DATABASE_URL is required")
    remote=bool(args.staging)
    if remote and os.environ.get("AACAPITAL_D1_STAGING_CONFIRM")!="YES": ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES for staging")
    mapping=json.loads(args.ipomatrix_map.read_text(encoding="utf-8"))
    issue_neon,fin_neon=neon_rows(url)
    by_mid={r["ipomatrix_id"]:r for r in issue_neon if r.get("ipomatrix_id") is not None}
    by_isin={str(r["isin"]).upper():r for r in issue_neon if r.get("isin")}
    by_name={r["name_norm"] or name_norm(r.get("name_display")):r for r in issue_neon}
    fin_by_key={(r["ipo_id"],str(r["period"]),str(r["basis"])):r for r in fin_neon}
    config=args.wrangler_config.resolve()
    d1_ipo=d1_query(config,args.binding,remote,"SELECT id,ipo_matrix_id,isin,name_norm FROM ipo")
    d1_by_mid={r.get("ipo_matrix_id"):r for r in d1_ipo if r.get("ipo_matrix_id") is not None}
    d1_by_isin={str(r.get("isin")).upper():r for r in d1_ipo if r.get("isin")}
    d1_by_name={r.get("name_norm"):r for r in d1_ipo if r.get("name_norm")}
    table_cache={}
    for table in ("ipo_issue","company_profile","anchor_summary"):
        rows=d1_query(config,args.binding,remote,f"SELECT * FROM {table}"); table_cache[table]={r.get("ipo_id"):r for r in rows}
    fin_d1=d1_query(config,args.binding,remote,"SELECT * FROM financial_statements")
    table_cache["financial_statements"]={(r.get("ipo_id"),str(r.get("period")),str(r.get("basis"))):r for r in fin_d1}
    issue_neon_fields={"open_date":"open_date","close_date":"close_date","allotment_date":"allotment_date","listing_date":"listing_date","band_lo_rs":"band_lo","band_hi_rs":"band_hi","issue_price_rs":"issue_price","face_value_rs":"face_value","lot_size_shares":"lot_size","issue_size_cr":"issue_size_cr","fresh_cr":"fresh_cr","ofs_cr":"ofs_cr","registrar_name":"registrar"}
    fin_neon_fields={"revenue_cr":"revenue","total_income_cr":"total_income","ebitda_cr":"ebitda","pat_cr":"pat","net_worth_cr":"net_worth","debt_cr":"total_debt","assets_cr":"total_assets"}
    output=[]
    for base in args.ipomatrix:
        for path in sorted(base.rglob("*.json")):
            try: payload=json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception: continue
            mid=json_path(payload,mapping.get("matrix_id")); name=json_path(payload,mapping.get("name")); isin=json_path(payload,mapping.get("isin"))
            if mid is None or not name: continue
            neon=by_mid.get(mid) or (by_isin.get(str(isin).upper()) if isin else None) or by_name.get(name_norm(name))
            d1spine=d1_by_mid.get(mid) or (d1_by_isin.get(str(isin).upper()) if isin else None) or d1_by_name.get(name_norm(name))
            ipo_id=(d1spine or {}).get("id") or (neon or {}).get("ipo_id")
            if ipo_id is None:
                output.append({"matrix_id":mid,"ipo_id":"","company_name":name,"table":"ipo","row_key":"","field":"identity","d1_value":"","neon_value":"","matrix_value":str(isin or name),"status":"UNMATCHED_IDENTITY","recommended_value":"","approved":""}); continue
            for section,table in (("ipo_issue","ipo_issue"),("company_profile","company_profile"),("anchor_summary","anchor_summary")):
                d1row=table_cache[table].get(ipo_id,{})
                for field,rule in (mapping.get(section) or {}).items():
                    if not isinstance(rule,dict) or "path" not in rule: continue
                    mv=norm_value(json_path(payload,rule["path"]),rule.get("unit"),rule.get("normalized_unit",rule.get("unit")))
                    nv=norm_value(neon.get(issue_neon_fields.get(field))) if section=="ipo_issue" and neon else None
                    dv=norm_value(d1row.get(field)); status,recommended=choose(dv,nv,mv)
                    if status!="ABSENT_ALL": output.append({"matrix_id":mid,"ipo_id":ipo_id,"company_name":name,"table":table,"row_key":str(ipo_id),"field":field,"d1_value":dv or "","neon_value":nv or "","matrix_value":mv or "","status":status,"recommended_value":recommended or "","approved":""})
            fin_spec=mapping.get("financial_statements") or {}; rows=json_path(payload,fin_spec.get("rows")) or []
            if isinstance(rows,list):
                for item in rows:
                    if not isinstance(item,dict): continue
                    fields=fin_spec.get("fields") or {}; period=norm_value(json_path(item,(fields.get("period") or {}).get("path"))); basis=norm_value(json_path(item,(fields.get("basis") or {}).get("path")))
                    if not period or not basis: continue
                    key=(ipo_id,period,basis); d1row=table_cache["financial_statements"].get(key,{}); nrow=fin_by_key.get(key,{})
                    for field,rule in fields.items():
                        if field in ("period","basis") or not isinstance(rule,dict) or "path" not in rule: continue
                        mv=norm_value(json_path(item,rule["path"]),rule.get("unit"),rule.get("normalized_unit",rule.get("unit"))); nv=norm_value(nrow.get(fin_neon_fields.get(field))); dv=norm_value(d1row.get(field)); status,recommended=choose(dv,nv,mv)
                        if status!="ABSENT_ALL": output.append({"matrix_id":mid,"ipo_id":ipo_id,"company_name":name,"table":"financial_statements","row_key":json.dumps({"ipo_id":ipo_id,"period":period,"basis":basis},separators=(",",":")),"field":field,"d1_value":dv or "","neon_value":nv or "","matrix_value":mv or "","status":status,"recommended_value":recommended or "","approved":""})
    args.output.parent.mkdir(parents=True,exist_ok=True); fields=["matrix_id","ipo_id","company_name","table","row_key","field","d1_value","neon_value","matrix_value","status","recommended_value","approved"]
    with args.output.open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(output)
    counts=defaultdict(int)
    for row in output: counts[row["status"]]+=1
    print(json.dumps({"rows":len(output),"status_counts":dict(sorted(counts.items())),"output":str(args.output)},sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
