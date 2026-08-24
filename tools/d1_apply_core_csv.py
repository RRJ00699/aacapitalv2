from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED = {
    "ipo_issue": {"open_date","close_date","allotment_date","listing_date","band_lo_rs","band_hi_rs","issue_price_rs","face_value_rs","lot_size_shares","issue_size_cr","fresh_cr","ofs_cr","market_cap_cr","registrar_name"},
    "company_profile": {"business_description","sector","industry","incorporated_date","registered_office","website","promoters_json"},
    "anchor_summary": {"shares","amount_cr","investor_count","allocation_pct","document_sha256","observed_at"},
    "financial_statements": {"revenue_cr","total_income_cr","ebitda_cr","pat_cr","net_worth_cr","reserves_cr","debt_cr","assets_cr","cash_cr"},
}

def sql_value(value):
    if value is None or value == "": return "NULL"
    return "'" + str(value).replace("'", "''") + "'"

def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"

def run_wrangler(config: Path, binding: str, remote: bool, args: list[str]):
    target="--remote" if remote else "--local"
    subprocess.run([npx_cmd(),"wrangler","--config",str(config),"d1",*args,target],cwd=ROOT,check=True,text=True,encoding="utf-8",errors="replace")

def statement(row: dict[str,str]) -> str:
    table=row["table"]; field=row["field"]
    if table not in ALLOWED or field not in ALLOWED[table]: raise ValueError(f"field not approved for import: {table}.{field}")
    value=row.get("recommended_value")
    if value in (None,""): raise ValueError(f"approved row has no recommended_value: {table}.{field}")
    if table=="financial_statements":
        key=json.loads(row["row_key"]); ipo_id=int(key["ipo_id"]); period=key["period"]; basis=key["basis"]
        return f"INSERT INTO financial_statements(ipo_id,period,basis,{field}) VALUES({ipo_id},{sql_value(period)},{sql_value(basis)},{sql_value(value)}) ON CONFLICT(ipo_id,period,basis) DO UPDATE SET {field}=COALESCE(financial_statements.{field},excluded.{field});"
    ipo_id=int(row["ipo_id"])
    return f"INSERT INTO {table}(ipo_id,{field}) VALUES({ipo_id},{sql_value(value)}) ON CONFLICT(ipo_id) DO UPDATE SET {field}=COALESCE({table}.{field},excluded.{field});"

def execute(config: Path,binding: str,remote: bool,statements: list[str],max_file_bytes: int):
    pending=[];size=24;done=0
    def flush():
        nonlocal pending,size,done
        if not pending:return
        with tempfile.NamedTemporaryFile("w",suffix=".sql",delete=False,encoding="utf-8",newline="\n") as f:
            f.write("PRAGMA foreign_keys=ON;\n"+"\n".join(pending)+"\n"); path=Path(f.name)
        try: run_wrangler(config,binding,remote,["execute",binding,"--file",str(path)])
        finally: path.unlink(missing_ok=True)
        done+=len(pending); print(f"approved_core_fields: {done} / {len(statements)}"); pending=[]; size=24
    for sql in statements:
        b=len(sql.encode("utf-8"))+1
        if pending and size+b>max_file_bytes: flush()
        pending.append(sql); size+=b
    flush()

def main() -> int:
    ap=argparse.ArgumentParser(description="Apply only explicitly approved core comparison CSV rows to D1")
    ap.add_argument("--csv",type=Path,required=True); ap.add_argument("--wrangler-config",type=Path,default=ROOT/"d1/wrangler.jsonc"); ap.add_argument("--binding",default="DB")
    target=ap.add_mutually_exclusive_group(required=True); target.add_argument("--local",action="store_true"); target.add_argument("--staging",action="store_true")
    ap.add_argument("--max-file-bytes",type=int,default=5_000_000); args=ap.parse_args(); remote=bool(args.staging)
    if remote and os.environ.get("AACAPITAL_D1_STAGING_CONFIRM")!="YES": ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES for staging")
    with args.csv.open("r",encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    approved=[r for r in rows if str(r.get("approved") or "").strip().upper() in {"YES","Y","TRUE","1"}]
    unsafe=[r for r in approved if not str(r.get("status") or "").startswith("MISSING_D1")]
    if unsafe: raise SystemExit(f"refusing {len(unsafe)} approved non-missing rows; importer never overwrites existing D1 facts")
    statements=[statement(r) for r in approved]; execute(args.wrangler_config.resolve(),args.binding,remote,statements,args.max_file_bytes)
    print(json.dumps({"approved_rows":len(approved),"applied_rows":len(statements)},sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
