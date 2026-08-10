#!/usr/bin/env python3
"""Restartable SBI extraction worker backed only by the documents ledger and R2."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

import pymupdf

try:
    from .r2 import R2DocumentStore
    from .sbi_sonnet import (
        MODEL, PROMPT_VERSION, TOOL_NAME, already_extracted, build_tool_request,
        parse_extraction, pending_documents_query, write_extraction,
    )
except ImportError:
    from r2 import R2DocumentStore
    from sbi_sonnet import (
        MODEL, PROMPT_VERSION, TOOL_NAME, already_extracted, build_tool_request,
        parse_extraction, pending_documents_query, write_extraction,
    )

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "artifacts" / "sbi-extraction"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
RUN_CAP_ENV = "SBI_SONNET_RUN_CAP_USD"
PRICE_ENV = {
    "input_usd_per_mtok": "SBI_SONNET_INPUT_USD_PER_MTOK",
    "output_usd_per_mtok": "SBI_SONNET_OUTPUT_USD_PER_MTOK",
    "output_cap": "SBI_SONNET_OUTPUT_CAP",
    "spend_cap": RUN_CAP_ENV,
}
INPUT_TOKEN_RESERVE_MIN = 1_024
INPUT_TOKEN_RESERVE_PCT = Decimal("0.10")
TERMINAL_STATUSES = (
    "EXTRACTED", "EXTRACTED_WITH_DROPS", "ALREADY_EXTRACTED",
    "SHA_MISMATCH", "MISSING_DOCUMENT", "MODEL_ERROR", "PARSE_ERROR",
    "EVIDENCE_REJECTED", "WRITE_ERROR", "TRUNCATED", "SPEND_STOPPED",
)
# Stable two-int PostgreSQL advisory-lock identity for the canonical SBI worker.
# Session locks survive commits/rollbacks, never hold row locks, and are released
# automatically if the connection dies.
SBI_WORKER_LOCK = (1_092_499_283, 1_651_073_001)


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class PriceCard:
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    output_cap: int
    spend_cap: Decimal


@dataclass(frozen=True)
class WorkerConfiguration:
    status: str
    card: PriceCard | None = None
    error: str | None = None


def worker_configuration(environ=None):
    environ = os.environ if environ is None else environ
    names = tuple(PRICE_ENV.values())
    present = [name for name in names if environ.get(name)]
    if not present:
        return WorkerConfiguration("SKIPPED_OWNER_NOT_CONFIGURED")
    missing = [name for name in names if not environ.get(name)]
    if missing:
        return WorkerConfiguration("WARNING_CONFIGURATION_ERROR",
                                   error="missing: " + ", ".join(missing))
    try:
        card = PriceCard(
            Decimal(environ[PRICE_ENV["input_usd_per_mtok"]]),
            Decimal(environ[PRICE_ENV["output_usd_per_mtok"]]),
            int(environ[PRICE_ENV["output_cap"]]),
            Decimal(environ[PRICE_ENV["spend_cap"]]),
        )
    except (ValueError, ArithmeticError):
        return WorkerConfiguration("WARNING_CONFIGURATION_ERROR",
                                   error="values must be positive numbers")
    if min(card.input_usd_per_mtok, card.output_usd_per_mtok,
           Decimal(card.output_cap), card.spend_cap) <= 0:
        return WorkerConfiguration("WARNING_CONFIGURATION_ERROR",
                                   error="values must be positive numbers")
    return WorkerConfiguration("CONFIGURED", card=card)


def load_owner_price_card(environ=None):
    config = worker_configuration(environ)
    if config.status != "CONFIGURED":
        detail = f": {config.error}" if config.error else ""
        raise SystemExit(f"OWNER-APPROVED PRICE CARD REQUIRED: {config.status}{detail}")
    return config.card


def cost(input_tokens: int, output_tokens: int, card: PriceCard) -> Decimal:
    return ((Decimal(input_tokens) * card.input_usd_per_mtok
             + Decimal(output_tokens) * card.output_usd_per_mtok)
            / Decimal(1_000_000))


def guarded_input_tokens(official_count: int) -> int:
    if not isinstance(official_count, int) or isinstance(official_count, bool) or official_count <= 0:
        raise ValueError("official_count must be a positive integer")
    percentage = math.ceil(official_count * (Decimal("1") + INPUT_TOKEN_RESERVE_PCT))
    return max(official_count + INPUT_TOKEN_RESERVE_MIN, percentage)


def pdf_pages(body: bytes) -> list[dict]:
    with pymupdf.open(stream=body, filetype="pdf") as doc:
        return [{"page_number": i + 1, "text": page.get_text()}
                for i, page in enumerate(doc)]


TYPOGRAPHY_FOLD = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u201a": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u00a0": " ",
})
COMPARISON_MODE = "NFKC+TYPOGRAPHY_FOLD+WHITESPACE"


def normalize_evidence_text(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).translate(TYPOGRAPHY_FOLD).split())


def validate_evidence(extraction: dict, pages: list[dict]):
    """Require normalized exact evidence on the asserted synthetic page."""
    page_text = {page["page_number"]: normalize_evidence_text(page["text"])
                 for page in pages}
    groups = (("claim", extraction["claims"]),
              ("scalar_fact", extraction["scalar_facts"]))
    for item_type, items in groups:
        for position, item in enumerate(items):
            original = item["excerpt"]
            excerpt = normalize_evidence_text(original)
            asserted = item["page_number"]
            if excerpt and excerpt in page_text.get(asserted, ""):
                continue
            found = sorted(page for page, text in page_text.items()
                           if page != asserted and excerpt and excerpt in text)
            diagnostic = " ".join(str(original).split())[:160]
            raise ValueError(
                f'{item_type}[{position}] evidence not found on asserted PAGE {asserted}; '
                f'excerpt="{diagnostic}"; comparison={COMPARISON_MODE}; '
                f'found_on_other_pages={found}')


def _anthropic_request(url: str, *, payload: dict, api_key: str):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ModelError(f"Anthropic HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ModelError(str(exc)) from exc
    if not isinstance(result, dict) or result.get("type") == "error":
        raise ModelError(json.dumps(result)[:1000])
    return result


def count_tokens_call(*, pages: list[dict], api_key: str) -> int:
    """Count tokens for the exact request immediately before its generation."""
    result = _anthropic_request(
        COUNT_TOKENS_URL, payload=build_tool_request(pages), api_key=api_key)
    value = result.get("input_tokens")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ModelError(f"invalid count_tokens response: {json.dumps(result)[:1000]}")
    return value


def anthropic_call(*, pages: list[dict], api_key: str, output_cap: int):
    """Make exactly one forced strict tool call."""
    result = _anthropic_request(
        MESSAGES_URL,
        payload=build_tool_request(pages, output_cap=output_cap), api_key=api_key)
    usage = result.get("usage") or {}
    itok, otok = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    stop_reason, content = result.get("stop_reason"), result.get("content")
    if stop_reason == "max_tokens":
        text = "".join(block.get("text", "") for block in (content or [])
                       if isinstance(block, dict) and block.get("type") == "text")
        return text, itok, otok, stop_reason
    if stop_reason != "tool_use" or not isinstance(content, list) or len(content) != 1:
        raise ModelError("forced SBI extraction must return exactly one tool_use block")
    block = content[0]
    if (not isinstance(block, dict) or block.get("type") != "tool_use"
            or block.get("name") != TOOL_NAME or not isinstance(block.get("input"), dict)):
        raise ModelError("forced SBI extraction returned an invalid tool_use block")
    return block["input"], itok, otok, stop_reason


def select_pending_documents(conn, *, limit=None):
    """Run the one canonical DB pending-document query."""
    sql, params = pending_documents_query(limit=limit)
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return list(cur.fetchall())
    finally:
        close = getattr(cur, "close", None)
        if close:
            close()


def parse_complete_response(response, *, doc_id, stop_reason=None,
                            parser=parse_extraction):
    """Never pass capped output into parsing or canonical persistence."""
    if stop_reason == "max_tokens":
        return "TRUNCATED", None
    return "COMPLETE", parser(response, doc_id=doc_id)


def extraction_success_status(parsed):
    return "EXTRACTED_WITH_DROPS" if parsed.get("dropped_items") else "EXTRACTED"


def _base_record(row):
    doc_id, ipo_id, _, _ = row
    return {"doc_id": doc_id, "ipo_id": ipo_id, "model": MODEL,
            "prompt_version": PROMPT_VERSION, "input_tokens": 0,
            "output_tokens": 0, "actual_cost": "0.000000"}


def _record(records, summary, base, status, **extra):
    record = {**base, "status": status, **extra}
    records.append(record)
    summary[status] += 1
    return record


def try_acquire_worker_lock(conn) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("SELECT pg_try_advisory_lock(%s,%s)", SBI_WORKER_LOCK)
        row = cur.fetchone()
        return bool(row and row[0] is True)
    finally:
        close = getattr(cur, "close", None)
        if close:
            close()


def release_worker_lock(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT pg_advisory_unlock(%s,%s)", SBI_WORKER_LOCK)
        cur.fetchone()
    finally:
        close = getattr(cur, "close", None)
        if close:
            close()


def end_read_transaction(conn):
    """End a read-only psycopg transaction before any external IO."""
    commit = getattr(conn, "commit", None)
    if commit:
        commit()


def run_pending_worker(conn, **kwargs):
    """Acquire the one session lock and run, or fail closed without external IO."""
    acquired = try_acquire_worker_lock(conn)
    end_read_transaction(conn)
    if not acquired:
        return {"summary": {"status": "WORKER_BUSY", "WORKER_BUSY": 1,
                            "selected": 0, "actual_sbi_spend": "0.000000"},
                "records": []}
    try:
        return _run_pending_worker_locked(conn, **kwargs)
    finally:
        try:
            release_worker_lock(conn)
        finally:
            end_read_transaction(conn)


def _run_pending_worker_locked(conn, *, store=None, card=None, environ=None, limit=None,
                               model_call=anthropic_call,
                               token_counter=count_tokens_call,
                               page_reader=pdf_pages):
    """Process the current DB backlog; restart naturally reselects only pending rows.

    Network transports are injectable so tests never need credentials or external IO.
    Production requires both the exact-request token counter and strict model transport.
    """
    environ = os.environ if environ is None else environ
    card = card or load_owner_price_card(environ)
    if (model_call is anthropic_call
            and environ.get("SBI_SONNET_OWNER_APPROVED") != "YES"):
        return {"summary": {"status": "OWNER_NOT_APPROVED",
                            "extraction_status": "OWNER_NOT_APPROVED",
                            "selected": 0, "actual_sbi_spend": "0.000000"},
                "records": []}
    store = store or R2DocumentStore()
    api_key = environ.get("ANTHROPIC_API_KEY")
    if (model_call is anthropic_call or token_counter is count_tokens_call) and not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for production extraction")
    rows = select_pending_documents(conn, limit=limit)
    end_read_transaction(conn)
    maximum_output_cost = cost(0, len(rows) * card.output_cap, card)
    print(
        "SBI PREFLIGHT\n"
        f"selected={len(rows)}\n"
        f"input_price={card.input_usd_per_mtok}/MTok\n"
        f"output_price={card.output_usd_per_mtok}/MTok\n"
        f"output_cap={card.output_cap}\n"
        f"run_cap=${card.spend_cap}\n"
        f"max_output_cost=${maximum_output_cost:.6f}\n"
        "input_guard=official count_tokens per document + max(1024,10%)\n"
        "generation=OWNER APPROVED",
        flush=True,
    )
    summary = Counter(selected=len(rows))
    summary.update({status: 0 for status in TERMINAL_STATUSES})
    records, spent = [], Decimal(0)
    stop_later_calls = False

    for row in rows:
        doc_id, ipo_id, object_key, expected_sha = row
        base = _base_record(row)
        if stop_later_calls:
            _record(records, summary, base, "SPEND_STOPPED",
                    error="owner run cap or guard assumption exhausted")
            continue
        extracted = already_extracted(conn, doc_id)
        end_read_transaction(conn)
        if extracted:
            _record(records, summary, base, "ALREADY_EXTRACTED", error=None)
            continue
        try:
            body = store.get_document(object_key)
            if body is None:
                raise FileNotFoundError(object_key)
        except (FileNotFoundError, KeyError) as exc:
            _record(records, summary, base, "MISSING_DOCUMENT",
                    error=f"{type(exc).__name__}: {exc}")
            continue
        except Exception as exc:
            _record(records, summary, base, "MISSING_DOCUMENT",
                    error=f"{type(exc).__name__}: {exc}")
            continue
        if hashlib.sha256(body).hexdigest() != expected_sha:
            _record(records, summary, base, "SHA_MISMATCH",
                    error="R2 bytes do not match documents.sha256")
            continue
        try:
            pages = page_reader(body)
        except Exception as exc:
            _record(records, summary, base, "PARSE_ERROR",
                    error=f"{type(exc).__name__}: {exc}")
            continue
        try:
            official = token_counter(pages=pages, api_key=api_key)
            guarded = guarded_input_tokens(official)
        except Exception as exc:
            _record(records, summary, base, "MODEL_ERROR",
                    error=f"{type(exc).__name__}: {exc}")
            continue
        projected = spent + cost(guarded, card.output_cap, card)
        if projected > card.spend_cap:
            stop_later_calls = True
            _record(records, summary, base, "SPEND_STOPPED",
                    official_preflight_input_tokens=official,
                    guarded_preflight_input_tokens=guarded,
                    error=f"guarded maximum ${projected:.6f} exceeds ${card.spend_cap:.6f}")
            continue
        try:
            response, itok, otok, stop_reason = model_call(
                pages=pages, api_key=api_key, output_cap=card.output_cap)
        except Exception as exc:
            stop_later_calls = True
            _record(records, summary, base, "MODEL_ERROR",
                    official_preflight_input_tokens=official,
                    guarded_preflight_input_tokens=guarded,
                    error=f"{type(exc).__name__}: {exc}")
            continue
        note_cost = cost(itok, otok, card)
        spent += note_cost
        base.update(input_tokens=itok, output_tokens=otok,
                    actual_cost=f"{note_cost:.6f}")
        guard_exceeded = itok > guarded or spent > card.spend_cap
        try:
            response_status, parsed = parse_complete_response(
                response, doc_id=doc_id, stop_reason=stop_reason)
        except Exception as exc:
            _record(records, summary, base, "PARSE_ERROR",
                    official_preflight_input_tokens=official,
                    guarded_preflight_input_tokens=guarded,
                    error=f"{type(exc).__name__}: {exc}")
            stop_later_calls = stop_later_calls or guard_exceeded
            continue
        if response_status == "TRUNCATED":
            _record(records, summary, base, "TRUNCATED",
                    official_preflight_input_tokens=official,
                    guarded_preflight_input_tokens=guarded,
                    error="output reached owner-configured cap")
            stop_later_calls = stop_later_calls or guard_exceeded
            continue
        assert parsed is not None
        dropped = parsed.get("dropped_items", [])
        try:
            validate_evidence(parsed, pages)
        except Exception as exc:
            _record(records, summary, base, "EVIDENCE_REJECTED",
                    dropped_items=dropped,
                    official_preflight_input_tokens=official,
                    guarded_preflight_input_tokens=guarded,
                    error=f"{type(exc).__name__}: {exc}")
            stop_later_calls = stop_later_calls or guard_exceeded
            continue
        try:
            write_extraction(conn, ipo_id=ipo_id, doc_id=doc_id,
                             extraction=parsed, validated=True)
        except Exception as exc:
            conn.rollback()
            _record(records, summary, base, "WRITE_ERROR", dropped_items=dropped,
                    official_preflight_input_tokens=official,
                    guarded_preflight_input_tokens=guarded,
                    error=f"{type(exc).__name__}: {exc}")
            stop_later_calls = stop_later_calls or guard_exceeded
            continue
        _record(records, summary, base, extraction_success_status(parsed),
                dropped_items=dropped,
                official_preflight_input_tokens=official,
                guarded_preflight_input_tokens=guarded, stop_reason=stop_reason,
                error=None)
        stop_later_calls = stop_later_calls or guard_exceeded

    summary["actual_sbi_spend"] = f"{spent:.6f}"
    summary["spend_stopped"] = bool(stop_later_calls)
    summary["retryable_selected"] = sum(
        summary[status] for status in (
            "SHA_MISMATCH", "MISSING_DOCUMENT", "MODEL_ERROR", "PARSE_ERROR",
            "EVIDENCE_REJECTED", "WRITE_ERROR", "TRUNCATED", "SPEND_STOPPED"))
    return {"summary": dict(summary), "records": records}


def persist_manifest(payload, directory=RESULT_DIR):
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"worker-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return str(target)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-approved", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    if not args.owner_approved or os.getenv("SBI_SONNET_OWNER_APPROVED") != "YES":
        raise SystemExit("requires --owner-approved and SBI_SONNET_OWNER_APPROVED=YES")
    required = ("DATABASE_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY", "R2_DOCUMENT_BUCKET", "ANTHROPIC_API_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit("missing credentials: " + ", ".join(missing))
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        result = run_pending_worker(conn, limit=args.limit)
        result["manifest_path"] = persist_manifest(result)
        print(json.dumps(result["summary"], indent=2))
        print(f"manifest = {result['manifest_path']}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
