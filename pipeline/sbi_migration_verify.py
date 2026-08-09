#!/usr/bin/env python3
"""Owner-gated, read-only verification of tracked SBI migration candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from .fill_ipo import _norm
    from .company_identity import load_company_identity_set
    from .sbi_ingest import company_from_filename, resolve_ipo
    from .sbi_sonnet import MODEL, PROMPT_VERSION
except ImportError:
    from fill_ipo import _norm
    from company_identity import load_company_identity_set
    from sbi_ingest import company_from_filename, resolve_ipo
    from sbi_sonnet import MODEL, PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "research_notes"
STATUSES = (
    "VERIFIED_ALREADY_PRESENT", "LEDGER_MISSING", "OBJECT_KEY_MISSING",
    "R2_OBJECT_MISSING", "SHA_MISMATCH", "IPO_UNRESOLVED",
    "EXTRACTION_MISSING", "REMOTE_CHECK_ERROR",
)


def local_inventory(directory=DEFAULT_DIR):
    rows = []
    for path in sorted(Path(directory).glob("**/*")):
        if path.is_file() and path.suffix.lower() == ".pdf":
            body = path.read_bytes()
            try:
                filename = str(path.relative_to(ROOT))
            except ValueError:
                filename = str(path)
            rows.append({"local_path": filename, "bytes": len(body),
                         "local_sha256": hashlib.sha256(body).hexdigest()})
    return rows


class OperationCounter:
    def __init__(self):
        self.neon_reads = self.r2_heads = self.r2_gets = 0


def _read(cur, counter, sql, params):
    counter.neon_reads += 1
    cur.execute(sql, params)
    return cur.fetchone()


def verify_remote(row, conn, store, counter, identity_rows=None):
    """Classify one PDF. Exceptions are isolated so every input gets one status."""
    row.update({"ipo_id": None, "isin": None, "documents_id": None,
                "documents_sha256": None, "documents_object_key": None,
                "r2_object_exists": None, "r2_sha_status": "NOT_CHECKED",
                "extraction_tuple": None})
    cur = None
    try:
        cur = conn.cursor()
        company = company_from_filename(ROOT / row["local_path"])
        cur.close(); cur = None
        identity = resolve_ipo(conn, isin=None, company=company, counter=counter,
                               identity_rows=identity_rows)
        row["identity_resolution"] = identity.method
        row["identity_ambiguous_count"] = identity.ambiguous_count
        if identity.row:
            row["ipo_id"], row["isin"], _ = identity.row
        cur = conn.cursor()

        ledger = _read(cur, counter,
            """SELECT id,sha256,object_key,ipo_id FROM documents
                 WHERE sha256=%s AND doc_type='sbi' LIMIT 1""",
            (row["local_sha256"],))
        if ledger:
            (row["documents_id"], row["documents_sha256"],
             row["documents_object_key"], ledger_ipo_id) = ledger
            if row["ipo_id"] is None and ledger_ipo_id is not None:
                owner = _read(cur, counter, "SELECT id,isin FROM ipo WHERE id=%s",
                              (ledger_ipo_id,))
                if owner:
                    row["ipo_id"], row["isin"] = owner

        if row["documents_id"] is not None:
            extraction = _read(cur, counter,
                """SELECT doc_id,model,prompt_version FROM insights
                     WHERE doc_id=%s AND source_type='SBI' AND model=%s
                       AND prompt_version=%s LIMIT 1""",
                (row["documents_id"], MODEL, PROMPT_VERSION))
            row["extraction_tuple"] = list(extraction) if extraction else None

        if row["ipo_id"] is None:
            row["status"] = "IPO_UNRESOLVED"
        elif not ledger:
            row["status"] = "LEDGER_MISSING"
        elif not row["documents_object_key"]:
            row["status"] = "OBJECT_KEY_MISSING"
        else:
            counter.r2_heads += 1
            head = store.head_document(row["documents_object_key"])
            if head is None:
                row.update(status="R2_OBJECT_MISSING", r2_object_exists=False)
            else:
                row["r2_object_exists"] = True
                metadata = {str(k).lower(): str(v).lower()
                            for k, v in head.get("Metadata", {}).items()}
                remote_sha = metadata.get("sha256")
                if remote_sha is None:
                    counter.r2_gets += 1
                    remote_sha = hashlib.sha256(
                        store.get_document(row["documents_object_key"])).hexdigest()
                    row["r2_sha_method"] = "GET"
                else:
                    row["r2_sha_method"] = "HEAD_METADATA"
                matches = (remote_sha == row["local_sha256"] == row["documents_sha256"])
                row["r2_sha_status"] = "VERIFIED" if matches else "MISMATCH"
                if not matches:
                    row["status"] = "SHA_MISMATCH"
                elif row["extraction_tuple"] is None:
                    row["status"] = "EXTRACTION_MISSING"
                else:
                    row["status"] = "VERIFIED_ALREADY_PRESENT"
    except Exception as exc:
        row.update(status="REMOTE_CHECK_ERROR", error=f"{type(exc).__name__}: {exc}")
    finally:
        if cur is not None:
            cur.close()
    return row


def _normalise(value):
    return _norm(value)


def aggregate(rows):
    counts = Counter(r.get("status") for r in rows)
    return {"TOTAL": len(rows),
            "RESOLVED_IPO": sum(r.get("ipo_id") is not None for r in rows),
            **{status: counts[status] for status in STATUSES},
            "AMBIGUOUS_IDENTITY": sum(
                r.get("identity_resolution") == "AMBIGUOUS" for r in rows)}


def preflight(rows):
    count = len(rows)
    components = {
        "identity_set_load": 1,
        "ledger_lookup": count,
        "ledger_owner_lookup": f"0 to {count}",
        "extraction_lookup": f"0 to {count}",
    }
    return {"tracked_pdf_count": count, "tracked_bytes": sum(r["bytes"] for r in rows),
            "expected_neon_reads": {"components": components,
                "total": f"{1 + count} minimum; {1 + 3 * count} maximum"},
            "expected_r2_head_count": f"0 to {count}",
            "maximum_possible_r2_get_count": count, "r2_put_count": 0,
            "neon_writes": 0, "sonnet_calls": 0,
            "estimated_runtime": ">60 seconds (up to 241 sequential remote checks)"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--verify-remote", action="store_true")
    ap.add_argument("--owner-approved", action="store_true")
    ap.add_argument("--directory", default=str(DEFAULT_DIR))
    args = ap.parse_args(argv)
    rows = local_inventory(args.directory)
    print(json.dumps({"preflight": preflight(rows)}), file=sys.stderr, flush=True)
    counter = OperationCounter()
    started = time.monotonic()
    if args.verify_remote:
        if not args.owner_approved or os.environ.get("SBI_OWNER_APPROVED") != "YES":
            raise SystemExit("remote verification requires owner approval")
        required = ("DATABASE_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
                    "R2_SECRET_ACCESS_KEY", "R2_DOCUMENT_BUCKET")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise SystemExit("remote verification credentials missing: " + ", ".join(missing))
        import psycopg2
        try:
            from .r2 import R2DocumentStore
        except ImportError:
            from r2 import R2DocumentStore
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        # Enforce read-only at the PostgreSQL session boundary even if a credential
        # was accidentally provisioned with broader privileges.
        conn.set_session(readonly=True, autocommit=True)
        store = R2DocumentStore()
        try:
            cur = conn.cursor()
            identity_rows = load_company_identity_set(
                cur, execute=lambda sql, params: _counted_execute(
                    cur, counter, sql, params))
            cur.close()
            rows = [verify_remote(row, conn, store, counter, identity_rows)
                    for row in rows]
        finally:
            conn.close()
    else:
        for row in rows:
            row["status"] = "NOT_REMOTELY_VERIFIED"
    runtime = time.monotonic() - started
    print(json.dumps({"files": rows, "aggregate": aggregate(rows),
                      "operations": {"r2_head": counter.r2_heads,
                                     "r2_get": counter.r2_gets,
                                     "neon_reads": counter.neon_reads,
                                     "runtime_seconds": round(runtime, 3)}}, indent=2))
    return 0


def _counted_execute(cur, counter, sql, params):
    counter.neon_reads += 1
    cur.execute(sql, params)


if __name__ == "__main__":
    raise SystemExit(main())
