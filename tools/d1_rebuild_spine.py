from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import tempfile
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parents[1]
CHILD_TABLES = ("ipo_issue", "company_profile", "financial_statements", "anchor_summary")


def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"


def sqlv(value):
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def name_norm(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip() or None


def d1_query(config: Path, binding: str, sql: str):
    cp = subprocess.run(
        [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
         "--remote", "--command", sql, "--json"],
        cwd=ROOT, check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    payload = json.loads(cp.stdout)
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("results"), list):
                return item["results"]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def neon_spine(url: str):
    conn = psycopg2.connect(url, connect_timeout=20)
    conn.set_session(readonly=True, autocommit=False)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # These columns are already used by the checked-in comparator and are therefore known to exist.
        cur.execute("SELECT id, ipomatrix_id, isin, name_norm, name_display FROM ipo ORDER BY id")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def matrix_payloads(paths):
    out = {}
    for base in paths:
        for path in base.rglob("*.json"):
            try:
                obj = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            data = obj.get("data") if isinstance(obj, dict) else None
            if not isinstance(data, dict):
                continue
            try:
                mid = int(data.get("id"))
            except (TypeError, ValueError):
                continue
            name = data.get("company_name")
            if not name:
                continue
            isin = str(data.get("isin")).strip().upper() if data.get("isin") else None
            out[mid] = {"matrix_id": mid, "name": name, "name_norm": name_norm(name), "isin": isin}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild empty remote D1 IPO spine using canonical Neon IDs, then add Matrix-only identities")
    ap.add_argument("--ipomatrix", action="append", type=Path, required=True)
    ap.add_argument("--wrangler-config", type=Path, required=True)
    ap.add_argument("--binding", default="DB")
    args = ap.parse_args()

    if os.environ.get("AACAPITAL_D1_STAGING_CONFIRM") != "YES":
        ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES")
    url = os.environ.get("NEON_READONLY_DATABASE_URL")
    if not url:
        ap.error("NEON_READONLY_DATABASE_URL is required")

    config = args.wrangler_config.resolve()
    child_counts = {}
    for table in CHILD_TABLES:
        rows = d1_query(config, args.binding, f"SELECT COUNT(*) AS n FROM {table}")
        child_counts[table] = int(rows[0]["n"]) if rows else 0
    if any(child_counts.values()):
        raise SystemExit(f"refusing spine rebuild because child/core rows already exist: {child_counts}")

    neon = neon_spine(url)
    if not neon:
        raise SystemExit("refusing spine rebuild: Neon returned zero ipo rows")
    matrix = matrix_payloads(args.ipomatrix)

    neon_mids = {int(r["ipomatrix_id"]) for r in neon if r.get("ipomatrix_id") is not None}
    neon_isins = {str(r["isin"]).upper() for r in neon if r.get("isin")}
    neon_names = {(r.get("name_norm") or name_norm(r.get("name_display"))) for r in neon}
    matrix_only = [
        p for mid, p in sorted(matrix.items())
        if mid not in neon_mids
        and (not p.get("isin") or p["isin"] not in neon_isins)
        and p.get("name_norm") not in neon_names
    ]

    max_id = max(int(r["id"]) for r in neon)
    statements = ["PRAGMA foreign_keys=ON;", "DELETE FROM ipo;"]
    for r in neon:
        iid = int(r["id"])
        mid = int(r["ipomatrix_id"]) if r.get("ipomatrix_id") is not None else None
        isin = str(r["isin"]).upper() if r.get("isin") else None
        name = r.get("name_display") or r.get("name_norm") or f"IPO {iid}"
        norm = r.get("name_norm") or name_norm(name)
        statements.append(
            "INSERT INTO ipo(id,isin,name,name_norm,ipo_matrix_id,security_kind,status) VALUES("
            f"{iid},{sqlv(isin)},{sqlv(name)},{sqlv(norm)},{'NULL' if mid is None else mid},'EQUITY','ANNOUNCED');"
        )

    for offset, p in enumerate(matrix_only, start=1):
        iid = max_id + offset
        statements.append(
            "INSERT INTO ipo(id,isin,name,name_norm,ipo_matrix_id,security_kind,status) VALUES("
            f"{iid},{sqlv(p.get('isin'))},{sqlv(p['name'])},{sqlv(p['name_norm'])},{p['matrix_id']},'EQUITY','ANNOUNCED');"
        )

    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8", newline="\n") as f:
        f.write("\n".join(statements) + "\n")
        sql_path = Path(f.name)
    try:
        subprocess.run(
            [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", args.binding,
             "--remote", "--file", str(sql_path)],
            cwd=ROOT, check=True, text=True, encoding="utf-8", errors="replace",
        )
    finally:
        sql_path.unlink(missing_ok=True)

    expected = len(neon) + len(matrix_only)
    rows = d1_query(config, args.binding, "SELECT COUNT(*) AS n FROM ipo")
    actual = int(rows[0]["n"]) if rows else -1
    if actual != expected:
        raise SystemExit(f"spine verification failed: expected={expected} actual={actual}")

    print(json.dumps({
        "neon_spine_rows": len(neon),
        "matrix_only_rows": len(matrix_only),
        "expected_total": expected,
        "verified_total": actual,
        "child_counts_before": child_counts,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
