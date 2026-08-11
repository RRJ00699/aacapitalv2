"""SBI cron lane: ingest temporary downloads, then run the canonical DB worker."""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

try:
    from .company_identity import load_company_identity_set
    from .r2 import R2DocumentStore
    from .sbi_extraction_run import (
        RESULT_DIR, anthropic_call, count_tokens_call, persist_manifest,
        run_pending_worker, worker_configuration,
    )
    from .sbi_ingest import ingest_file
except ImportError:
    from company_identity import load_company_identity_set
    from r2 import R2DocumentStore
    from sbi_extraction_run import (
        RESULT_DIR, anthropic_call, count_tokens_call, persist_manifest,
        run_pending_worker, worker_configuration,
    )
    from sbi_ingest import ingest_file


def ongoing_configuration(environ=None):
    """Compatibility name used by cron; there is only one worker configuration."""
    return worker_configuration(environ)


def downloaded_pdfs(directory):
    return sorted(path for path in Path(directory).glob("**/*")
                  if path.is_file() and path.suffix.lower() == ".pdf")


def run_sbi_lane(conn, *, directory, store=None, model_call=anthropic_call,
                 token_counter=count_tokens_call, environ=None, dry_run=False,
                 manifest_directory=RESULT_DIR):
    """Ingest new PDFs and invoke the same ledger-driven worker for all pending SBI docs."""
    paths = downloaded_pdfs(directory)
    ingest_summary = Counter(downloaded=len(paths), resolved=0, unresolved=0,
                             newly_ledgered=0, already_ledgered=0, ingest_errors=0)
    ingest_records = []
    if dry_run:
        return {"summary": {**ingest_summary, "dry_run": True}, "records": []}
    environ = os.environ if environ is None else environ
    store = store or R2DocumentStore()
    cur = conn.cursor()
    identity_rows = load_company_identity_set(cur)
    close = getattr(cur, "close", None)
    if close:
        close()
    for path in paths:
        try:
            result = ingest_file(conn, path, store=store, owner_approved=True,
                                 retain_source=False, identity_rows=identity_rows)
            if result["status"] in {"UNRESOLVED", "INVALID_REVIEWED_OVERRIDE"}:
                ingest_summary["unresolved"] += 1
                ingest_records.append({"filename": str(path), **result})
                continue
            if result["status"] == "SKIPPED_REVIEWED_EXCLUSION":
                ingest_records.append({"filename": str(path), **result})
                continue
            ingest_summary["resolved"] += 1
            ingest_summary["newly_ledgered" if result["created"] else "already_ledgered"] += 1
            ingest_records.append({"filename": str(path), **result})
        except Exception as exc:
            conn.rollback()
            ingest_summary["ingest_errors"] += 1
            ingest_records.append({"filename": str(path), "status": "INGEST_ERROR",
                                   "error": f"{type(exc).__name__}: {exc}"})

    config = worker_configuration(environ)
    if (config.status == "CONFIGURED" and model_call is anthropic_call
            and not environ.get("ANTHROPIC_API_KEY")):
        worker = {"summary": {"extraction_status": "SKIPPED_OWNER_NOT_CONFIGURED",
                              "configuration_error": "ANTHROPIC_API_KEY is absent",
                              "selected": 0, "actual_sbi_spend": "0.000000"}, "records": []}
    elif config.status == "CONFIGURED":
        worker = run_pending_worker(
            conn, store=store, card=config.card, environ=environ,
            model_call=model_call, token_counter=token_counter)
        worker["summary"].setdefault("extraction_status", "CONFIGURED")
    else:
        worker = {"summary": {
            "extraction_status": config.status,
            "selected": 0,
            "actual_sbi_spend": "0.000000",
        }, "records": []}
        if config.error:
            worker["summary"]["configuration_error"] = config.error
    summary = {**ingest_summary, **worker["summary"]}
    payload = {"summary": summary, "records": ingest_records + worker["records"]}
    manifest_path = persist_manifest(payload, manifest_directory)
    return {**payload, "manifest_path": manifest_path}
