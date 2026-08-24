from __future__ import annotations

import argparse, csv, json, platform, subprocess, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def name_norm(v):
    return re.sub(r"[^a-z0-9]+"," ",(v or "").lower()).strip() or None

def npx_cmd(): return "npx.cmd" if platform.system().lower().startswith("win") else "npx"

def d1_query(config: Path,binding: str,sql: str):
    cp=subprocess.run([npx_cmd(),"wrangler","--config",str(config),"d1","execute",binding,"--remote","--command",sql,"--json"],cwd=ROOT,check=True,capture_output=True,text=True,encoding="utf-8",errors="replace")
    payload=json.loads(cp.stdout)
    if isinstance(payload,list):
        for item in payload:
            if isinstance(item,dict) and isinstance(item.get("results"),list): return item["results"]
    if isinstance(payload,dict) and isinstance(payload.get("results"),list): return payload["results"]
    return []

def sqlv(v):
    if v is None or v=="": return "NULL"
    return "'"+str(v).replace("'","''")+"'"

def load_payloads(paths):
    out={}
    for base in paths:
        for p in base.rglob("*.json"):
            try: obj=json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception: continue
            data=obj.get("data") if isinstance(obj,dict) else None
            if not isinstance(data,dict): continue
            mid=data.get("id")
            try: mid=int(mid)
            except Exception: continue
            out[mid]={"matrix_id":mid,"company_name":data.get("company_name"),"isin":str(data.get("isin")).strip().upper() if data.get("isin") else None}
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv",type=Path,required=True)
    ap.add_argument("--ipomatrix",action="append",type=Path,required=True)
    ap.add_argument("--wrangler-config",type=Path,required=True)
    ap.add_argument("--binding",default="DB")
    args=ap.parse_args()
    config=args.wrangler_config.resolve()
    rows=list(csv.DictReader(args.csv.open("r",encoding="utf-8-sig",newline="")))
    mids=sorted({int(r["matrix_id"]) for r in rows if r.get("status")=="UNMATCHED_IDENTITY" and r.get("matrix_id")})
    payloads=load_payloads(args.ipomatrix)
    existing=d1_query(config,args.binding,"SELECT id,ipo_matrix_id,isin,name_norm FROM ipo")
    by_mid={r.get("ipo_matrix_id") for r in existing if r.get("ipo_matrix_id") is not None}
    by_isin={str(r.get("isin")).upper() for r in existing if r.get("isin")}
    by_name={r.get("name_norm") for r in existing if r.get("name_norm")}
    stmts=[]; inserted=0; skipped=0
    for mid in mids:
        p=payloads.get(mid)
        if not p or not p.get("company_name"): raise SystemExit(f"missing payload identity for matrix_id={mid}")
        norm=name_norm(p["company_name"]); isin=p.get("isin")
        if mid in by_mid or (isin and isin in by_isin) or (norm and norm in by_name):
            skipped+=1; continue
        stmts.append(f"INSERT INTO ipo(isin,name,name_norm,ipo_matrix_id,security_kind,status) VALUES({sqlv(isin)},{sqlv(p['company_name'])},{sqlv(norm)},{mid},'EQUITY','ANNOUNCED');")
        by_mid.add(mid)
        if isin: by_isin.add(isin)
        if norm: by_name.add(norm)
        inserted+=1
    if stmts:
        sql="PRAGMA foreign_keys=ON;\n"+"\n".join(stmts)
        subprocess.run([npx_cmd(),"wrangler","--config",str(config),"d1","execute",args.binding,"--remote","--command",sql],cwd=ROOT,check=True,text=True,encoding="utf-8",errors="replace")
    print(json.dumps({"unmatched":len(mids),"inserted":inserted,"skipped_existing":skipped},sort_keys=True))

if __name__=="__main__": main()
