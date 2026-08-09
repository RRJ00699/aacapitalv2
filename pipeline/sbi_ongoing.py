"""Canonical ongoing SBI lane: temp PDF -> ledger/R2 -> Sonnet -> canonical rows."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

try:
    from .company_identity import load_company_identity_set
    from .r2 import R2DocumentStore
    from .sbi_extraction_run import (
        FAILURE_STATUSES, PriceCard, RESULT_DIR, anthropic_call, cost,
        parse_complete_response, pdf_pages, validate_evidence,
    )
    from .sbi_ingest import ingest_file
    from .sbi_sonnet import (MODEL, PROMPT_VERSION, already_extracted,
                             estimate_input_tokens, write_extraction)
except ImportError:
    from company_identity import load_company_identity_set
    from r2 import R2DocumentStore
    from sbi_extraction_run import (
        FAILURE_STATUSES, PriceCard, RESULT_DIR, anthropic_call, cost,
        parse_complete_response, pdf_pages, validate_evidence,
    )
    from sbi_ingest import ingest_file
    from sbi_sonnet import (MODEL, PROMPT_VERSION, already_extracted,
                            estimate_input_tokens, write_extraction)

RUN_CAP_ENV = "SBI_SONNET_RUN_CAP_USD"
CONFIG_NAMES = ("SBI_SONNET_INPUT_USD_PER_MTOK", "SBI_SONNET_OUTPUT_USD_PER_MTOK",
                "SBI_SONNET_OUTPUT_CAP", RUN_CAP_ENV)


@dataclass(frozen=True)
class OngoingConfiguration:
    status: str
    card: PriceCard | None = None
    error: str | None = None


def ongoing_configuration(environ=None):
    environ = os.environ if environ is None else environ
    present = [name for name in CONFIG_NAMES if environ.get(name)]
    if not present:
        return OngoingConfiguration("SKIPPED_OWNER_NOT_CONFIGURED")
    missing = [name for name in CONFIG_NAMES if not environ.get(name)]
    if missing:
        return OngoingConfiguration("WARNING_CONFIGURATION_ERROR",
                                    error="missing: " + ", ".join(missing))
    try:
        card = PriceCard(Decimal(environ[CONFIG_NAMES[0]]), Decimal(environ[CONFIG_NAMES[1]]),
                         int(environ[CONFIG_NAMES[2]]), Decimal(environ[CONFIG_NAMES[3]]))
    except (ValueError, ArithmeticError):
        return OngoingConfiguration("WARNING_CONFIGURATION_ERROR",
                                    error="values must be positive numbers")
    if min(card.input_usd_per_mtok, card.output_usd_per_mtok,
           card.spend_cap, Decimal(card.output_cap)) <= 0:
        return OngoingConfiguration("WARNING_CONFIGURATION_ERROR",
                                    error="values must be positive numbers")
    return OngoingConfiguration("CONFIGURED", card=card)


def ongoing_price_card(environ=None):
    config = ongoing_configuration(environ)
    if config.status != "CONFIGURED":
        raise ValueError(config.status)
    return config.card


def downloaded_pdfs(directory):
    return sorted(path for path in Path(directory).glob("**/*")
                  if path.is_file() and path.suffix.lower() == ".pdf")


def _ledger_row(conn, doc_id):
    cur = conn.cursor()
    cur.execute("""SELECT id,ipo_id,object_key,sha256 FROM documents
                    WHERE id=%s AND doc_type='sbi' AND object_key IS NOT NULL""", (doc_id,))
    return cur.fetchone()


class CutoverConfigurationError(ValueError):
    pass


def read_cutover(conn):
    """Read and strictly validate platform_config.value TEXT as an aware ISO timestamp."""
    cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key='sbi_ongoing_cutover_at'")
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    raw = str(row[0]).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CutoverConfigurationError("sbi_ongoing_cutover_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise CutoverConfigurationError("sbi_ongoing_cutover_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def pending_sbi_doc_ids(conn, cutover_at):
    """Select only ongoing documents at/after the validated deterministic boundary."""
    if cutover_at is None:
        return []
    cur = conn.cursor()
    cur.execute("""SELECT id FROM documents
                    WHERE doc_type='sbi' AND ipo_id IS NOT NULL
                      AND object_key IS NOT NULL AND fetched_at >= %s
                    ORDER BY fetched_at,id""", (cutover_at,))
    return [row[0] for row in cur.fetchall()]


def persist_manifest(payload, directory=RESULT_DIR):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = directory / f"ongoing-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return str(path)


def _progress(index, total, doc_id, status, itok, otok, note_cost, spent):
    print(f"[{index}/{total}] doc_id={doc_id} status={status} input_tokens={itok} "
          f"output_tokens={otok} note_cost=${note_cost:.6f} "
          f"cumulative_cost=${spent:.6f}", flush=True)


def run_sbi_lane(conn, *, directory, store=None, model_call=anthropic_call,
                 environ=None, dry_run=False, manifest_directory=RESULT_DIR):
    """Run one isolated SBI batch; every input receives a terminal classification."""
    paths = downloaded_pdfs(directory)
    summary = Counter(downloaded=len(paths))
    summary.update({key: 0 for key in (
        "resolved", "unresolved", "newly_ledgered", "already_ledgered",
        "ingest_errors", "extraction_attempted", "extracted", "already_extracted",
        "spend_stopped", "missing_ledger_rows", *FAILURE_STATUSES,
    )})
    records = []
    if dry_run:
        return {"summary": {**summary, "dry_run": True}, "records": records}
    card = ongoing_price_card(environ)
    environ = os.environ if environ is None else environ
    api_key = environ.get("ANTHROPIC_API_KEY")
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
            records.append({"filename": str(path), "doc_id": result["doc_id"],
                "ipo_id": result.get("ipo_id"),
                "status": "NEWLY_LEDGERED" if result["created"] else "ALREADY_LEDGERED"})
        except Exception as exc:
            conn.rollback(); summary["ingest_errors"] += 1
            records.append({"filename": str(path), "status": "INGEST_ERROR",
                            "error": f"{type(exc).__name__}: {exc}"})

    cutover_at = None
    cutover_status = None
    try:
        cutover_at = read_cutover(conn)
    except CutoverConfigurationError as exc:
        cutover_status = "WARNING_INVALID_CUTOVER"
        records.append({"status": cutover_status, "error": str(exc)})
    if cutover_at is None and cutover_status is None:
        cutover_status = "SKIPPED_CUTOVER_NOT_CONFIGURED"
    if cutover_at is not None:
        # The query itself enforces the history/future boundary. Newly ingested IDs
        # are deliberately not trusted outside that boundary.
        doc_ids = pending_sbi_doc_ids(conn, cutover_at)
    else:
        doc_ids = []
    if doc_ids and not api_key:
        cutover_status = "WARNING_CONFIGURATION_ERROR"
        records.append({"status": cutover_status,
                        "error": "ANTHROPIC_API_KEY is required for extraction"})
        doc_ids = []
    doc_ids = list(dict.fromkeys(doc_ids))
    spent = Decimal(0)
    for index, doc_id in enumerate(doc_ids, 1):
        row = _ledger_row(conn, doc_id)
        if not row:
            summary["missing_ledger_rows"] += 1
            summary["MISSING_LEDGER_ROW"] += 1
            records.append({"doc_id": doc_id, "status": "MISSING_LEDGER_ROW"})
            continue
        _, ipo_id, object_key, expected_sha = row
        if already_extracted(conn, doc_id):
            summary["already_extracted"] += 1
            records.append({"doc_id": doc_id, "ipo_id": ipo_id,
                            "status": "ALREADY_EXTRACTED"})
            continue
        try:
            body = store.get_document(object_key)
            if hashlib.sha256(body).hexdigest() != expected_sha:
                raise ValueError("R2 bytes do not match documents.sha256")
            pages = pdf_pages(body)
            estimated_input = estimate_input_tokens(pages)
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
                    write_extraction(conn, ipo_id=ipo_id, doc_id=doc_id,
                                     extraction=parsed, validated=True)
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
    summary["cutover_status"] = cutover_status
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = {"timestamp": timestamp, "model": MODEL,
        "prompt_version": PROMPT_VERSION, "output_cap": card.output_cap,
        "run_spend_cap": str(card.spend_cap),
        "cutover_at": cutover_at.isoformat() if cutover_at else None,
        "cutover_status": cutover_status, "summary": dict(summary),
        "records": records, "actual_sbi_spend": summary["actual_sbi_spend"],
        "spend_stopped": bool(summary["spend_stopped"])}
    manifest_path = persist_manifest(manifest, manifest_directory)
    return {"summary": dict(summary), "records": records,
            "manifest_path": manifest_path, "cutover_status": cutover_status}
