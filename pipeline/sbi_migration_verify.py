#!/usr/bin/env python3
"""Bounded, read-only verifier for tracked SBI migration candidates.

Dry-run performs only local hashing. ``--verify-remote`` performs Neon reads and R2
HEADs (and a GET only when metadata cannot prove the byte hash); it never writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "research_notes"


def local_inventory(directory=DEFAULT_DIR):
    rows = []
    for path in sorted(Path(directory).glob("**/*")):
        if path.is_file() and path.suffix.lower() == ".pdf":
            body = path.read_bytes()
            try:
                filename = str(path.relative_to(ROOT))
            except ValueError:
                filename = str(path)
            rows.append({"filename": filename, "bytes": len(body),
                         "local_sha256": hashlib.sha256(body).hexdigest()})
    return rows


def ledger_row(conn, digest):
    cur = conn.cursor()
    cur.execute("""SELECT d.id,d.sha256,d.object_key,d.ipo_id,i.isin
                     FROM documents d LEFT JOIN ipo i ON i.id=d.ipo_id
                    WHERE d.sha256=%s AND d.doc_type='sbi' LIMIT 1""", (digest,))
    return cur.fetchone()


def verify_remote(row, conn, store):
    found = ledger_row(conn, row["local_sha256"])
    row.update({"documents_id": None, "documents_sha256": None, "object_key": None,
                "ipo_id": None, "isin": None, "r2_status": "NOT_CHECKED",
                "extraction_status": "NOT_CHECKED"})
    if not found:
        row["status"] = "LEDGER_ROW_MISSING"
        return row
    row.update(dict(zip(("documents_id", "documents_sha256", "object_key", "ipo_id", "isin"), found)))
    if not row["object_key"]:
        row["status"] = "OBJECT_KEY_MISSING"
        return row
    head = store.head_document(row["object_key"])
    if head is None:
        row.update(status="R2_OBJECT_MISSING", r2_status="MISSING")
        return row
    metadata = {str(k).lower(): str(v).lower() for k, v in head.get("Metadata", {}).items()}
    remote_sha = metadata.get("sha256")
    if remote_sha is None:
        remote_sha = hashlib.sha256(store.get_document(row["object_key"])).hexdigest()
        row["r2_method"] = "GET"
    else:
        row["r2_method"] = "HEAD_METADATA"
    row["r2_status"] = "VERIFIED" if remote_sha == row["local_sha256"] else "SHA_MISMATCH"
    cur = conn.cursor()
    cur.execute("""SELECT 1 FROM insights WHERE doc_id=%s AND source_type='SBI' LIMIT 1""",
                (row["documents_id"],))
    row["extraction_status"] = "EXTRACTED" if cur.fetchone() else "PENDING"
    row["status"] = ("ALREADY_LEDGERED_AND_R2_VERIFIED" if row["r2_status"] == "VERIFIED"
                     else "SHA_MISMATCH")
    return row


def aggregate(rows):
    return {
        "TOTAL": len(rows), "LEDGERED": sum(r.get("documents_id") is not None for r in rows),
        "R2_VERIFIED": sum(r.get("r2_status") == "VERIFIED" for r in rows),
        "SHA_MATCH": sum(r.get("r2_status") == "VERIFIED" for r in rows),
        "EXTRACTED": sum(r.get("extraction_status") == "EXTRACTED" for r in rows),
        "UNRESOLVED": sum(r.get("ipo_id") is None and r.get("documents_id") is not None for r in rows),
        "MISSING": sum("MISSING" in r.get("status", "") for r in rows),
        "MISMATCH": sum(r.get("status") == "SHA_MISMATCH" for r in rows),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify-remote", action="store_true")
    ap.add_argument("--owner-approved", action="store_true")
    ap.add_argument("--directory", default=str(DEFAULT_DIR))
    args = ap.parse_args(argv)
    if not args.dry_run and not args.verify_remote:
        ap.error("choose --dry-run or --verify-remote")
    rows = local_inventory(args.directory)
    if args.verify_remote:
        if not args.owner_approved or os.environ.get("SBI_OWNER_APPROVED") != "YES":
            raise SystemExit("remote verification requires owner approval")
        import psycopg2
        try:
            from .r2 import R2DocumentStore
        except ImportError:
            from r2 import R2DocumentStore
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        store = R2DocumentStore()
        try:
            rows = [verify_remote(row, conn, store) for row in rows]
        finally:
            conn.close()
    else:
        for row in rows:
            row.update(status="READY_FOR_INGEST", documents_id=None,
                       r2_status="NOT_CHECKED_DRY_RUN", extraction_status="NOT_CHECKED_DRY_RUN")
    print(json.dumps({"files": rows, "aggregate": aggregate(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
