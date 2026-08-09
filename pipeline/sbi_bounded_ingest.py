#!/usr/bin/env python3
"""Owner-gated, bounded SBI migration and post-write three-way SHA proof.

This checkpoint intentionally has no extraction/model call and no delete operation.
Only rows proven to be ``LEDGER_MISSING`` by the immediately preceding inventory are
eligible for mutation.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import pathlib
import subprocess
import time
from collections import Counter

try:
    from .company_identity import canon, load_company_identity_set
    from .r2 import R2DocumentStore
    from .sbi_ingest import company_from_filename, ingest_file
    from .sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote
    from .sbi_sonnet import MODEL, PROMPT_VERSION, SYSTEM_PROMPT
except ImportError:
    from company_identity import canon, load_company_identity_set
    from r2 import R2DocumentStore
    from sbi_ingest import company_from_filename, ingest_file
    from sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote
    from sbi_sonnet import MODEL, PROMPT_VERSION, SYSTEM_PROMPT

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "research_notes"
STOP_STATUSES = {"SHA_MISMATCH", "OBJECT_KEY_MISSING", "R2_OBJECT_MISSING", "REMOTE_CHECK_ERROR"}


class CountingS3Client:
    """Count actual wire operations without changing R2 store semantics."""
    def __init__(self, inner):
        self.inner = inner
        self.heads = self.gets = self.puts = 0

    def head_object(self, **kwargs):
        self.heads += 1
        return self.inner.head_object(**kwargs)

    def get_object(self, **kwargs):
        self.gets += 1
        return self.inner.get_object(**kwargs)

    def put_object(self, **kwargs):
        self.puts += 1
        return self.inner.put_object(**kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


class CountingCursor:
    def __init__(self, inner, counts):
        self.inner, self.counts = inner, counts

    def execute(self, sql, params=()):
        verb = sql.lstrip().split(None, 1)[0].upper()
        self.counts["neon_writes" if verb in {"INSERT", "UPDATE", "DELETE"} else "neon_reads"] += 1
        return self.inner.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.inner, name)


class CountingConnection:
    def __init__(self, inner, counts):
        self.inner, self.counts = inner, counts

    def cursor(self, *args, **kwargs):
        return CountingCursor(self.inner.cursor(*args, **kwargs), self.counts)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def unresolved_report(rows, identity_rows, limit=3):
    names = [(row[2], canon(row[2])) for row in identity_rows]
    report = []
    for row in rows:
        if row.get("status") != "IPO_UNRESOLVED":
            continue
        company = company_from_filename(ROOT / row["local_path"])
        wanted = canon(company)
        exact = sorted({name for name, value in names if value == wanted})
        closest = exact or [name for name, _ in sorted(
            names, key=lambda item: (-difflib.SequenceMatcher(None, wanted, item[1]).ratio(), item[0]))[:limit]]
        report.append({
            "filename": row["local_path"],
            "canonical_company_name": None,
            "ambiguity_count": row.get("identity_ambiguous_count", 0),
            "closest_deterministic_spine_candidates": closest,
            "reason_unresolved": "multiple canonical-equality matches" if exact else "no exact or unique canonical match",
            "group": "AMBIGUOUS" if exact else "NO_CANONICAL_MATCH",
        })
    return report


def extraction_inventory(rows):
    totals = Counter()
    notes = []
    for row in rows:
        if row.get("r2_sha_status") != "VERIFIED":
            continue
        path = ROOT / row["local_path"]
        page_count = None
        try:
            info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True,
                                  check=True, timeout=30).stdout
            page_count = int(next(line.split(":", 1)[1] for line in info.splitlines()
                                  if line.startswith("Pages:")))
            text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True,
                                  check=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError, StopIteration, ValueError):
            text = ""
        chars = len(text)
        estimated_input = (chars + 3) // 4 + (len(SYSTEM_PROMPT) + 3) // 4
        notes.append({"filename": row["local_path"], "pages": page_count,
                      "pdf_bytes": row["bytes"], "text_chars": chars,
                      "estimated_input_tokens": estimated_input})
        totals.update(notes=1, pages=page_count or 0, pdf_bytes=row["bytes"],
                      text_chars=chars, input_tokens=estimated_input)
    return {"model": MODEL, "prompt_version": PROMPT_VERSION,
            "already_extracted": sum(r.get("r2_sha_status") == "VERIFIED" and r.get("extraction_tuple") is not None for r in rows),
            "needs_extraction": sum(r.get("r2_sha_status") == "VERIFIED" and r.get("extraction_tuple") is None for r in rows),
            "size_estimate": dict(totals),
            "token_method": "UTF-8 text characters / 4 plus system prompt; no model call",
            "estimated_output_tokens_per_note": "UNKNOWN until owner sets an output cap",
            "estimated_cost_per_note": "UNKNOWN: no owner-approved price card supplied",
            "estimated_total_cost": "UNKNOWN: no owner-approved price card supplied",
            "estimated_runtime": "UNKNOWN: no paid-call latency evidence collected",
            "notes": notes}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-approved", action="store_true")
    ap.add_argument("--directory", default=str(DEFAULT_DIR))
    args = ap.parse_args(argv)
    if not args.owner_approved or os.environ.get("SBI_OWNER_APPROVED") != "YES":
        raise SystemExit("bounded ingest requires --owner-approved and SBI_OWNER_APPROVED=YES")
    required = ("DATABASE_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_DOCUMENT_BUCKET")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit("bounded ingest credentials missing: " + ", ".join(missing))

    import psycopg2
    started = time.monotonic()
    raw_conn = psycopg2.connect(os.environ["DATABASE_URL"])
    db_counts = Counter()
    conn = CountingConnection(raw_conn, db_counts)
    store = R2DocumentStore()
    wire = CountingS3Client(store.client)
    store.client = wire
    failures = []
    try:
        cur = conn.cursor()
        identity_rows = load_company_identity_set(cur)
        cur.close()
        initial_counter = OperationCounter()
        rows = [verify_remote(row, conn, store, initial_counter, identity_rows)
                for row in local_inventory(args.directory)]
        scope = [row for row in rows if row["status"] == "LEDGER_MISSING"]
        preflight = {"PDF count to ingest": len(scope),
                     "total bytes to ingest": sum(row["bytes"] for row in scope),
                     "expected R2 PUT count": len(scope),
                     "expected Neon writes": len(scope),
                     "expected verification HEAD/GET count": f"{len(scope)} HEAD; 0 to {len(scope)} GET",
                     "estimated runtime": f"approximately {round(len(scope) * 17.25 / 241, 1)} seconds using owner read-only baseline"}
        print(json.dumps({"pre_ingest": preflight}), flush=True)
        for row in scope:
            try:
                result = ingest_file(conn, ROOT / row["local_path"], store=store,
                                     owner_approved=True, retain_source=True,
                                     identity_rows=identity_rows)
                if result["status"] != "LEDGERED":
                    failures.append({"filename": row["local_path"], **result})
            except Exception as exc:
                raw_conn.rollback()
                failures.append({"filename": row["local_path"], "error": f"{type(exc).__name__}: {exc}"})

        final_counter = OperationCounter()
        verified = [verify_remote(row, conn, store, final_counter, identity_rows)
                    for row in local_inventory(args.directory)]
        bad = [row for row in verified if row["status"] in STOP_STATUSES]
        result = {"aggregate": aggregate(verified),
                  "ingest_attempts": len(scope), "successful_ledger_writes": len(scope) - len(failures),
                  "successful_r2_objects": sum(r.get("r2_sha_status") == "VERIFIED" for r in verified),
                  "failed_ingests": failures,
                  "three_way_sha_match_count": sum(r.get("r2_sha_status") == "VERIFIED" for r in verified),
                  "unresolved": unresolved_report(verified, identity_rows),
                  "operations": {"r2_put": wire.puts, "r2_head": wire.heads,
                                 "r2_get": wire.gets, **db_counts,
                                 "runtime_seconds": round(time.monotonic() - started, 3)},
                  "extraction_estimate": extraction_inventory(verified),
                  "stop": bool(bad or failures),
                  "next_owner_approval": "Approve Sonnet extraction scope/cost and separately decide the 43 unresolved identities; deletion remains unapproved."}
        print(json.dumps(result, indent=2))
        return 1 if result["stop"] else 0
    finally:
        raw_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
