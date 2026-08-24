from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]


def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"


def db_url() -> str:
    url = os.environ.get("NEON_READONLY_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise SystemExit("NEON_READONLY_DATABASE_URL (preferred) or DATABASE_URL is required")
    return url


def sqlv(v) -> str:
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def b(v):
    if v is None:
        return None
    return 1 if bool(v) else 0


def js(v):
    if v is None:
        return None
    return json.dumps(v, sort_keys=True, separators=(",", ":"), default=str)


def d1_query(config: Path, binding: str, sql: str):
    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    cmd = [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
           "--remote", "--command", sql, "--json"]
    cp = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if cp.returncode != 0:
        raise SystemExit(f"Wrangler D1 query failed (exit={cp.returncode})\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    payload = json.loads(cp.stdout)
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("results"), list):
                return item["results"]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def execute_sql_file(config: Path, binding: str, statements: list[str], retries: int = 2):
    if not statements:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8", newline="\n") as f:
        f.write("PRAGMA foreign_keys=ON;\n")
        for statement in statements:
            f.write(statement + "\n")
        path = Path(f.name)
    try:
        cmd = [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
               "--remote", "--file", str(path), "--yes"]
        for attempt in range(retries + 1):
            cp = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
            if cp.returncode == 0:
                if cp.stdout:
                    print(cp.stdout, end="" if cp.stdout.endswith("\n") else "\n")
                return
            combined = cp.stdout + cp.stderr
            if attempt < retries and "Authentication error [code: 10000]" not in combined:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Wrangler D1 import failed (exit={cp.returncode})\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    finally:
        path.unlink(missing_ok=True)


def load_neon():
    conn = psycopg2.connect(db_url(), connect_timeout=20)
    conn.set_session(readonly=True, autocommit=False)
    out = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for table in (
                "allowed_users", "access_requests", "user_settings", "listing_outcomes",
                "rule_validation_results", "insights", "ipo_news", "symbol_aliases", "ipo_gmp"
            ):
                cur.execute(f"SELECT * FROM {table}")
                out[table] = list(cur.fetchall())
            # Secrets/cookies/tokens are intentionally excluded. Cloudflare Secrets are canonical.
            cur.execute("SELECT key,value,updated_at FROM platform_config WHERE key='daily_spend_cap_usd'")
            out["app_config"] = list(cur.fetchall())
    finally:
        conn.close()
    return out


def statements(data):
    s = []
    for r in data["allowed_users"]:
        s.append("INSERT INTO allowed_users(email,added_by,added_at,password_hash) VALUES(" +
                 f"{sqlv(r['email'])},{sqlv(r['added_by'])},{sqlv(iso(r['added_at']))},{sqlv(r['password_hash'])}) " +
                 "ON CONFLICT(email) DO UPDATE SET added_by=excluded.added_by,added_at=excluded.added_at,password_hash=excluded.password_hash;")
    for r in data["access_requests"]:
        s.append("INSERT INTO access_requests(email,name,status,requested_at,decided_at,decided_by,note) VALUES(" +
                 f"{sqlv(r['email'])},{sqlv(r['name'])},{sqlv(r['status'])},{sqlv(iso(r['requested_at']))},{sqlv(iso(r['decided_at']))},{sqlv(r['decided_by'])},{sqlv(r['note'])}) " +
                 "ON CONFLICT(email) DO UPDATE SET name=excluded.name,status=excluded.status,requested_at=excluded.requested_at,decided_at=excluded.decided_at,decided_by=excluded.decided_by,note=excluded.note;")
    for r in data["user_settings"]:
        s.append("INSERT INTO user_settings(key,value_json,updated_at) VALUES(" +
                 f"{sqlv(r['key'])},{sqlv(js(r['value']))},{sqlv(iso(r['updated_at']))}) " +
                 "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at;")
    for r in data["app_config"]:
        s.append("INSERT INTO app_config(key,value,updated_at) VALUES(" +
                 f"{sqlv(r['key'])},{sqlv(r['value'])},{sqlv(iso(r['updated_at']))}) " +
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at;")
    for r in data["listing_outcomes"]:
        vals = [r['ipo_id'], r['listing_open'], r['d1_close'], r['gap_pct'], r['best_close'], r['worst_close'],
                b(r['ceiling_20']), b(r['hold_positive_vs_open']), b(r['winner_35']), r['pool'], iso(r['computed_at']), r['dataset_version']]
        s.append("INSERT INTO listing_outcomes(ipo_id,listing_open,d1_close,gap_pct,best_close,worst_close,ceiling_20,hold_positive_vs_open,winner_35,pool,computed_at,dataset_version) VALUES(" +
                 ",".join("NULL" if v is None else str(v) if isinstance(v, int) else sqlv(v) for v in vals) + ") " +
                 "ON CONFLICT(ipo_id) DO UPDATE SET listing_open=excluded.listing_open,d1_close=excluded.d1_close,gap_pct=excluded.gap_pct,best_close=excluded.best_close,worst_close=excluded.worst_close,ceiling_20=excluded.ceiling_20,hold_positive_vs_open=excluded.hold_positive_vs_open,winner_35=excluded.winner_35,pool=excluded.pool,computed_at=excluded.computed_at,dataset_version=excluded.dataset_version;")
    rv_cols = ["id","rule_id","rule_version","backtest_version","dataset","sql_filter","rule_filter","date_range","n","win_rate","avg_return","median_return","max_drawdown","expectancy","p_vs_baseline","beats_baseline","baseline_win_rate","universe_n","run_at","ci95_low","ci95_high","odds_ratio","abs_lift","rel_lift","test_name","q_bh","beats_fdr","power","git_hash","exclusion_ledger_json","finding_status"]
    for r in data["rule_validation_results"]:
        vals = dict(r)
        vals["beats_baseline"] = b(vals.get("beats_baseline")); vals["beats_fdr"] = b(vals.get("beats_fdr"))
        vals["run_at"] = iso(vals.get("run_at")); vals["exclusion_ledger_json"] = js(vals.pop("exclusion_ledger", None))
        encoded=[]
        for c in rv_cols:
            v=vals.get(c)
            encoded.append("NULL" if v is None else str(v) if c in {"id","n","universe_n","beats_baseline","beats_fdr"} else sqlv(v))
        s.append(f"INSERT INTO rule_validation_results({','.join(rv_cols)}) VALUES({','.join(encoded)}) ON CONFLICT(id) DO NOTHING;")
    for r in data["insights"]:
        vals=[r['id'],r['ipo_id'],r['doc_id'],r['category'],r['statement'],r['direction'],r['source_type'],r['page_number'],r['excerpt'],r['model'],r['prompt_version'],str(r['run_id']) if r['run_id'] else None,r['confidence'],b(r['is_current']),iso(r['created_at'])]
        enc=[]
        for i,v in enumerate(vals):
            enc.append("NULL" if v is None else str(v) if i in {0,1,2,7,13} else sqlv(v))
        s.append("INSERT INTO legacy_insights(id,ipo_id,doc_id,category,statement,direction,source_type,page_number,excerpt,model,prompt_version,run_id,confidence,is_current,created_at) VALUES("+",".join(enc)+") ON CONFLICT(id) DO NOTHING;")
    for r in data["ipo_news"]:
        vals=[r['id'],r['company_name'],r['nse_symbol'],r['publisher'],r['headline'],r['url'],iso(r['published_at']),r['snippet'],r['selection_score'],r['source'],r['fetch_status'],b(r['is_current']),iso(r['created_at'])]
        enc=[]
        for i,v in enumerate(vals): enc.append("NULL" if v is None else str(v) if i in {0,8,11} else sqlv(v))
        s.append("INSERT INTO ipo_news(id,company_name,nse_symbol,publisher,headline,url,published_at,snippet,selection_score,source,fetch_status,is_current,created_at) VALUES("+",".join(enc)+") ON CONFLICT(id) DO NOTHING;")
    for r in data["symbol_aliases"]:
        s.append("INSERT INTO symbol_aliases(old_symbol,new_symbol,note,created_at) VALUES("+
                 f"{sqlv(r['old_symbol'])},{sqlv(r['new_symbol'])},{sqlv(r['note'])},{sqlv(iso(r['created_at']))}) ON CONFLICT(old_symbol) DO UPDATE SET new_symbol=excluded.new_symbol,note=excluded.note,created_at=excluded.created_at;")
    for r in data["ipo_gmp"]:
        s.append("INSERT INTO legacy_gmp(company,d,gmp,est_listing,raw) VALUES("+
                 f"{sqlv(r['company'])},{sqlv(str(r['date']))},{sqlv(r['gmp'])},{sqlv(r['est_listing'])},{sqlv(r['raw'])}) ON CONFLICT(company,d) DO UPDATE SET gmp=excluded.gmp,est_listing=excluded.est_listing,raw=excluded.raw;")
    return s


def main() -> int:
    ap=argparse.ArgumentParser(description="Backfill remaining small operational Neon tables into D1; secrets are excluded")
    ap.add_argument("--wrangler-config",type=Path,required=True); ap.add_argument("--binding",default="DB")
    ap.add_argument("--apply",action="store_true"); ap.add_argument("--max-statements-per-import",type=int,default=1500)
    args=ap.parse_args()
    if args.apply and os.environ.get("AACAPITAL_D1_STAGING_CONFIRM") != "YES": ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES before remote D1 writes")
    config=args.wrangler_config.resolve()
    d1_query(config,args.binding,"SELECT COUNT(*) AS n FROM allowed_users")
    data=load_neon(); stmts=statements(data)
    expected={k:len(v) for k,v in data.items()}
    print(json.dumps({"mode":"APPLY" if args.apply else "FETCH_ONLY","source_counts":expected,"statements":len(stmts),"secrets_migrated":0},sort_keys=True))
    if not args.apply: return 0
    for i in range(0,len(stmts),args.max_statements_per_import):
        chunk=stmts[i:i+args.max_statements_per_import]; print(f"D1 import {i+1}-{i+len(chunk)} / {len(stmts)}"); execute_sql_file(config,args.binding,chunk)
    checks={
      "allowed_users":"allowed_users","access_requests":"access_requests","user_settings":"user_settings","app_config":"app_config",
      "listing_outcomes":"listing_outcomes","rule_validation_results":"rule_validation_results","insights":"legacy_insights","ipo_news":"ipo_news","symbol_aliases":"symbol_aliases","ipo_gmp":"legacy_gmp"}
    d1_counts={}
    for key,table in checks.items():
        rows=d1_query(config,args.binding,f"SELECT COUNT(*) AS n FROM {table}"); d1_counts[key]=int(rows[0]["n"]) if rows else 0
    result={"mode":"APPLY","source_counts":expected,"d1_counts":d1_counts,"statements":len(stmts),"secrets_migrated":0,"secret_policy":"CLOUDFLARE_SECRETS_CANONICAL"}
    out=ROOT/"artifacts"/"d1-operational-state-backfill.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True)); print(f"output={out.relative_to(ROOT)}"); return 0

if __name__ == "__main__": raise SystemExit(main())
