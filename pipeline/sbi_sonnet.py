"""Canonical, evidence-first SBI note extraction.

This module intentionally contains no PDF regex parser.  Production callers obtain
the immutable bytes from ``documents.object_key`` and inject a model client; tests use
the same parser/writer with a deterministic client.  A paid client is never created at
import time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "sbi-v1"
SOURCE_TYPE = "SBI"

# These are sourced statements, never house-calculated valuation outputs.
SCALAR_FIELDS = {"sbi_rating", "sbi_fair_value", "sbi_target_value"}
FORBIDDEN_FIELDS = {
    "fair_value_lo", "fair_value_hi", "pe", "pb", "roe", "roce", "fcf",
    "margin_of_safety", "pro_forma_eps", "interest_savings",
}
CLAIM_KINDS = {
    "valuation_observation": ("valuation", "neutral"),
    "key_positive": ("sbi", "positive"),
    "key_risk": ("risk", "negative"),
    "business_observation": ("sbi", "neutral"),
    "verdict": ("sbi", "neutral"),
}

SYSTEM_PROMPT = """Extract only statements explicitly printed in this SBI IPO note.
Return ONLY one JSON object with arrays `claims` and `scalar_facts`.

Allowed scalar_facts fields: sbi_rating, sbi_fair_value, sbi_target_value. Fair or
target values are allowed only when SBI explicitly prints them. Allowed claim kinds:
valuation_observation, business_observation, key_positive, key_risk, verdict.

Every claim/fact must contain a positive integer page_number and a short verbatim
excerpt copied from that page. Every claim also needs `statement` and `kind`; every
fact needs `field` and `value`. Do not calculate or infer house fair value, pro-forma
EPS, P/E, ROE, ROCE, FCF, margin of safety, interest savings, or any other
deterministic valuation output. Omit unsupported items; never fill gaps."""


class SBIExtractionError(ValueError):
    """The model response cannot safely enter canonical writers."""


def _json_object(response: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict):
        obj = response
    else:
        try:
            obj = json.loads(response)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SBIExtractionError("malformed model response") from exc
    if not isinstance(obj, dict):
        raise SBIExtractionError("model response must be a JSON object")
    return obj


def parse_extraction(response: str | bytes | dict[str, Any], *, doc_id: int) -> dict[str, Any]:
    """Validate the complete response before any database write."""
    obj = _json_object(response)
    forbidden = FORBIDDEN_FIELDS.intersection(obj)
    if forbidden:
        raise SBIExtractionError(f"deterministic fields are forbidden: {sorted(forbidden)}")
    claims = obj.get("claims", [])
    facts = obj.get("scalar_facts", [])
    if not isinstance(claims, list) or not isinstance(facts, list):
        raise SBIExtractionError("claims and scalar_facts must be arrays")
    clean_claims, clean_facts = [], []
    for position, claim in enumerate(claims):
        if not isinstance(claim, dict) or claim.get("kind") not in CLAIM_KINDS:
            raise SBIExtractionError(f"claims[{position}] has unsupported kind")
        if not claim.get("statement") or not claim.get("excerpt"):
            raise SBIExtractionError(f"claims[{position}] lacks statement/excerpt")
        if not isinstance(claim.get("page_number"), int) or claim["page_number"] < 1:
            raise SBIExtractionError(f"claims[{position}] lacks a valid page_number")
        confidence = claim.get("confidence")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise SBIExtractionError(f"claims[{position}] has invalid confidence")
        clean_claims.append({**claim, "doc_id": doc_id, "source_type": SOURCE_TYPE,
                             "model": MODEL, "prompt_version": PROMPT_VERSION})
    for position, fact in enumerate(facts):
        if not isinstance(fact, dict) or fact.get("field") not in SCALAR_FIELDS:
            raise SBIExtractionError(f"scalar_facts[{position}] has unsupported field")
        if fact.get("value") in (None, "") or not fact.get("excerpt"):
            raise SBIExtractionError(f"scalar_facts[{position}] lacks value/excerpt")
        if not isinstance(fact.get("page_number"), int) or fact["page_number"] < 1:
            raise SBIExtractionError(f"scalar_facts[{position}] lacks a valid page_number")
        clean_facts.append({**fact, "doc_id": doc_id, "source_type": SOURCE_TYPE,
                            "model": MODEL, "prompt_version": PROMPT_VERSION})
    return {"claims": clean_claims, "scalar_facts": clean_facts}


def already_extracted(conn, doc_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("""SELECT 1 FROM insights WHERE doc_id=%s AND source_type='SBI'
                    AND model=%s AND prompt_version=%s
                  UNION ALL
                  SELECT 1 FROM source_facts WHERE source LIKE %s
                  LIMIT 1""",
                (doc_id, MODEL, PROMPT_VERSION,
                 f'SBI:doc={doc_id}:page=%:model={MODEL}:prompt={PROMPT_VERSION}:%'))
    return cur.fetchone() is not None


def write_extraction(conn, *, ipo_id: int, doc_id: int, extraction: dict[str, Any], commit=True):
    """Route only canonical sourced facts and evidenced insights; never valuation."""
    if already_extracted(conn, doc_id):
        return {"skipped": True, "facts": 0, "insights": 0}
    parsed = parse_extraction(extraction, doc_id=doc_id)
    try:
        from .fill_v2 import log_source_fact, upsert_insights
    except ImportError:
        from fill_v2 import log_source_fact, upsert_insights
    for fact in parsed["scalar_facts"]:
        provenance = (f"SBI:doc={doc_id}:page={fact['page_number']}:model={MODEL}:"
                      f"prompt={PROMPT_VERSION}:excerpt={fact['excerpt'][:250]}")
        log_source_fact(conn, ipo_id, fact["field"], fact["value"], provenance,
                        doc_id=doc_id, confidence=fact.get("confidence", 1.0), commit=False)
    items = []
    for claim in parsed["claims"]:
        category, direction = CLAIM_KINDS[claim["kind"]]
        items.append({"category": category, "direction": direction,
                      "statement": claim["statement"], "excerpt": claim["excerpt"],
                      "page_number": claim["page_number"], "doc_id": doc_id,
                      "confidence": claim.get("confidence")})
    inserted, _, run_id = upsert_insights(
        conn, ipo_id, items, model=MODEL, prompt_version=PROMPT_VERSION,
        doc_id=doc_id, source_type=SOURCE_TYPE, commit=False)
    if commit:
        conn.commit()
    return {"skipped": False, "facts": len(parsed["scalar_facts"]),
            "insights": inserted, "run_id": run_id}


def extract(*, doc_id: int, pages: list[dict[str, Any]], model_client: Callable[..., Any]):
    """Invoke an explicitly supplied client, making offline testing the default."""
    response = model_client(model=MODEL, prompt_version=PROMPT_VERSION,
                            system=SYSTEM_PROMPT, pages=pages)
    return parse_extraction(response, doc_id=doc_id)
