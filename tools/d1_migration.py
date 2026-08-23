#!/usr/bin/env python3
"""Auditable Stage-B loader: read-only Neon/immutable IPO Matrix -> Wrangler local D1.

The default is a dry inventory. ``--apply-local`` invokes Wrangler with ``--local``;
there is deliberately no remote mode.  PostgreSQL is opened read-only and traversed by
keyset, never OFFSET.  Secrets and payloads are never printed.
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, sqlite3, subprocess, tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
WRANGLER = ROOT / "d1" / "wrangler.jsonc"

def fingerprint(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest()

def name_norm(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace("LIMITED", "").replace("LTD", ""))

def number(value: Any) -> float | None:
    if value is None or value == "": return None
    try: return float(str(value).replace(",", "").replace("₹", "").replace("%", "").strip())
    except (TypeError, ValueError): return None

@dataclass(frozen=True)
class UnitResult:
    value: float | None
    anomalies: tuple[str, ...] = ()

def validate_issue(row: dict[str, Any]) -> tuple[str, ...]:
    lo, hi, price = (number(row.get(k)) for k in ("band_lo_rs", "band_hi_rs", "issue_price_rs"))
    face = number(row.get("face_value_rs")); size = number(row.get("issue_size_cr"))
    fresh = number(row.get("fresh_cr")); ofs = number(row.get("ofs_cr")); out=[]
    if lo is not None and hi is not None and lo > hi: out.append("BAND_REVERSED")
    if lo is not None and price is not None and price < lo: out.append("PRICE_OUTSIDE_BAND")
    if hi is not None and price is not None and price > hi: out.append("PRICE_OUTSIDE_BAND")
    if face and lo and lo < face * .5: out.append("BAND_FACE_MAGNITUDE")
    if size and fresh is not None and ofs is not None and abs(fresh + ofs - size) > max(1.0, size*.02): out.append("ISSUE_COMPONENT_MISMATCH")
    for key in ("issue_size_cr","fresh_cr","ofs_cr","market_cap_cr"):
        if number(row.get(key)) is not None and number(row[key]) < 0: out.append("NEGATIVE_MONEY")
    return tuple(sorted(set(out)))

def discover_json(paths: Iterable[Path]) -> list[Path]:
    return sorted({f for p in paths for f in ([p] if p.is_file() else p.rglob("*.json"))})

def inventory(paths: Iterable[Path]) -> list[dict[str, Any]]:
    result=[]
    for path in discover_json(paths):
        raw=path.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
        try: payload=json.loads(raw)
        except json.JSONDecodeError as exc:
            result.append({"path":str(path),"sha256":sha,"size_bytes":len(raw),"valid":False,"error":f"JSON:{exc.lineno}:{exc.colno}"}); continue
        data=payload.get("data",payload) if isinstance(payload,dict) else payload
        matrix_id=None
        if isinstance(data,dict): matrix_id=data.get("id") or data.get("ipo_id") or data.get("ipoId")
        result.append({"path":str(path),"sha256":sha,"size_bytes":len(raw),"valid":True,"matrix_id":matrix_id,"payload":payload})
    return result

def resolve_identity(conn: sqlite3.Connection, *, isin: str|None, name: str, matrix_id: int|None=None) -> int:
    """ISIN, then exact canonical name. Symbol is intentionally not accepted."""
    norm=name_norm(name)
    by_isin=conn.execute("SELECT id FROM ipo WHERE isin=?",(isin,)).fetchone() if isin else None
    by_name=conn.execute("SELECT id FROM ipo WHERE name_norm=?",(norm,)).fetchone()
    if by_isin and by_name and by_isin[0] != by_name[0]: raise ValueError("IDENTITY_COLLISION")
    found=by_isin or by_name
    if found: return int(found[0])
    cur=conn.execute("INSERT INTO ipo(isin,name,name_norm,ipo_matrix_id) VALUES(?,?,?,?)",(isin,name,norm,matrix_id))
    return int(cur.lastrowid)

def postgres_batches(url: str, dataset: str, columns: list[str], batch_size: int=1000):
    """Repeatable-read, read-only keyset stream. Dataset/columns come from fixed code."""
    import psycopg2
    conn=psycopg2.connect(url, connect_timeout=20)
    conn.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
    last=0
    try:
        while True:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {','.join(columns)} FROM {dataset} WHERE id > %s ORDER BY id LIMIT %s",(last,batch_size))
                rows=cur.fetchall()
            if not rows: break
            yield rows; last=rows[-1][0]
    finally: conn.rollback(); conn.close()

def wrangler(args: list[str], *, input_sql: str|None=None) -> subprocess.CompletedProcess[str]:
    cmd=["npx","wrangler","d1",*args,"--local","--config",str(WRANGLER)]
    return subprocess.run(cmd,cwd=ROOT,input=input_sql,text=True,capture_output=True,check=True)

def apply_schema() -> None:
    wrangler(["migrations","apply","DB"])

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--ipomatrix",action="append",type=Path,default=[])
    ap.add_argument("--apply-local",action="store_true"); ap.add_argument("--with-neon",action="store_true")
    ap.add_argument("--report",type=Path,default=ROOT/"artifacts/d1-inventory.json")
    args=ap.parse_args()
    if args.with_neon and not os.environ.get("NEON_READONLY_DATABASE_URL"):
        ap.error("--with-neon requires NEON_READONLY_DATABASE_URL (DATABASE_URL is never accepted)")
    rows=inventory(args.ipomatrix); ids=[r.get("matrix_id") for r in rows if r.get("valid") and r.get("matrix_id") is not None]
    report={"files":len(rows),"valid_json":sum(bool(r.get("valid")) for r in rows),"bytes":sum(r["size_bytes"] for r in rows),
            "unique_matrix_ids":len(set(ids)),"duplicate_matrix_ids":sorted({x for x in ids if ids.count(x)>1}),
            "status":"inventory_only"}
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,indent=2)+"\n")
    if args.apply_local:
        apply_schema(); report["status"]="schema_applied_local"
        args.report.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
