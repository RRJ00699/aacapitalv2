from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def name_norm(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def sql_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"


def run_wrangler(config: Path, binding: str, remote: bool, args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    target = "--remote" if remote else "--local"
    cmd = [npx_cmd(), "wrangler", "d1", *args, target, "--config", str(config)]
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )


def inventory(paths: list[Path]):
    for base in paths:
        for path in sorted(base.rglob("*.json")):
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            text = raw.decode("utf-8-sig")
            payload = json.loads(text)
            data = payload.get("data") if isinstance(payload, dict) else None
            data = data if isinstance(data, dict) else {}
            mid = data.get("id")
            try:
                mid = int(mid) if mid is not None else None
            except (TypeError, ValueError):
                mid = None
            name = data.get("company_name")
            isin = data.get("isin")
            yield {
                "sha256": sha,
                "matrix_id": mid,
                "company_name": name,
                "name_norm": name_norm(name),
                "isin": str(isin).strip().upper() if isin else None,
                "filename": str(path),
                "size_bytes": len(raw),
                "payload_json": text,
            }


def split_payload(text: str, chunk_chars: int) -> list[str]:
    if chunk_chars < 1000:
        raise ValueError("--chunk-chars must be >= 1000")
    return [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)] or [""]


def row_sql(row: dict, chunk_chars: int) -> list[str]:
    chunks = split_payload(row["payload_json"], chunk_chars)
    metadata_cols = (
        "sha256",
        "matrix_id",
        "company_name",
        "name_norm",
        "isin",
        "filename",
        "size_bytes",
        "payload_json",
        "chunk_count",
    )
    metadata_values = (
        row["sha256"],
        row["matrix_id"],
        row["company_name"],
        row["name_norm"],
        row["isin"],
        row["filename"],
        row["size_bytes"],
        "",
        len(chunks),
    )
    statements = [
        f"INSERT INTO ipomatrix_raw_stage({','.join(metadata_cols)}) "
        f"VALUES({','.join(sql_value(v) for v in metadata_values)}) "
        "ON CONFLICT(sha256) DO UPDATE SET "
        "matrix_id=excluded.matrix_id,company_name=excluded.company_name,name_norm=excluded.name_norm,"
        "isin=excluded.isin,filename=excluded.filename,size_bytes=excluded.size_bytes,chunk_count=excluded.chunk_count;"
    ]
    for chunk_no, chunk in enumerate(chunks):
        statements.append(
            "INSERT INTO ipomatrix_raw_stage_chunks(sha256,chunk_no,payload_chunk) "
            f"VALUES({sql_value(row['sha256'])},{chunk_no},{sql_value(chunk)}) "
            "ON CONFLICT(sha256,chunk_no) DO NOTHING;"
        )
    return statements


def execute_bounded(config: Path, binding: str, remote: bool, statements: list[str], max_file_bytes: int):
    pending: list[str] = []
    size = 24
    executed = 0

    def flush():
        nonlocal pending, size, executed
        if not pending:
            return
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8", newline="\n") as f:
            f.write("PRAGMA foreign_keys=ON;\n" + "\n".join(pending) + "\n")
            temp = Path(f.name)
        try:
            run_wrangler(config, binding, remote, ["execute", binding, "--file", str(temp)])
        finally:
            temp.unlink(missing_ok=True)
        executed += len(pending)
        print(f"ipomatrix_raw_stage SQL: {executed} / {len(statements)}")
        pending = []
        size = 24

    for statement in statements:
        statement_bytes = len(statement.encode("utf-8")) + 1
        if pending and size + statement_bytes > max_file_bytes:
            flush()
        if statement_bytes + 24 > max_file_bytes:
            raise ValueError(f"single chunk statement exceeds --max-file-bytes: {statement_bytes}")
        pending.append(statement)
        size += statement_bytes
    flush()


def d1_scalar(config: Path, binding: str, remote: bool, sql: str) -> int:
    cp = run_wrangler(config, binding, remote, ["execute", binding, "--command", sql, "--json"], capture=True)
    payload = json.loads(cp.stdout)
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        rows = payload[0].get("results") or []
    elif isinstance(payload, dict):
        rows = payload.get("results") or []
    else:
        rows = []
    return int(rows[0]["n"]) if rows else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Raw-first IPO Matrix -> D1 loader")
    ap.add_argument("--ipomatrix", action="append", type=Path, required=True)
    ap.add_argument("--wrangler-config", type=Path, default=ROOT / "d1/wrangler.jsonc")
    ap.add_argument("--binding", default="DB")
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--local", action="store_true")
    target.add_argument("--staging", action="store_true")
    ap.add_argument("--max-file-bytes", type=int, default=5_000_000)
    ap.add_argument("--chunk-chars", type=int, default=12_000)
    args = ap.parse_args()

    remote = bool(args.staging)
    if remote and os.environ.get("AACAPITAL_D1_STAGING_CONFIRM") != "YES":
        ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES for staging")

    config = args.wrangler_config.resolve()
    run_wrangler(config, args.binding, remote, ["migrations", "apply", args.binding])

    rows = list(inventory(args.ipomatrix))
    statements: list[str] = []
    for row in rows:
        statements.extend(row_sql(row, args.chunk_chars))
    execute_bounded(config, args.binding, remote, statements, args.max_file_bytes)

    real_ipos = sum(1 for row in rows if row["matrix_id"] is not None and row["company_name"])
    helper_files = len(rows) - real_ipos
    staged_files = d1_scalar(config, args.binding, remote, "SELECT count(*) AS n FROM ipomatrix_raw_stage")
    staged_chunks = d1_scalar(config, args.binding, remote, "SELECT count(*) AS n FROM ipomatrix_raw_stage_chunks")
    bad_chunk_counts = d1_scalar(
        config,
        args.binding,
        remote,
        "SELECT count(*) AS n FROM ipomatrix_raw_stage s WHERE "
        "s.chunk_count<>(SELECT count(*) FROM ipomatrix_raw_stage_chunks c WHERE c.sha256=s.sha256)",
    )
    print(
        json.dumps(
            {
                "json_files": len(rows),
                "ipo_payloads": real_ipos,
                "helper_files": helper_files,
                "staged_files": staged_files,
                "staged_chunks": staged_chunks,
                "bad_chunk_counts": bad_chunk_counts,
            },
            sort_keys=True,
        )
    )
    if staged_files != len(rows) or bad_chunk_counts != 0:
        raise SystemExit("raw stage verification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
