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
import time
from collections import Counter

try:
    from .company_identity import canon, load_company_identity_set
    from .r2 import R2DocumentStore
    from .sbi_ingest import company_from_filename, ingest_file
    from .sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote
except ImportError:
    from company_identity import canon, load_company_identity_set
    from r2 import R2DocumentStore
    from sbi_ingest import company_from_filename, ingest_file
    from sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote

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
        if "SELECT id, ipo_id, doc_type, object_key" in sql and "FROM documents WHERE sha256" in sql:
            self.counts["document_ledger_reads"] += 1
        elif "INSERT INTO documents" in sql:
            self.counts["document_ledger_writes"] += 1
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
    """Build a human-review report without changing any classification.

    Fuzzy/difflib suggestions are display-only and MUST NEVER feed identity
    resolution, ledger ownership, or automated ingest.
    """
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
            "ambiguity_count": row.get("identity_ambiguous_count", 0),
            "closest_name_suggestions_advisory_only": closest,
            "reason_unresolved": "multiple canonical-equality matches" if exact else "no exact or unique canonical match",
            "group": "AMBIGUOUS" if exact else "NO_CANONICAL_MATCH",
        })
    return report


def preflight_contract(rows, scope, pre_ingest_classification_reads):
    """Return the owner cost contract, separating reads, writes, and R2 calls."""
    expected_post_reads = len(rows) + len(scope)
    neon_contract = {
        "identity_set_load": 1,
        "pre_ingest_classification_reads": pre_ingest_classification_reads,
        "per_document_ledger_select": len(scope),
        "per_document_insert": len(scope),
        "post_ingest_verification_reads": expected_post_reads,
        "expected_total_reads": 1 + pre_ingest_classification_reads + len(scope) + expected_post_reads,
        "expected_total_writes": len(scope),
    }
    return {"PDF count to ingest": len(scope),
            "total bytes to ingest": sum(row["bytes"] for row in scope),
            "expected R2 PUT count": len(scope),
            "expected Neon statements": neon_contract,
            "expected verification HEAD/GET count": f"{len(scope)} HEAD; 0 to {len(scope)} GET",
            "estimated runtime": f"approximately {round(len(scope) * 17.25 / 241, 1)} seconds using owner read-only baseline"}


def next_owner_approval(unresolved):
    return (f"Approve Sonnet extraction scope/cost and separately decide the "
            f"{len(unresolved)} unresolved identities; deletion remains unapproved.")


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
        preflight = preflight_contract(rows, scope, initial_counter.neon_reads)
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
        unresolved = unresolved_report(verified, identity_rows)
        result = {"aggregate": aggregate(verified),
                  "ingest_attempts": len(scope), "successful_ledger_writes": len(scope) - len(failures),
                  "successful_r2_objects": sum(r.get("r2_sha_status") == "VERIFIED" for r in verified),
                  "failed_ingests": failures,
                  "three_way_sha_match_count": sum(r.get("r2_sha_status") == "VERIFIED" for r in verified),
                  "unresolved": unresolved,
                  "operations": {"r2_put": wire.puts, "r2_head": wire.heads,
                                 "r2_get": wire.gets, **db_counts,
                                 "runtime_seconds": round(time.monotonic() - started, 3)},
                  "stop": bool(bad or failures),
                  "next_owner_approval": next_owner_approval(unresolved)}
        print(json.dumps(result, indent=2))
        return 1 if result["stop"] else 0
    finally:
        raw_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
