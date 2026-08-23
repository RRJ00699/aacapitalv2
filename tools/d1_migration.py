#!/usr/bin/env python3
"""Neon READ ONLY + immutable IPO Matrix -> Wrangler local D1.

There is intentionally no remote mode and no DATABASE_URL fallback.  Normalized IPO
Matrix identity fields are accepted only through an owner-reviewed path map produced
after ``--survey``; every JSON payload is archived even when identity is unmapped.
"""
from __future__ import annotations

import argparse, datetime as dt, decimal, hashlib, json, os, sqlite3, subprocess, sys, tempfile, time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from _scripts.lib.canon import canon as name_norm

WRANGLER = ROOT / "d1" / "wrangler.jsonc"
DDL = ROOT / "d1" / "migrations" / "0001_functional_model.sql"
DECIMAL = decimal.Decimal

NEON_QUERIES = {
    "ipo": """SELECT i.id,i.isin,i.name_display,i.name_norm,i.symbol,i.ipomatrix_id,i.status,
               i.created_at,(SELECT string_agg(DISTINCT upper(trim(sf.value)),',' ORDER BY upper(trim(sf.value)))
                 FROM source_facts sf WHERE sf.ipo_id=i.id AND sf.field='security_kind') AS security_kind_evidence
               FROM ipo i ORDER BY i.id""",
    "ipo_issue": """SELECT ii.ipo_id,ii.open_date,ii.close_date,ii.allotment_date,i.listing_date,
               ii.band_lo,ii.band_hi,ii.issue_price,ii.face_value,ii.lot_size,ii.issue_size_cr,ii.fresh_cr,
               ii.ofs_cr,ii.registrar FROM ipo_issue ii JOIN ipo i ON i.id=ii.ipo_id ORDER BY ii.ipo_id""",
    "financial_statements": """SELECT ipo_id,period,basis,revenue,total_income,ebitda,
               pat,net_worth,total_debt,total_assets,source FROM financial_statements
               ORDER BY ipo_id,period,basis""",
    "subscription_snapshots": """SELECT ipo_id,captured_at,is_final,qib_x,nii_x,bnii_x,
               snii_x,retail_x,total_x FROM subscription_snapshots ORDER BY ipo_id,captured_at""",
    "market_daily": """SELECT ipo_id,d,o,h,l,c,v FROM market_candles ORDER BY ipo_id,d""",
    "market_15m": """SELECT ipo_id,ts,o,h,l,c,v FROM market_candles_15m ORDER BY ipo_id,ts""",
    "listing_observations": """SELECT ipo_id,observed_at,obs_type,ltp,buy_qty,sell_qty,payload
               FROM listing_observations ORDER BY ipo_id,observed_at,obs_type""",
    "documents": """SELECT ipo_id,doc_type,sha256,COALESCE(source_url,url) source_url,
               byte_size,page_count,object_key,fetched_at FROM documents ORDER BY sha256""",
    "source_facts": """SELECT ipo_id,field,value,source,confidence,fetched_at
               FROM source_facts ORDER BY ipo_id,fetched_at,field,source""",
}

def fingerprint(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":"),
                                     sort_keys=True, default=str).encode()).hexdigest()

def decimal_text(value: Any) -> str | None:
    """Exact canonical decimal representation; never round through binary float."""
    if value is None or value == "": return None
    raw=str(value).replace(",", "").replace("₹", "").replace("%", "").strip()
    try: parsed=DECIMAL(raw)
    except decimal.InvalidOperation: return None
    if not parsed.is_finite(): return None
    rendered=format(parsed, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered

def validate_issue(row: dict[str, Any]) -> tuple[str, ...]:
    def d(key):
        text=decimal_text(row.get(key)); return DECIMAL(text) if text is not None else None
    lo,hi,price,face,size,fresh,ofs=(d(k) for k in ("band_lo_rs","band_hi_rs","issue_price_rs",
        "face_value_rs","issue_size_cr","fresh_cr","ofs_cr")); out=[]
    if lo is not None and hi is not None and lo>hi: out.append("BAND_REVERSED")
    if lo is not None and price is not None and price<lo or hi is not None and price is not None and price>hi: out.append("PRICE_OUTSIDE_BAND")
    if row.get("is_book_built",True) and face is not None and lo is not None and lo<face:
        out.append("BAND_BELOW_FACE_VALUE")
    if size and fresh is not None and ofs is not None and abs(fresh+ofs-size)>max(DECIMAL(1),size*DECIMAL("0.02")): out.append("ISSUE_COMPONENT_MISMATCH")
    for key in ("issue_size_cr","fresh_cr","ofs_cr","market_cap_cr"):
        value=d(key)
        if value is not None and value<0: out.append("NEGATIVE_MONEY")
    return tuple(sorted(set(out)))

def derive_security_kind(evidence_text: Any) -> tuple[str,str|None]:
    evidence={x for x in str(evidence_text or "").split(",") if x};allowed={"EQUITY","REIT","INVIT","FPO"};recognized=evidence&allowed
    if len(evidence)>1 or evidence-recognized:return "EQUITY","AMBIGUOUS_SECURITY_KIND"
    return next(iter(recognized),"EQUITY"),None

def discover_json(paths: Iterable[Path]) -> list[Path]:
    return sorted({f for p in paths for f in ([p] if p.is_file() else p.rglob("*.json"))})

def inventory(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows=[]
    for path in discover_json(paths):
        raw=path.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
        try: payload=json.loads(raw)
        except json.JSONDecodeError as exc:
            rows.append({"path":str(path),"sha256":sha,"size_bytes":len(raw),"valid":False,
                         "error":f"JSON:{exc.lineno}:{exc.colno}","raw":raw.decode("utf-8","replace")}); continue
        rows.append({"path":str(path),"sha256":sha,"size_bytes":len(raw),"valid":True,
                     "payload":payload,"raw":raw.decode("utf-8")})
    return rows

def _leaf_type(value: Any) -> str:
    if value is None:return "null"
    if isinstance(value,bool):return "boolean"
    if isinstance(value,int):return "integer"
    if isinstance(value,float):return "number"
    if isinstance(value,str):return "string"
    return "object" if isinstance(value,dict) else "array"

def walk_json(value: Any, path: str = "$"):
    if isinstance(value,dict):
        for key,item in value.items(): yield from walk_json(item,f"{path}.{key}")
    elif isinstance(value,list):
        for item in value: yield from walk_json(item,f"{path}[]")
    else: yield path,value

def survey(rows: list[dict[str, Any]], sample_limit=3) -> dict[str, Any]:
    counts=Counter(); types=defaultdict(Counter); samples=defaultdict(list)
    for row in rows:
        if not row.get("valid"): continue
        seen=set()
        for path,value in walk_json(row["payload"]):
            types[path][_leaf_type(value)]+=1
            if path not in seen: counts[path]+=1; seen.add(path)
            sample=json.dumps(value,ensure_ascii=False,default=str)
            if sample not in samples[path] and len(samples[path])<sample_limit: samples[path].append(sample)
    return {"files_surveyed":sum(bool(r.get("valid")) for r in rows),"paths":[
        {"json_path":p,"occurrence_count":counts[p],
         "primitive_types":dict(sorted(types[p].items())),
         "null_frequency":(types[p].get("null",0)/sum(types[p].values())),
         "representative_values":samples[p]} for p in sorted(counts)]}

def json_path(payload: Any, path: str|None) -> Any:
    if not path:return None
    value=payload
    for token in path.removeprefix("$.").split("."):
        if not isinstance(value,dict):return None
        value=value.get(token)
    return value

def sql_value(value: Any) -> str:
    if isinstance(value,SqlExpr):return value.sql
    if value is None:return "NULL"
    if isinstance(value,bool):return "1" if value else "0"
    if isinstance(value,int):return str(value)
    if isinstance(value,(dict,list)):value=json.dumps(value,ensure_ascii=False,separators=(",",":"),default=str)
    return "'"+str(value).replace("'","''")+"'"

@dataclass(frozen=True)
class SqlExpr:
    sql: str

def insert_sql(table: str, columns: tuple[str,...], values: tuple[Any,...]) -> str:
    return f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES({','.join(sql_value(v) for v in values)});"

def _row_value(row: dict[str,Any], key: str|None):
    return json_path(row,key) if key and key.startswith("$") else row.get(key) if key else None

def approved_decimal(value: Any, source_unit: str, normalized_unit: str) -> str|None:
    """Apply only a declared conversion; absence of a unit approval is an error."""
    text=decimal_text(value)
    if text is None:return None
    if source_unit==normalized_unit:return text
    if source_unit=="rs" and normalized_unit=="cr":return decimal_text(DECIMAL(text)/DECIMAL(10_000_000))
    raise ValueError(f"UNAPPROVED_UNIT:{source_unit}->{normalized_unit}")

def transform_ipomatrix(payload: dict[str,Any], raw_sha: str, mapping: dict[str,Any]) -> tuple[list[str],Counter]:
    """Reviewed-map-driven bootstrap. No path or unit exists here by assumption."""
    mid=json_path(payload,mapping["matrix_id"]); ipo_id=SqlExpr(f"(SELECT id FROM ipo WHERE ipo_matrix_id={sql_value(mid)})")
    sql=[];counts=Counter()
    def provenance(table,field,raw,normalized,unit,locator):
        observed=mapping.get("observed_at") or "1970-01-01T00:00:00Z"
        vals=(ipo_id,table,field,str(raw),str(normalized),unit,"ipomatrix",raw_sha,observed,"ipomatrix-bootstrap-v1")
        sql.append(insert_sql("source_facts",("ipo_id","target_table","target_field","raw_value","normalized_value","unit","source_name","raw_object_sha256","observed_at","parser_version","observation_fingerprint"),vals+(fingerprint(*vals,locator),)));counts["ipomatrix_fact_rows"]+=1
    def scalar_section(name,table,columns):
        spec=mapping.get(name) or {};values=[];names=[];field_values={}
        for target in columns:
            rule=spec.get(target)
            if not rule:continue
            raw=json_path(payload,rule["path"]);value=raw
            if "unit" in rule:value=approved_decimal(value,rule["unit"],rule.get("normalized_unit",rule["unit"]))
            if value is not None:
                names.append(target);values.append(value);field_values[target]=value;counts[f"ipomatrix_{table}.{target}"]+=1
                provenance(table,target,raw,value,rule.get("normalized_unit",rule.get("unit")),rule["path"])
        if table=="ipo_issue" and validate_issue(field_values):raise ValueError("UNIT_ANOMALY:"+",".join(validate_issue(field_values)))
        if names:sql.append(insert_sql(table,("ipo_id",*names),(ipo_id,*values)));counts[f"ipomatrix_rows_{table}"]+=1
    scalar_section("ipo_issue","ipo_issue",("open_date","close_date","allotment_date","listing_date","band_lo_rs","band_hi_rs","issue_price_rs","face_value_rs","lot_size_shares","issue_size_cr","fresh_cr","ofs_cr","market_cap_cr","registrar_name"))
    scalar_section("company_profile","company_profile",("business_description","sector","industry","incorporated_date","registered_office","website","promoters_json"))
    for section,table,fields,key_fields in (
      ("ownership","ownership",("holder_category","pre_pct","post_pct","dilution_pct"),()),
      ("objects_of_issue","objects_of_issue",("row_order","purpose_code","purpose_raw","amount_cr","document_sha256","page"),()),
      ("financial_statements","financial_statements",("period","basis","revenue_cr","total_income_cr","ebitda_cr","pat_cr","net_worth_cr","reserves_cr","debt_cr","assets_cr","cash_cr","page"),()),
      ("reservations","reservations",("category","shares_reserved","reservation_pct"),()),
      ("subscription_snapshots","subscription_snapshots",("captured_at","category","shares_reserved","shares_bid","subscription_x","is_final"),()),
      ("anchor_allocations","anchor_allocations",("allocation_row","investor_name_raw","shares","price_rs","amount_cr","allocation_pct","document_sha256","page"),()),
      ("peer_comparisons","peer_comparisons",("peer_name_raw","eps_rs","pe_x","pb_x","roe_pct","ronw_pct","market_cap_cr","as_of_date","document_sha256","page"),()),
      ("documents","documents",("sha256","doc_type","source_url","size_bytes","page_count","r2_key","fetched_at"),()),
    ):
        spec=mapping.get(section) or {};rows=json_path(payload,spec.get("rows")) or []
        if not isinstance(rows,list):continue
        for order,row in enumerate(rows,1):
            if not isinstance(row,dict):continue
            names=[];values=[]
            for target in fields:
                rule=(spec.get("fields") or {}).get(target)
                if not rule:continue
                value=order if rule.get("value")=="row_order" else _row_value(row,rule.get("path"));raw=value
                if "unit" in rule:value=approved_decimal(value,rule["unit"],rule.get("normalized_unit",rule["unit"]))
                if value is not None:
                    names.append(target);values.append(value);counts[f"ipomatrix_{table}.{target}"]+=1
                    provenance(table,target,raw,value,rule.get("normalized_unit",rule.get("unit")),f"{spec.get('rows')}[{order-1}].{rule.get('path')}")
            if not names:continue
            if table in ("objects_of_issue","anchor_allocations","peer_comparisons") and "document_sha256" not in names:
                names.append("document_sha256");values.append(raw_sha)
            if table=="subscription_snapshots":
                fp=fingerprint("ipomatrix",mid,*values);names.append("observation_fingerprint");values.append(fp)
            if table=="documents":
                # Documents own their SHA key and IPO is the second column.
                sql.append(insert_sql(table,(names[0],"ipo_id",*names[1:]),(values[0],ipo_id,*values[1:])));counts[f"ipomatrix_rows_{table}"]+=1;continue
            sql.append(insert_sql(table,("ipo_id",*names),(ipo_id,*values)));counts[f"ipomatrix_rows_{table}"]+=1
    scalar_section("anchor_summary","anchor_summary",("shares","amount_cr","investor_count","allocation_pct","document_sha256","observed_at"))
    for metric,rule in (mapping.get("sourced_kpis") or {}).items():
        value=json_path(payload,rule["path"])
        if value is None:continue
        normalized=approved_decimal(value,rule["unit"],rule.get("normalized_unit",rule["unit"]));observed=rule.get("observed_at") or "1970-01-01T00:00:00Z"
        vals=(ipo_id,"source_facts",metric,str(value),normalized,rule.get("normalized_unit",rule["unit"]),"ipomatrix",raw_sha,observed,"ipomatrix-bootstrap-v1")
        sql.append(insert_sql("source_facts",("ipo_id","target_table","target_field","raw_value","normalized_value","unit","source_name","raw_object_sha256","observed_at","parser_version","observation_fingerprint"),vals+(fingerprint(*vals),)));counts[f"ipomatrix_source_facts.{metric}"]+=1;counts["ipomatrix_fact_rows"]+=1
    return sql,counts

def reviewed_paths(mapping: dict[str,Any]) -> set[str]:
    paths=set()
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ("path","rows") and isinstance(item,str):paths.add(item)
                else:walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(mapping);return paths

def resolve_identity(conn: sqlite3.Connection, *, isin: str|None, name: str, matrix_id: int|None=None) -> int:
    norm=name_norm(name); by_isin=conn.execute("SELECT id FROM ipo WHERE isin=?",(isin,)).fetchone() if isin else None
    by_name=conn.execute("SELECT id FROM ipo WHERE name_norm=?",(norm,)).fetchone() if norm else None
    if by_isin and by_name and by_isin[0]!=by_name[0]: raise ValueError("IDENTITY_COLLISION")
    found=by_isin or by_name
    if found:return int(found[0])
    cur=conn.execute("INSERT INTO ipo(isin,name,name_norm,ipo_matrix_id) VALUES(?,?,?,?)",(isin,name,norm,matrix_id)); return int(cur.lastrowid)

def map_ipomatrix_identity(*, isin: str|None, name: str, matrix_id: int|None,
                           by_isin: dict[str,int], by_name: dict[str,int], by_matrix: dict[int,int]):
    """Resolve Matrix identity without symbol; return SQL plus explicit collision reason."""
    norm=name_norm(name); isin_key=(isin or "").strip().upper() or None
    isin_owner=by_isin.get(isin_key) if isin_key else None; name_owner=by_name.get(norm) if norm else None
    matrix_owner=by_matrix.get(matrix_id) if matrix_id is not None else None
    owners={x for x in (isin_owner,name_owner,matrix_owner) if x is not None}
    if len(owners)>1:return [],"IDENTITY_COLLISION"
    owner=next(iter(owners),None)
    if owner is not None:
        if matrix_id is None:return [],None
        by_matrix[matrix_id]=owner
        return [f"UPDATE ipo SET ipo_matrix_id=COALESCE(ipo_matrix_id,{sql_value(matrix_id)}) WHERE id={sql_value(owner)};"],None
    if not norm:return [],"UNMAPPED_IDENTITY"
    statement=insert_sql("ipo",("isin","name","name_norm","ipo_matrix_id"),(isin_key,name,norm,matrix_id))
    # Negative temporary owners still detect collisions among later archive rows. D1
    # assigns the permanent id; no relationship is built from this temporary value.
    temporary=-(len(by_name)+1);by_name[norm]=temporary
    if isin_key:by_isin[isin_key]=temporary
    if matrix_id is not None:by_matrix[matrix_id]=temporary
    return [statement],None

def transform_neon(dataset: str, row: dict[str,Any]) -> list[str]:
    d=decimal_text
    if dataset=="ipo": return [insert_sql("ipo",("id","isin","name","name_norm","nse_symbol","ipo_matrix_id","security_kind","status","discovered_at"),
        (row["id"],row["isin"],row["name_display"],row["name_norm"] or name_norm(row["name_display"]),row["symbol"],row["ipomatrix_id"],str(row.get("security_kind") or "EQUITY").strip().upper(),str(row.get("status") or "ANNOUNCED").strip().upper(),row["created_at"]))]
    if dataset=="ipo_issue":
        mapped={"band_lo_rs":row["band_lo"],"band_hi_rs":row["band_hi"],"issue_price_rs":row["issue_price"],"face_value_rs":row["face_value"],"issue_size_cr":row["issue_size_cr"],"fresh_cr":row["fresh_cr"],"ofs_cr":row["ofs_cr"],"is_book_built":True}
        if validate_issue(mapped): return []
        return [insert_sql("ipo_issue",("ipo_id","open_date","close_date","allotment_date","listing_date","band_lo_rs","band_hi_rs","issue_price_rs","face_value_rs","lot_size_shares","issue_size_cr","fresh_cr","ofs_cr","registrar_name","source_name"),
          (row["ipo_id"],row["open_date"],row["close_date"],row["allotment_date"],row["listing_date"],d(row["band_lo"]),d(row["band_hi"]),d(row["issue_price"]),d(row["face_value"]),row["lot_size"],d(row["issue_size_cr"]),d(row["fresh_cr"]),d(row["ofs_cr"]),row["registrar"],"neon"))]
    if dataset=="financial_statements": return [insert_sql("financial_statements",("ipo_id","period","basis","revenue_cr","total_income_cr","ebitda_cr","pat_cr","net_worth_cr","debt_cr","assets_cr"),
      (row["ipo_id"],row["period"],row["basis"],d(row["revenue"]),d(row["total_income"]),d(row["ebitda"]),d(row["pat"]),d(row["net_worth"]),d(row["total_debt"]),d(row["total_assets"])))]
    if dataset=="subscription_snapshots":
        out=[]
        for cat,key in (("QIB","qib_x"),("NII","nii_x"),("bNII","bnii_x"),("sNII","snii_x"),("retail","retail_x"),("total","total_x")):
            if row[key] is None:continue
            fp=fingerprint("neon",row["ipo_id"],row["captured_at"],cat,d(row[key]),bool(row["is_final"]))
            out.append(insert_sql("subscription_snapshots",("ipo_id","captured_at","category","subscription_x","is_final","observation_fingerprint"),(row["ipo_id"],row["captured_at"],cat,d(row[key]),row["is_final"],fp)))
        return out
    if dataset in ("market_daily","market_15m"):
        interval,stamp=("1d",row.get("d")) if dataset=="market_daily" else ("15m",row.get("ts")); values=(row["ipo_id"],interval,stamp,d(row["o"]),d(row["h"]),d(row["l"]),d(row["c"]),row["v"],"neon")
        return [insert_sql("market_bars",("ipo_id","interval","ts","open_rs","high_rs","low_rs","close_rs","volume_shares","source_name","content_fingerprint"),values+(fingerprint(*values),))]
    if dataset=="listing_observations":
        payload=row["payload"]; values=(row["ipo_id"],row["obs_type"],row["observed_at"],d(row["ltp"]),row["buy_qty"],row["sell_qty"],payload,"neon")
        return [insert_sql("listing_observations",("ipo_id","observation_type","observed_at","price_rs","buy_qty_shares","sell_qty_shares","payload_json","source_name","content_fingerprint"),values+(fingerprint(*values),))]
    if dataset=="documents": return [insert_sql("documents",("sha256","ipo_id","doc_type","source_url","size_bytes","page_count","r2_key","fetched_at"),(row["sha256"],row["ipo_id"],row["doc_type"],row["source_url"],row["byte_size"],row["page_count"],row["object_key"],row["fetched_at"]))]
    if dataset=="source_facts":
        values=(row["ipo_id"],"legacy",row["field"],row["value"],row["source"],row["fetched_at"],"neon-v2-migration",decimal_text(row["confidence"]))
        return [insert_sql("source_facts",("ipo_id","target_table","target_field","raw_value","source_name","observed_at","parser_version","confidence","observation_fingerprint"),values+(fingerprint(*values),))]
    raise KeyError(dataset)

def extract_neon(url: str, batch_size=1000):
    import psycopg2.extras
    conn=psycopg2.connect(url,connect_timeout=20); conn.set_session(readonly=True,isolation_level="REPEATABLE READ",autocommit=False)
    try:
        for dataset,query in NEON_QUERIES.items():
            cur=conn.cursor(name=f"d1_{dataset}",cursor_factory=psycopg2.extras.RealDictCursor); cur.itersize=batch_size; cur.execute(query)
            while True:
                rows=cur.fetchmany(batch_size)
                if not rows:break
                for row in rows:yield dataset,dict(row)
            cur.close()
    finally:conn.rollback();conn.close()

def wrangler(args: list[str]):
    return subprocess.run(["npx","wrangler","d1",*args,"--local","--config",str(WRANGLER)],cwd=ROOT,text=True,capture_output=True,check=True)

def apply_local(sql_lines: list[str]):
    with tempfile.NamedTemporaryFile("w",suffix=".sql",delete=False,encoding="utf-8") as f:
        # Wrangler executes --file atomically. Explicit BEGIN/COMMIT is rejected by D1's
        # execution wrapper, so transaction ownership deliberately remains with Wrangler.
        f.write("PRAGMA foreign_keys=ON;\n"+"\n".join(sql_lines)+"\n"); path=f.name
    try:wrangler(["execute","DB","--file",path])
    finally:Path(path).unlink(missing_ok=True)

def checkpoint_sql(dataset: str, source_rows: int, written_rows: int) -> str:
    """Commit a stable dataset boundary; idempotent reruns resume from this boundary."""
    return ("INSERT INTO migration_checkpoints(dataset,last_key,source_rows,written_rows,updated_at) "
      f"VALUES({sql_value(dataset)},'COMPLETE',{source_rows},{written_rows},CURRENT_TIMESTAMP) "
      "ON CONFLICT(dataset) DO UPDATE SET last_key='COMPLETE',source_rows=excluded.source_rows,"
      "written_rows=excluded.written_rows,updated_at=CURRENT_TIMESTAMP;")

def main() -> int:
    started=time.monotonic()
    ap=argparse.ArgumentParser(); ap.add_argument("--ipomatrix",action="append",type=Path,default=[]); ap.add_argument("--survey",type=Path)
    ap.add_argument("--ipomatrix-map",type=Path); ap.add_argument("--apply-local",action="store_true"); ap.add_argument("--batch-size",type=int,default=1000)
    ap.add_argument("--report",type=Path,default=ROOT/"artifacts/d1-migration.json"); args=ap.parse_args()
    rows=inventory(args.ipomatrix)
    if args.survey:args.survey.parent.mkdir(parents=True,exist_ok=True);args.survey.write_text(json.dumps(survey(rows),indent=2,ensure_ascii=False)+"\n")
    if not args.apply_local:
        print(json.dumps({"files":len(rows),"valid_json":sum(bool(x.get("valid")) for x in rows),"status":"survey_only"},sort_keys=True));return 0
    url=os.environ.get("NEON_READONLY_DATABASE_URL")
    if not url:ap.error("--apply-local requires NEON_READONLY_DATABASE_URL (DATABASE_URL is never accepted)")
    if rows and not args.ipomatrix_map:ap.error("IPO Matrix normalization requires --ipomatrix-map from the reviewed survey")
    mapping=json.loads(args.ipomatrix_map.read_text()) if args.ipomatrix_map else {}
    normalization_sections={"ipo_issue","company_profile","ownership","objects_of_issue","financial_statements","reservations","subscription_snapshots","anchor_summary","anchor_allocations","peer_comparisons","sourced_kpis","documents"}
    if rows and (mapping.get("reviewed") is not True or not normalization_sections.intersection(mapping)):
        ap.error("--ipomatrix-map must be owner-reviewed and include normalized bootstrap sections")
    wrangler(["migrations","apply","DB"]); statements=[]; counts=Counter(); quarantined=0
    by_isin={};by_name={};by_matrix={};by_symbol={}
    for dataset,row in extract_neon(url,args.batch_size):
        structural_reason=None;evidence=set()
        if dataset=="ipo":
            evidence={x for x in str(row.get("security_kind_evidence") or "").split(",") if x}
            row["security_kind"],structural_reason=derive_security_kind(row.get("security_kind_evidence"))
            if row.get("isin"):by_isin[str(row["isin"]).strip().upper()]=row["id"]
            by_name[row.get("name_norm") or name_norm(row.get("name_display"))]=row["id"]
            if row.get("ipomatrix_id") is not None:by_matrix[row["ipomatrix_id"]]=row["id"]
            kind=str(row["security_kind"]).strip().upper();status=str(row.get("status") or "ANNOUNCED").strip().upper()
            if kind not in {"EQUITY","REIT","INVIT","FPO"}:structural_reason="INVALID_SECURITY_KIND"
            elif status not in {"ANNOUNCED","UPCOMING","OPEN","CLOSED","ALLOTTED","LISTED","WITHDRAWN"}:structural_reason="INVALID_LIFECYCLE_STATUS"
            if structural_reason:
                fp=fingerprint("neon","ipo",row["id"],structural_reason)
                statements.append(insert_sql("migration_quarantine",("source_name","source_identity","dataset","reason_code","detail_json","fingerprint"),("neon",row["id"],"ipo",structural_reason,{"security_kind":kind,"status":status},fp)))
                counts["quarantined_ipo_structural"]+=1;quarantined+=1
            symbol=str(row.get("symbol") or "").strip().upper()
            if symbol and symbol in by_symbol and by_symbol[symbol]!=row["id"]:
                fp=fingerprint("neon","ipo",row["id"],"SYMBOL_COLLISION",symbol)
                statements.append(insert_sql("migration_quarantine",("source_name","source_identity","dataset","reason_code","detail_json","fingerprint"),("neon",row["id"],"ipo","SYMBOL_COLLISION",{"symbol":symbol,"first_owner":by_symbol[symbol]},fp)))
                counts["quarantined_ipo_symbol"]+=1;quarantined+=1;row["symbol"]=None
            elif symbol:by_symbol[symbol]=row["id"]
        counts[f"source_{dataset}"]+=1
        for key,value in row.items():
            if value is not None:counts[f"source_nonnull_{dataset}.{key}"]+=1
        mapped=[] if structural_reason else transform_neon(dataset,row)
        if dataset=="ipo" and not evidence and not structural_reason:
            values=(row["id"],"ipo","security_kind",None,"EQUITY",None,"migration_default","security-classification",row["created_at"],"d1-migration-v1")
            mapped.append(insert_sql("source_facts",("ipo_id","target_table","target_field","raw_value","normalized_value","unit","source_name","document_sha256","observed_at","parser_version","observation_fingerprint"),values+(fingerprint(*values),)))
            counts["derived_source_fact_rows"]+=1
        if dataset=="ipo_issue" and not mapped:
            anomalies=validate_issue({"band_lo_rs":row["band_lo"],"band_hi_rs":row["band_hi"],"issue_price_rs":row["issue_price"],"face_value_rs":row["face_value"],"issue_size_cr":row["issue_size_cr"],"fresh_cr":row["fresh_cr"],"ofs_cr":row["ofs_cr"],"is_book_built":True})
            fp=fingerprint("neon",dataset,row["ipo_id"],anomalies); statements.append(insert_sql("migration_quarantine",("source_name","source_identity","dataset","reason_code","detail_json","fingerprint"),("neon",row["ipo_id"],dataset,"UNIT_ANOMALY",{"codes":anomalies},fp)));quarantined+=1;counts["quarantined_ipo_issue"]+=1
        statements.extend(mapped);counts[f"mapped_{dataset}"]+=len(mapped)
    for item in rows:
        sha=item["sha256"]; statements.append(insert_sql("raw_objects",("sha256","source_name","source_object_id","size_bytes","payload_json"),(sha,"ipomatrix",str(json_path(item.get("payload"),mapping.get("matrix_id")) or item["path"]),item["size_bytes"],item["raw"])));counts["source_ipomatrix"]+=1
        if not item.get("valid"):reason="MALFORMED_SOURCE"
        else:
            name=json_path(item["payload"],mapping.get("name")); isin=json_path(item["payload"],mapping.get("isin")); mid=json_path(item["payload"],mapping.get("matrix_id"))
            reason=None if name else "UNMAPPED_IDENTITY"
            if name:
                identity_sql,reason=map_ipomatrix_identity(isin=isin,name=name,matrix_id=mid,by_isin=by_isin,by_name=by_name,by_matrix=by_matrix)
                statements.extend(identity_sql)
                if reason is None:
                    counts["mapped_ipomatrix_identity"]+=1
                    try:
                        bootstrap_sql,bootstrap_counts=transform_ipomatrix(item["payload"],sha,mapping)
                        statements.extend(bootstrap_sql);counts.update(bootstrap_counts)
                    except (KeyError,ValueError) as exc:
                        reason=str(exc).split(":",1)[0];counts["quarantined_ipomatrix_bootstrap"]+=1
        if reason:
            statements.append(insert_sql("migration_quarantine",("source_name","source_identity","dataset","reason_code","detail_json","raw_sha256","fingerprint"),("ipomatrix",item["path"],"raw_objects",reason,{"path":item["path"]},sha,fingerprint("ipomatrix",sha,reason))));quarantined+=1;counts["quarantined_ipomatrix"]+=1
    for dataset in NEON_QUERIES:
        statements.append(checkpoint_sql(dataset,counts[f"source_{dataset}"],counts[f"mapped_{dataset}"]))
    statements.append(checkpoint_sql("ipomatrix",counts["source_ipomatrix"],counts["mapped_ipomatrix_identity"]))
    apply_local(statements)
    observed_paths={entry["json_path"] for entry in survey(rows)["paths"]};approved=reviewed_paths(mapping)
    report={**counts,"quarantined_rows":quarantined,"sql_statements":len(statements),
      "ipomatrix_raw_only_paths":sorted(observed_paths-approved),"runtime_seconds":round(time.monotonic()-started,6),
      "status":"migrated_to_wrangler_local"}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n");print(json.dumps(report,sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
