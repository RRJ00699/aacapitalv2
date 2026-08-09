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
from dataclasses import dataclass
from decimal import Decimal

import pymupdf

try:
    from .company_identity import load_company_identity_set
    from .r2 import R2DocumentStore
    from .sbi_bounded_ingest import unresolved_report
    from .sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote
    from .sbi_sonnet import MODEL, PROMPT_VERSION, SYSTEM_PROMPT, already_extracted, estimate_input_tokens, parse_extraction, write_extraction
except ImportError:
    from company_identity import load_company_identity_set
    from r2 import R2DocumentStore
    from sbi_bounded_ingest import unresolved_report
    from sbi_migration_verify import OperationCounter, aggregate, local_inventory, verify_remote
    from sbi_sonnet import MODEL, PROMPT_VERSION, SYSTEM_PROMPT, already_extracted, estimate_input_tokens, parse_extraction, write_extraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
# OWNER-APPROVED PRICE CARD REQUIRED. Paid-lane values have no code defaults.
EXPECTED_DOCUMENTS = 198
PRE_V11_INPUT_TOKENS = 985_679
PRE_V11_SYSTEM_PROMPT_TOKENS = 196
EXPECTED_INPUT_TOKENS = (PRE_V11_INPUT_TOKENS + EXPECTED_DOCUMENTS
                         * (((len(SYSTEM_PROMPT) + 3) // 4) - PRE_V11_SYSTEM_PROMPT_TOKENS))
RESULT_DIR = ROOT / "artifacts" / "sbi-extraction"
PRICE_ENV = {
    "input_usd_per_mtok": "SBI_SONNET_INPUT_USD_PER_MTOK",
    "output_usd_per_mtok": "SBI_SONNET_OUTPUT_USD_PER_MTOK",
    "output_cap": "SBI_SONNET_OUTPUT_CAP",
    "spend_cap": "SBI_SONNET_SPEND_CAP_USD",
}


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class PriceCard:
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    output_cap: int
    spend_cap: Decimal


def load_owner_price_card(environ=None) -> PriceCard:
    environ = os.environ if environ is None else environ
    missing = [name for name in PRICE_ENV.values() if not environ.get(name)]
    if missing:
        raise SystemExit("OWNER-APPROVED PRICE CARD REQUIRED: " + ", ".join(missing))
    try:
        card = PriceCard(Decimal(environ[PRICE_ENV["input_usd_per_mtok"]]),
                         Decimal(environ[PRICE_ENV["output_usd_per_mtok"]]),
                         int(environ[PRICE_ENV["output_cap"]]),
                         Decimal(environ[PRICE_ENV["spend_cap"]]))
    except (ValueError, ArithmeticError) as exc:
        raise SystemExit("OWNER-APPROVED PRICE CARD values must be positive numbers") from exc
    if min(card.input_usd_per_mtok, card.output_usd_per_mtok,
           card.spend_cap, Decimal(card.output_cap)) <= 0:
        raise SystemExit("OWNER-APPROVED PRICE CARD values must be positive numbers")
    return card


def cost(input_tokens: int, output_tokens: int, card: PriceCard) -> Decimal:
    return ((Decimal(input_tokens) * card.input_usd_per_mtok
             + Decimal(output_tokens) * card.output_usd_per_mtok) / Decimal(1_000_000))


def print_cost_checkpoint(card: PriceCard):
    input_est = cost(EXPECTED_INPUT_TOKENS, 0, card)
    output_est = cost(0, EXPECTED_DOCUMENTS * card.output_cap, card)
    total = input_est + output_est
    print(f"documents to extract = {EXPECTED_DOCUMENTS}")
    print(f"estimated input tokens = {EXPECTED_INPUT_TOKENS}")
    print(f"output cap = {card.output_cap}/note")
    print(f"maximum possible output tokens = {EXPECTED_DOCUMENTS * card.output_cap}")
    print(f"input cost estimate = ${input_est:.6f}")
    print(f"maximum output cost = ${output_est:.6f}")
    print(f"maximum total estimate = ${total:.6f}", flush=True)
    if total > card.spend_cap:
        raise SystemExit(f"ABORT: ${total:.6f} estimate exceeds ${card.spend_cap:.2f} cap")


def print_remaining_cost_checkpoint(card: PriceCard, remaining: int):
    """Use current work count and the full input estimate as a safe upper bound."""
    maximum = (cost(EXPECTED_INPUT_TOKENS, 0, card)
               + cost(0, remaining * card.output_cap, card))
    print(f"remaining eligible maximum cost (conservative) = ${maximum:.6f}", flush=True)
    if maximum > card.spend_cap:
        raise SystemExit(f"ABORT: remaining maximum ${maximum:.6f} exceeds ${card.spend_cap:.2f} cap")


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


def anthropic_call(*, pages: list[dict], api_key: str, output_cap: int):
    page_text = "\n\n".join(f"--- PAGE {p['page_number']} ---\n{p['text']}" for p in pages)
    payload = json.dumps({"model": MODEL, "max_tokens": output_cap,
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
    return (text, int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)), result.get("stop_reason"))


def eligible_scope(rows, limit=None):
    eligible = [r for r in rows if r.get("ipo_id") is not None
                and r.get("documents_object_key") and r.get("r2_sha_status") == "VERIFIED"
                and r.get("extraction_tuple") is None]
    if len(eligible) > EXPECTED_DOCUMENTS:
        raise SystemExit(f"ABORT scope creep: eligible documents={len(eligible)}, expected maximum={EXPECTED_DOCUMENTS}")
    return eligible if limit is None else eligible[:limit]


def print_progress(index, total, row, record, cumulative_cost):
    print(f"[{index}/{total}] filename={row['local_path']} status={record['status']} "
          f"input_tokens={record['input_tokens']} output_tokens={record['output_tokens']} "
          f"note_cost=${record['actual_cost']} cumulative_cost=${cumulative_cost:.6f}", flush=True)


def parse_complete_response(response, *, doc_id, stop_reason, parser=parse_extraction):
    """Keep capped output out of parsing and all downstream write paths."""
    if stop_reason == "max_tokens":
        return "TRUNCATED", None
    return "COMPLETE", parser(response, doc_id=doc_id)


FAILURE_STATUSES = ("MODEL_ERROR", "PARSE_ERROR", "WRITE_ERROR",
                    "EVIDENCE_REJECTED", "TRUNCATED", "MISSING_LEDGER_ROW")


def full_run_approval_blocked(totals):
    return bool(any(totals[status] for status in FAILURE_STATUSES)
                or totals["successes"] != totals["calls"]
                or totals["spend_stopped"]
                or (totals["selected"] and totals["calls"] < totals["selected"]))


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
        source = next((r for r in rows if r.get("local_path") == item["filename"]), None)
        deterministic = bool(source and source.get("ipo_id") is not None and
                             source.get("identity_resolution") != "AMBIGUOUS")
        output.append({"filename": item["filename"],
            "local_sha": source.get("local_sha256") if source else None,
            "canonical_filename_company": pathlib.Path(item["filename"]).stem.rsplit("_IPO Note", 1)[0],
            "current_advisory_suggestions": item["closest_name_suggestions_advisory_only"],
            "ambiguity_exists": item["group"] == "AMBIGUOUS", "candidates": candidates,
            "group": item["group"], "deterministically_resolved": deterministic})
    return output


def maybe_write_cutover(conn, *, limit, verified, totals):
    """Create the immutable history/future boundary only after a clean full run."""
    missing = aggregate(verified)["EXTRACTION_MISSING"]
    if (limit is not None or missing != 0 or full_run_approval_blocked(totals)
            or totals["spend_stopped"]):
        return None
    doc_ids = [row["documents_id"] for row in verified
               if row.get("r2_sha_status") == "VERIFIED" and row.get("documents_id")]
    if len(doc_ids) != EXPECTED_DOCUMENTS:
        return None
    cur = conn.cursor()
    cur.execute("SELECT max(fetched_at) FROM documents WHERE id = ANY(%s)", (doc_ids,))
    marker = cur.fetchone()[0]
    if marker is None:
        return None
    value = marker.isoformat()
    cur.execute("""INSERT INTO platform_config(key,value,updated_at)
                   VALUES ('sbi_ongoing_cutover_at',%s,now())
                   ON CONFLICT (key) DO NOTHING""", (value,))
    written = cur.rowcount == 1
    conn.commit()
    return value if written else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-approved", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--directory", default=str(ROOT / "data" / "research_notes"))
    args = ap.parse_args(argv)
    if not args.owner_approved or os.getenv("SBI_SONNET_OWNER_APPROVED") != "YES":
        raise SystemExit("requires --owner-approved and SBI_SONNET_OWNER_APPROVED=YES")
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be zero or greater")
    card = load_owner_price_card()
    required = ["DATABASE_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "R2_DOCUMENT_BUCKET", "ANTHROPIC_API_KEY"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit("missing credentials: " + ", ".join(missing))
    print_cost_checkpoint(card)

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    store = R2DocumentStore()
    counter, records, totals = OperationCounter(), [], Counter()
    actual_cost = Decimal("0")
    try:
        cur = conn.cursor(); identity_rows = load_company_identity_set(cur); cur.close()
        rows = [verify_remote(row, conn, store, counter, identity_rows)
                for row in local_inventory(args.directory)]
        all_eligible = eligible_scope(rows)
        already_count = sum(r.get("extraction_tuple") is not None for r in rows
                            if r.get("r2_sha_status") == "VERIFIED")
        print(f"expected_scope = {EXPECTED_DOCUMENTS}")
        print(f"eligible_now = {len(all_eligible)}")
        print(f"already_extracted = {already_count}")
        print(f"remaining = {len(all_eligible)}", flush=True)
        print_remaining_cost_checkpoint(card, len(all_eligible))
        eligible = all_eligible if args.limit is None else all_eligible[:args.limit]
        total = len(eligible)
        totals["selected"] = total
        for index, row in enumerate(eligible, 1):
            base = {"doc_id": row["documents_id"], "ipo_id": row["ipo_id"],
                    "model": MODEL, "prompt_version": PROMPT_VERSION,
                    "input_tokens": 0, "output_tokens": 0, "actual_cost": "0.000000"}
            if already_extracted(conn, row["documents_id"]):
                records.append({**base, "status": "ALREADY_EXTRACTED", "error": None})
                totals["already_extracted"] += 1
                continue
            try:
                body = store.get_document(row["documents_object_key"])
                pages = pdf_pages(body)
                estimated_input = estimate_input_tokens(pages)
                if actual_cost + cost(estimated_input, card.output_cap, card) > card.spend_cap:
                    totals["spend_stopped"] = 1
                    print(f"STOP: next projected call would exceed ${card.spend_cap:.2f}", flush=True); break
                totals["calls"] += 1
                response, itok, otok, stop_reason = anthropic_call(
                    pages=pages, api_key=os.environ["ANTHROPIC_API_KEY"], output_cap=card.output_cap)
                note_cost = cost(itok, otok, card); actual_cost += note_cost
                base.update(input_tokens=itok, output_tokens=otok,
                            actual_cost=f"{note_cost:.6f}", stop_reason=stop_reason)
                totals["input_tokens"] += itok; totals["output_tokens"] += otok
                try:
                    response_status, parsed = parse_complete_response(
                        response, doc_id=row["documents_id"], stop_reason=stop_reason)
                except Exception as exc:
                    record = {**base, "status": "PARSE_ERROR", "error": f"{type(exc).__name__}: {exc}"}
                    records.append(record); print_progress(index, total, row, record, actual_cost)
                    totals["PARSE_ERROR"] += 1; continue
                if response_status == "TRUNCATED":
                    record = {**base, "status": "TRUNCATED", "error": "output reached owner cap"}
                    records.append(record); totals["TRUNCATED"] += 1
                    print_progress(index, total, row, record, actual_cost)
                    continue
                assert parsed is not None
                try:
                    validate_evidence(parsed, pages)
                except Exception as exc:
                    record = {**base, "status": "EVIDENCE_REJECTED", "error": f"{type(exc).__name__}: {exc}"}
                    records.append(record); print_progress(index, total, row, record, actual_cost)
                    totals["EVIDENCE_REJECTED"] += 1; continue
                try:
                    write_extraction(conn, ipo_id=row["ipo_id"], doc_id=row["documents_id"],
                                     extraction=parsed, validated=True)
                except Exception as exc:
                    conn.rollback(); record = {**base, "status": "WRITE_ERROR", "error": f"{type(exc).__name__}: {exc}"}
                    records.append(record); print_progress(index, total, row, record, actual_cost)
                    totals["WRITE_ERROR"] += 1; continue
                record = {**base, "status": "EXTRACTED", "error": None}
                records.append(record); totals["successes"] += 1
                print_progress(index, total, row, record, actual_cost)
            except Exception as exc:
                conn.rollback(); record = {**base, "status": "MODEL_ERROR", "error": f"{type(exc).__name__}: {exc}"}
                records.append(record); print_progress(index, total, row, record, actual_cost)
                totals["MODEL_ERROR"] += 1

        verified = [verify_remote(row, conn, store, OperationCounter(), identity_rows)
                    for row in local_inventory(args.directory)]
        cutover_written = maybe_write_cutover(
            conn, limit=args.limit, verified=verified, totals=totals)
        holdouts = deterministic_holdout_report(verified, identity_rows)
        result = {"records": records, "summary": {"calls": totals["calls"],
            "input_tokens": totals["input_tokens"], "output_tokens": totals["output_tokens"],
            "actual_cost": f"{actual_cost:.6f}", "successes": totals["successes"],
            "failures": sum(totals[k] for k in FAILURE_STATUSES),
            "failures_by_category": {k: totals[k] for k in FAILURE_STATUSES},
            "full_run_approval_blocked": full_run_approval_blocked(totals),
            "spend_stopped": bool(totals["spend_stopped"]),
            "cutover_written": cutover_written,
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
