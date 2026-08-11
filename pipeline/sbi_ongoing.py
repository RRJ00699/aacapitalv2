#!/usr/bin/env python3
"""Canonical ongoing SBI lane: local download -> immutable ledger/R2 -> Sonnet.

The model stage reads the PDF back from ``documents.object_key``.  Consequently a
successfully ledgered temporary download is never an extraction dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import urllib.request

import pymupdf

try:
    from .r2 import R2DocumentStore
    from .sbi_ingest import ingest_file
    from .sbi_sonnet import extract, write_extraction
except ImportError:
    from r2 import R2DocumentStore
    from sbi_ingest import ingest_file
    from sbi_sonnet import extract, write_extraction

SCHEDULED_LIMIT = 10
HISTORICAL_LIMIT = 40
LOCK_KEY = 83249021


def _normalise_evidence(value):
    """Existing fail-closed comparison: whitespace/case normalization, no fuzzy match."""
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def validate_evidence(extraction, pages):
    """Drop individual unsupported items while preserving exactly evidenced siblings."""
    valid = {"claims": [], "scalar_facts": []}
    dropped = []
    page_text = {int(page["page_number"]): _normalise_evidence(page["text"]) for page in pages}
    for collection in ("claims", "scalar_facts"):
        for position, item in enumerate(extraction.get(collection, [])):
            page = item.get("page_number")
            excerpt = _normalise_evidence(item.get("excerpt"))
            reason = None
            if page not in page_text:
                reason = "page_number_not_found"
            elif not excerpt or excerpt not in page_text[page]:
                reason = "exact_normalized_excerpt_mismatch"
            if reason:
                dropped.append({"collection": collection, "position": position,
                    "reason": reason, "page_number": page, "excerpt": item.get("excerpt")})
            else:
                valid[collection].append(item)
    return valid, dropped


def pending_documents(conn, limit):
    """Use one pending query, prioritising the newest fetched SBI notes."""
    cur = conn.cursor()
    cur.execute("""SELECT d.id,d.ipo_id,d.object_key
        FROM documents d
        WHERE d.doc_type='sbi' AND d.object_key IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM insights i WHERE i.doc_id=d.id
            AND i.source_type='SBI' AND i.model='claude-sonnet-4-6'
            AND i.prompt_version='sbi-v1')
        ORDER BY d.fetched_at DESC NULLS LAST,d.id DESC LIMIT %s""", (limit,))
    rows = cur.fetchall(); cur.close()
    return rows


def _pages(pdf_bytes):
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [{"page_number": number + 1, "text": page.get_text()}
                for number, page in enumerate(doc)]


def _safe_cleanup(conn):
    """Best-effort cleanup must never replace the processing exception."""
    if getattr(conn, "closed", False):
        return
    try:
        cur = conn.cursor(); cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,)); cur.close()
        conn.commit()
    except Exception:
        # A dead PostgreSQL session releases its advisory locks itself.
        pass


def run_worker(conn, *, limit, model_client, store=None):
    store = store or R2DocumentStore()
    reports = []
    cur = conn.cursor(); cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
    locked = cur.fetchone()[0]; cur.close()
    if not locked: return [{"status": "LOCKED"}]
    try:
        for doc_id, ipo_id, object_key in pending_documents(conn, limit):
            try:
                pages = _pages(store.get_document(object_key))
                proposed = extract(doc_id=doc_id, pages=pages, model_client=model_client)
                valid, dropped = validate_evidence(proposed, pages)
                if not valid["claims"] and not valid["scalar_facts"]:
                    reports.append({"doc_id": doc_id, "status": "EVIDENCE_REJECTED",
                                    "dropped_items": dropped})
                    continue
                write_extraction(conn, ipo_id=ipo_id, doc_id=doc_id, extraction=valid)
                reports.append({"doc_id": doc_id,
                    "status": "EXTRACTED_WITH_DROPS" if dropped else "EXTRACTED",
                    "dropped_items": dropped})
            except Exception:
                conn.rollback()
                raise
        return reports
    finally:
        _safe_cleanup(conn)


def _sonnet_configured(env):
    required = ("ANTHROPIC_API_KEY", "SBI_SONNET_INPUT_PRICE_PER_MTOK",
                "SBI_SONNET_OUTPUT_PRICE_PER_MTOK", "SBI_SONNET_RUN_CAP_USD")
    return env.get("SBI_SONNET_OWNER_APPROVED") == "YES" and all(env.get(k) for k in required)


def anthropic_model_client(env):
    """Construct the reviewed paid client only after the complete price gate passes."""
    spent = 0.0
    input_rate = float(env["SBI_SONNET_INPUT_PRICE_PER_MTOK"])
    output_rate = float(env["SBI_SONNET_OUTPUT_PRICE_PER_MTOK"])
    cap = float(env["SBI_SONNET_RUN_CAP_USD"])

    def call(*, model, system, pages, **_kwargs):
        nonlocal spent
        if spent >= cap:
            raise RuntimeError("SBI Sonnet run cap reached")
        prompt = "\n\n".join(f"=== PAGE {p['page_number']} ===\n{p['text']}" for p in pages)
        body = json.dumps({"model": model, "max_tokens": 5000, "system": system,
            "messages": [{"role": "user", "content": prompt}]}).encode()
        request = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
            headers={"content-type":"application/json", "x-api-key":env["ANTHROPIC_API_KEY"],
                     "anthropic-version":"2023-06-01"})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
        usage = payload.get("usage", {})
        spent += (usage.get("input_tokens", 0) * input_rate
                  + usage.get("output_tokens", 0) * output_rate) / 1_000_000
        if spent > cap:
            raise RuntimeError("SBI Sonnet response exceeded owner run cap; result rejected")
        return "".join(block.get("text", "") for block in payload.get("content", [])
                       if block.get("type") == "text")
    return call


def run_sbi_lane(conn, directory, *, limit=SCHEDULED_LIMIT, env=None, store=None,
                 model_client=None):
    """Always ingest; run the same bounded worker only after complete owner approval."""
    env = os.environ if env is None else env
    store = store or R2DocumentStore()
    ingested = []
    for path in sorted(pathlib.Path(directory).glob("*.pdf")):
        ingested.append(ingest_file(conn, path, owner_approved=True, store=store,
                                    retain_source=False))
    extraction = []
    if _sonnet_configured(env):
        if model_client is None:
            raise RuntimeError("owner-approved Sonnet run requires an explicit model client")
        extraction = run_worker(conn, limit=limit, model_client=model_client, store=store)
    return {"ingest": ingested, "sonnet_approved": _sonnet_configured(env),
            "extraction": extraction, "worker_limit": limit}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--directory", required=True); ap.add_argument("--limit", type=int, default=SCHEDULED_LIMIT)
    args = ap.parse_args(argv)
    if not 1 <= args.limit <= HISTORICAL_LIMIT: ap.error("--limit must be between 1 and 40")
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        # The CLI intentionally cannot silently construct a paid client. The scheduled
        # job performs ingest without it; owner extraction supplies the reviewed client.
        client = anthropic_model_client(os.environ) if _sonnet_configured(os.environ) else None
        report = run_sbi_lane(conn, args.directory, limit=args.limit, model_client=client)
        print(json.dumps(report, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
