#!/usr/bin/env python3
"""Owner-authorized, spend-bounded Sonnet extraction of SHA-verified SBI notes."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time
import urllib.error
import urllib.request
from collections import Counter
from decimal import Decimal

import pymupdf

try:
    from .company_identity import load_company_identity_set
    from .r2 import R2DocumentStore
    from .sbi_bounded_ingest import unresolved_report
    from .sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote
    from .sbi_sonnet import MODEL, PROMPT_VERSION, SYSTEM_PROMPT, already_extracted, parse_extraction, write_extraction
except ImportError:
    from company_identity import load_company_identity_set
    from r2 import R2DocumentStore
    from sbi_bounded_ingest import unresolved_report
    from sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote
    from sbi_sonnet import MODEL, PROMPT_VERSION, SYSTEM_PROMPT, already_extracted, parse_extraction, write_extraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_CAP = 1000
SPEND_CAP = Decimal("7.00")
# Current configured standard Anthropic API price card for Claude Sonnet 4.6.
INPUT_USD_PER_MTOK = Decimal("3.00")
OUTPUT_USD_PER_MTOK = Decimal("15.00")
EXPECTED_DOCUMENTS = 198
EXPECTED_INPUT_TOKENS = 985_679
RESULT_DIR = ROOT / "artifacts" / "sbi-extraction"


class ModelError(RuntimeError):
    pass


def cost(input_tokens: int, output_tokens: int) -> Decimal:
    return ((Decimal(input_tokens) * INPUT_USD_PER_MTOK
             + Decimal(output_tokens) * OUTPUT_USD_PER_MTOK) / Decimal(1_000_000))


def print_cost_checkpoint():
    input_est = cost(EXPECTED_INPUT_TOKENS, 0)
    output_est = cost(0, EXPECTED_DOCUMENTS * OUTPUT_CAP)
    total = input_est + output_est
    print(f"documents to extract = {EXPECTED_DOCUMENTS}")
    print(f"estimated input tokens = {EXPECTED_INPUT_TOKENS}")
    print(f"output cap = {OUTPUT_CAP}/note")
    print(f"maximum possible output tokens = {EXPECTED_DOCUMENTS * OUTPUT_CAP}")
    print(f"input cost estimate = ${input_est:.6f}")
    print(f"maximum output cost = ${output_est:.6f}")
    print(f"maximum total estimate = ${total:.6f}", flush=True)
    if total > SPEND_CAP:
        raise SystemExit(f"ABORT: ${total:.6f} estimate exceeds ${SPEND_CAP:.2f} cap")


def pdf_pages(body: bytes) -> list[dict]:
    with pymupdf.open(stream=body, filetype="pdf") as doc:
        return [{"page_number": i + 1, "text": page.get_text()} for i, page in enumerate(doc)]


def validate_evidence(extraction: dict, pages: list[dict]):
    """Reject the whole note unless every excerpt occurs on its asserted page."""
    page_text = {page["page_number"]: " ".join(page["text"].split()) for page in pages}
    for item in extraction["claims"] + extraction["scalar_facts"]:
        excerpt = " ".join(item["excerpt"].split())
        if not excerpt or excerpt not in page_text.get(item["page_number"], ""):
            raise ValueError(f"unsupported excerpt on page {item['page_number']}")


def anthropic_call(*, pages: list[dict], api_key: str):
    page_text = "\n\n".join(f"--- PAGE {p['page_number']} ---\n{p['text']}" for p in pages)
    payload = json.dumps({"model": MODEL, "max_tokens": OUTPUT_CAP,
                          "system": SYSTEM_PROMPT,
                          "messages": [{"role": "user", "content": page_text}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload,
        headers={"content-type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ModelError(str(exc)) from exc
    if result.get("type") == "error" or not result.get("content"):
        raise ModelError(json.dumps(result)[:1000])
    text = "".join(block.get("text", "") for block in result["content"] if block.get("type") == "text")
    usage = result.get("usage") or {}
    return text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def deterministic_holdout_report(rows, identity_rows):
    """Review only exact evidence already loaded from the identity spine."""
    advisory = unresolved_report(rows, identity_rows)
    by_name = {item[2]: item for item in identity_rows}
    output = []
    for item in advisory:
        candidates = []
        for name in item["closest_name_suggestions_advisory_only"]:
            row = by_name.get(name)
            if row:
                candidates.append({"ipo_id": row[0], "name": row[2], "isin": row[1]})
        source = next(r for r in rows if r["local_path"] == item["filename"])
        output.append({"filename": item["filename"], "local_sha": source["local_sha256"],
            "canonical_filename_company": pathlib.Path(item["filename"]).stem.rsplit("_IPO Note", 1)[0],
            "current_advisory_suggestions": item["closest_name_suggestions_advisory_only"],
            "ambiguity_exists": item["group"] == "AMBIGUOUS", "candidates": candidates,
            "group": item["group"], "deterministically_resolved": False})
    return output


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-approved", action="store_true")
    ap.add_argument("--directory", default=str(ROOT / "data" / "research_notes"))
    args = ap.parse_args(argv)
    if not args.owner_approved or os.getenv("SBI_SONNET_OWNER_APPROVED") != "YES":
        raise SystemExit("requires --owner-approved and SBI_SONNET_OWNER_APPROVED=YES")
    required = ["DATABASE_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "R2_DOCUMENT_BUCKET", "ANTHROPIC_API_KEY"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit("missing credentials: " + ", ".join(missing))
    print_cost_checkpoint()

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    store = R2DocumentStore()
    counter, records, totals = OperationCounter(), [], Counter()
    actual_cost = Decimal("0")
    try:
        cur = conn.cursor(); identity_rows = load_company_identity_set(cur); cur.close()
        rows = [verify_remote(row, conn, store, counter, identity_rows)
                for row in local_inventory(args.directory)]
        eligible = [r for r in rows if r.get("ipo_id") is not None
                    and r.get("documents_object_key") and r.get("r2_sha_status") == "VERIFIED"
                    and r.get("extraction_tuple") is None]
        if len(eligible) != EXPECTED_DOCUMENTS:
            raise SystemExit(f"ABORT: eligible documents={len(eligible)}, expected {EXPECTED_DOCUMENTS}")
        for row in eligible:
            base = {"doc_id": row["documents_id"], "ipo_id": row["ipo_id"],
                    "model": MODEL, "prompt_version": PROMPT_VERSION,
                    "input_tokens": 0, "output_tokens": 0, "actual_cost": "0.000000"}
            if already_extracted(conn, row["documents_id"]):
                records.append({**base, "status": "ALREADY_EXTRACTED", "error": None})
                totals["already_extracted"] += 1
                continue
            # The conservative projection uses the approved preflight average plus maximum output.
            try:
                body = store.get_document(row["documents_object_key"])
                pages = pdf_pages(body)
                estimated_input = ((sum(len(p["text"]) for p in pages) + 3) // 4
                                   + (len(SYSTEM_PROMPT) + 3) // 4)
                if actual_cost + cost(estimated_input, OUTPUT_CAP) > SPEND_CAP:
                    print("STOP: next projected call would exceed $7.00", flush=True); break
                totals["calls"] += 1
                response, itok, otok = anthropic_call(pages=pages, api_key=os.environ["ANTHROPIC_API_KEY"])
                note_cost = cost(itok, otok); actual_cost += note_cost
                base.update(input_tokens=itok, output_tokens=otok, actual_cost=f"{note_cost:.6f}")
                totals["input_tokens"] += itok; totals["output_tokens"] += otok
                try:
                    parsed = parse_extraction(response, doc_id=row["documents_id"])
                except Exception as exc:
                    records.append({**base, "status": "PARSE_ERROR", "error": f"{type(exc).__name__}: {exc}"})
                    totals["PARSE_ERROR"] += 1; continue
                try:
                    validate_evidence(parsed, pages)
                except Exception as exc:
                    records.append({**base, "status": "EVIDENCE_REJECTED", "error": f"{type(exc).__name__}: {exc}"})
                    totals["EVIDENCE_REJECTED"] += 1; continue
                try:
                    write_extraction(conn, ipo_id=row["ipo_id"], doc_id=row["documents_id"], extraction=parsed)
                except Exception as exc:
                    conn.rollback(); records.append({**base, "status": "WRITE_ERROR", "error": f"{type(exc).__name__}: {exc}"})
                    totals["WRITE_ERROR"] += 1; continue
                records.append({**base, "status": "EXTRACTED", "error": None}); totals["successes"] += 1
            except Exception as exc:
                conn.rollback(); records.append({**base, "status": "MODEL_ERROR", "error": f"{type(exc).__name__}: {exc}"})
                totals["MODEL_ERROR"] += 1

        verified = [verify_remote(row, conn, store, OperationCounter(), identity_rows)
                    for row in local_inventory(args.directory)]
        holdouts = deterministic_holdout_report(verified, identity_rows)
        result = {"records": records, "summary": {"calls": totals["calls"],
            "input_tokens": totals["input_tokens"], "output_tokens": totals["output_tokens"],
            "actual_cost": f"{actual_cost:.6f}", "successes": totals["successes"],
            "failures": sum(totals[k] for k in ("MODEL_ERROR", "PARSE_ERROR", "WRITE_ERROR", "EVIDENCE_REJECTED")),
            "failures_by_category": {k: totals[k] for k in ("MODEL_ERROR", "PARSE_ERROR", "WRITE_ERROR", "EVIDENCE_REJECTED")},
            "already_extracted": totals["already_extracted"],
            "EXTRACTION_MISSING": aggregate(verified)["EXTRACTION_MISSING"],
            "holdout_deterministically_resolved": sum(x["deterministically_resolved"] for x in holdouts),
            "remaining_unresolved": len(holdouts)}, "holdouts": holdouts}
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        target = RESULT_DIR / f"run-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.json"
        target.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result["summary"], indent=2)); print(f"manifest = {target.relative_to(ROOT)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
