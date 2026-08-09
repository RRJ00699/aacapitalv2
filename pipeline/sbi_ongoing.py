"""Canonical ongoing SBI lane: temp PDF -> ledger/R2 -> Sonnet -> canonical rows."""
from __future__ import annotations

import hashlib
import os
from collections import Counter
from decimal import Decimal
from pathlib import Path

try:
    from .company_identity import load_company_identity_set
    from .r2 import R2DocumentStore
    from .sbi_extraction_run import (
        FAILURE_STATUSES, PriceCard, anthropic_call, cost,
        parse_complete_response, pdf_pages, validate_evidence,
    )
    from .sbi_ingest import ingest_file
    from .sbi_sonnet import MODEL, PROMPT_VERSION, already_extracted, write_extraction
except ImportError:
    from company_identity import load_company_identity_set
    from r2 import R2DocumentStore
    from sbi_extraction_run import (
        FAILURE_STATUSES, PriceCard, anthropic_call, cost,
        parse_complete_response, pdf_pages, validate_evidence,
    )
    from sbi_ingest import ingest_file
    from sbi_sonnet import MODEL, PROMPT_VERSION, already_extracted, write_extraction

RUN_CAP_ENV = "SBI_SONNET_RUN_CAP_USD"


def ongoing_price_card(environ=None):
    environ = os.environ if environ is None else environ
    required = ("SBI_SONNET_INPUT_USD_PER_MTOK", "SBI_SONNET_OUTPUT_USD_PER_MTOK",
                "SBI_SONNET_OUTPUT_CAP", RUN_CAP_ENV)
    missing = [name for name in required if not environ.get(name)]
    if missing:
        raise SystemExit("ongoing SBI owner price card required: " + ", ".join(missing))
    try:
        card = PriceCard(Decimal(environ[required[0]]), Decimal(environ[required[1]]),
                         int(environ[required[2]]), Decimal(environ[required[3]]))
    except (ValueError, ArithmeticError) as exc:
        raise SystemExit("ongoing SBI owner price card values must be positive numbers") from exc
    if min(card.input_usd_per_mtok, card.output_usd_per_mtok,
           card.spend_cap, Decimal(card.output_cap)) <= 0:
        raise SystemExit("ongoing SBI owner price card values must be positive numbers")
    return card


def downloaded_pdfs(directory):
    return sorted(path for path in Path(directory).glob("**/*")
                  if path.is_file() and path.suffix.lower() == ".pdf")


def _ledger_row(conn, doc_id):
    cur = conn.cursor()
    cur.execute("""SELECT id,ipo_id,object_key,sha256 FROM documents
                    WHERE id=%s AND doc_type='sbi' AND object_key IS NOT NULL""", (doc_id,))
    return cur.fetchone()


def pending_sbi_doc_ids(conn):
    """Select ledgered SBI documents; tuple idempotency filters them before calls."""
    cur = conn.cursor()
    cur.execute("""SELECT id FROM documents
                    WHERE doc_type='sbi' AND ipo_id IS NOT NULL
                      AND object_key IS NOT NULL ORDER BY fetched_at,id""")
    return [row[0] for row in cur.fetchall()]


def _progress(index, total, doc_id, status, itok, otok, note_cost, spent):
    print(f"[{index}/{total}] doc_id={doc_id} status={status} input_tokens={itok} "
          f"output_tokens={otok} note_cost=${note_cost:.6f} "
          f"cumulative_cost=${spent:.6f}", flush=True)


def run_sbi_lane(conn, *, directory, store=None, model_call=anthropic_call,
                 environ=None, dry_run=False):
    """Run one isolated SBI batch; every input receives a terminal classification."""
    paths = downloaded_pdfs(directory)
    summary = Counter(downloaded=len(paths))
    summary.update({key: 0 for key in (
        "resolved", "unresolved", "newly_ledgered", "already_ledgered",
        "ingest_errors", "extraction_attempted", "extracted", "already_extracted",
        "spend_stopped", *FAILURE_STATUSES,
    )})
    records = []
    if dry_run:
        return {"summary": {**summary, "dry_run": True}, "records": records}
    card = ongoing_price_card(environ)
    environ = os.environ if environ is None else environ
    api_key = environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is required for the ongoing SBI lane")
    store = store or R2DocumentStore()
    cur = conn.cursor(); identity_rows = load_company_identity_set(cur); cur.close()
    doc_ids = []
    for path in paths:
        try:
            result = ingest_file(conn, path, store=store, owner_approved=True,
                                 retain_source=False, identity_rows=identity_rows)
            if result["status"] == "UNRESOLVED":
                summary["unresolved"] += 1
                records.append({"filename": str(path), "status": "UNRESOLVED",
                    "reason": result["identity_resolution"],
                    "ambiguity_count": result["ambiguous_count"]})
                continue
            summary["resolved"] += 1
            summary["newly_ledgered" if result["created"] else "already_ledgered"] += 1
            doc_ids.append(result["doc_id"])
        except Exception as exc:
            conn.rollback(); summary["ingest_errors"] += 1
            records.append({"filename": str(path), "status": "INGEST_ERROR",
                            "error": f"{type(exc).__name__}: {exc}"})

    # Include prior storage-success/extraction-failure documents. Completed tuples
    # make zero calls; pending objects retry without requiring another download.
    doc_ids.extend(pending_sbi_doc_ids(conn))
    doc_ids = list(dict.fromkeys(doc_ids))
    spent = Decimal(0)
    for index, doc_id in enumerate(doc_ids, 1):
        row = _ledger_row(conn, doc_id)
        if not row:
            summary["write_errors"] += 1
            continue
        _, ipo_id, object_key, expected_sha = row
        if already_extracted(conn, doc_id):
            summary["already_extracted"] += 1
            continue
        try:
            body = store.get_document(object_key)
            if hashlib.sha256(body).hexdigest() != expected_sha:
                raise ValueError("R2 bytes do not match documents.sha256")
            pages = pdf_pages(body)
            estimated_input = ((sum(len(page["text"]) for page in pages) + 3) // 4)
            if spent + cost(estimated_input, card.output_cap, card) > card.spend_cap:
                summary["spend_stopped"] = 1
                break
            summary["extraction_attempted"] += 1
            text, itok, otok, stop_reason = model_call(
                pages=pages, api_key=api_key, output_cap=card.output_cap)
            note_cost = cost(itok, otok, card); spent += note_cost
            try:
                status, parsed = parse_complete_response(
                    text, doc_id=doc_id, stop_reason=stop_reason)
            except Exception as exc:
                summary["PARSE_ERROR"] += 1
                records.append({"doc_id": doc_id, "ipo_id": ipo_id,
                    "status": "PARSE_ERROR", "input_tokens": itok,
                    "output_tokens": otok, "actual_cost": f"{note_cost:.6f}",
                    "error": f"{type(exc).__name__}: {exc}"})
                _progress(index, len(doc_ids), doc_id, "PARSE_ERROR", itok, otok,
                          note_cost, spent)
                continue
            if status == "TRUNCATED":
                summary["TRUNCATED"] += 1
            else:
                try:
                    validate_evidence(parsed, pages)
                except Exception as exc:
                    summary["EVIDENCE_REJECTED"] += 1
                    records.append({"doc_id": doc_id, "ipo_id": ipo_id,
                        "status": "EVIDENCE_REJECTED", "input_tokens": itok,
                        "output_tokens": otok, "actual_cost": f"{note_cost:.6f}",
                        "error": f"{type(exc).__name__}: {exc}"})
                    _progress(index, len(doc_ids), doc_id, "EVIDENCE_REJECTED", itok,
                              otok, note_cost, spent)
                    continue
                try:
                    write_extraction(conn, ipo_id=ipo_id, doc_id=doc_id, extraction=parsed)
                except Exception as exc:
                    conn.rollback(); summary["WRITE_ERROR"] += 1
                    records.append({"doc_id": doc_id, "ipo_id": ipo_id,
                        "status": "WRITE_ERROR", "input_tokens": itok,
                        "output_tokens": otok, "actual_cost": f"{note_cost:.6f}",
                        "error": f"{type(exc).__name__}: {exc}"})
                    _progress(index, len(doc_ids), doc_id, "WRITE_ERROR", itok, otok,
                              note_cost, spent)
                    continue
                status = "EXTRACTED"; summary["extracted"] += 1
            records.append({"doc_id": doc_id, "ipo_id": ipo_id, "status": status,
                "model": MODEL, "prompt_version": PROMPT_VERSION,
                "input_tokens": itok, "output_tokens": otok,
                "actual_cost": f"{note_cost:.6f}", "stop_reason": stop_reason})
            _progress(index, len(doc_ids), doc_id, status, itok, otok, note_cost, spent)
        except Exception as exc:
            conn.rollback()
            summary["MODEL_ERROR"] += 1
            records.append({"doc_id": doc_id, "ipo_id": ipo_id, "status": "MODEL_ERROR",
                            "error": f"{type(exc).__name__}: {exc}"})
            _progress(index, len(doc_ids), doc_id, "MODEL_ERROR", 0, 0,
                      Decimal(0), spent)
            continue
    summary["actual_sbi_spend"] = f"{spent:.6f}"
    summary["truncated"] = summary["TRUNCATED"]
    summary["parse_errors"] = summary["PARSE_ERROR"]
    summary["evidence_rejected"] = summary["EVIDENCE_REJECTED"]
    summary["write_errors"] = summary["WRITE_ERROR"]
    summary["model_errors"] = summary["MODEL_ERROR"]
    return {"summary": dict(summary), "records": records}
