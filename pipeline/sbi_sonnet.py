"""Canonical, evidence-first SBI note extraction.

This module intentionally contains no PDF regex parser.  Production callers obtain
the immutable bytes from ``documents.object_key`` and inject a model client; tests use
the same parser/writer with a deterministic client.  A paid client is never created at
import time.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "sbi-v1.2"
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
CLAIM_KEYS = {"kind", "statement", "excerpt", "page_number", "confidence"}
SCALAR_KEYS = {"field", "value", "excerpt", "page_number", "confidence"}

SYSTEM_PROMPT = """Extract only statements explicitly printed in this SBI IPO note.
Return ONLY one JSON object with arrays `claims` and `scalar_facts`.

Use this literal minimal schema example:
{
  "claims": [
    {
      "kind": "key_risk",
      "statement": "One concise sentence explicitly supported by the note.",
      "excerpt": "Verbatim excerpt of no more than fifteen words.",
      "page_number": 3
    }
  ],
  "scalar_facts": [
    {
      "field": "sbi_rating",
      "value": "SUBSCRIBE",
      "excerpt": "Verbatim excerpt of no more than fifteen words.",
      "page_number": 1
    }
  ]
}

Use exactly these field names.
For claims, the only accepted keys are: kind, statement, excerpt, page_number,
confidence (optional).
For scalar_facts, the only accepted keys are: field, value, excerpt, page_number,
confidence (optional).
Do not use synonyms such as: text, quote, description, citation, page, rating_text.
Omit any claim or scalar fact that cannot be supported using the exact required schema.

Allowed scalar_facts fields: sbi_rating, sbi_fair_value, sbi_target_value. Fair or
target values are allowed only when SBI explicitly prints them. Allowed claim kinds:
valuation_observation, business_observation, key_positive, key_risk, verdict.

Every claim/fact must contain a positive integer page_number and a short verbatim
excerpt copied from that page. Every claim also needs `statement` and `kind`; every
fact needs `field` and `value`. Do not calculate or infer house fair value, pro-forma
EPS, P/E, ROE, ROCE, FCF, margin of safety, interest savings, or any other
deterministic valuation output. Omit unsupported items; never fill gaps.
Maximum 10 claims and maximum 3 scalar_facts. Excerpts must contain no more than
15 words. Each statement must be one concise sentence.

Respond with the JSON object only: no Markdown fences, commentary, preamble, or
explanation after the object."""


class SBIExtractionError(ValueError):
    """The model response cannot safely enter canonical writers."""


def _json_object(response: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict):
        obj = response
    else:
        if isinstance(response, bytes):
            response = response.decode("utf-8", errors="replace")
        if not isinstance(response, str):
            raise SBIExtractionError("model response must be text or an object")
        text = response.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text,
                              flags=re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        decoder = json.JSONDecoder()
        try:
            obj, end = decoder.raw_decode(text)
            if text[end:].strip():
                raise json.JSONDecodeError("trailing output", text, end)
        except json.JSONDecodeError:
            candidates = []
            for start, char in enumerate(text):
                if char != "{":
                    continue
                try:
                    candidate, end = decoder.raw_decode(text, start)
                except json.JSONDecodeError:
                    continue
                prefix, suffix = text[:start].strip(), text[end:].strip()
                wrappers = (prefix, suffix)
                if (isinstance(candidate, dict) and all(len(part) <= 120 for part in wrappers)
                        and not any(any(c in part for c in "{}[]`") for part in wrappers)):
                    candidates.append(candidate)
            if len(candidates) != 1:
                prefix = " ".join(text[:120].split())
                raise SBIExtractionError(f"malformed model response; prefix={prefix!r}")
            obj = candidates[0]
    if not isinstance(obj, dict):
        raise SBIExtractionError("model response must be a JSON object")
    return obj


def parse_extraction(response: str | bytes | dict[str, Any], *, doc_id: int) -> dict[str, Any]:
    """Validate the complete response before any database write."""
    obj = _json_object(response)
    forbidden = FORBIDDEN_FIELDS.intersection(obj)
    if forbidden:
        raise SBIExtractionError(f"deterministic fields are forbidden: {sorted(forbidden)}")
    unexpected_top = set(obj) - {"claims", "scalar_facts"}
    if unexpected_top:
        raise SBIExtractionError(f"model response has unsupported top-level fields: {sorted(unexpected_top)}")
    claims = obj.get("claims", [])
    facts = obj.get("scalar_facts", [])
    if not isinstance(claims, list) or not isinstance(facts, list):
        raise SBIExtractionError("claims and scalar_facts must be arrays")
    if len(claims) > 10:
        raise SBIExtractionError("claims exceeds maximum of 10")
    if len(facts) > 3:
        raise SBIExtractionError("scalar_facts exceeds maximum of 3")
    clean_claims, clean_facts, dropped = [], [], []
    for position, claim in enumerate(claims):
        reason = _claim_error(claim)
        if reason:
            dropped.append({"item_type": "claim", "position": position, "reason": reason})
        else:
            clean_claims.append({**claim, "doc_id": doc_id, "source_type": SOURCE_TYPE,
                                 "model": MODEL, "prompt_version": PROMPT_VERSION})
    for position, fact in enumerate(facts):
        reason = _scalar_error(fact)
        if reason:
            dropped.append({"item_type": "scalar_fact", "position": position, "reason": reason})
        else:
            clean_facts.append({**fact, "doc_id": doc_id, "source_type": SOURCE_TYPE,
                                "model": MODEL, "prompt_version": PROMPT_VERSION})
    if not clean_claims and not clean_facts:
        raise SBIExtractionError("no valid extraction items remain after item validation")
    return {"claims": clean_claims, "scalar_facts": clean_facts, "dropped_items": dropped}


def _confidence_error(value):
    if value is None:
        return None
    try:
        valid = 0 <= float(value) <= 1
    except (TypeError, ValueError):
        valid = False
    return None if valid else "invalid confidence"


def _claim_error(claim):
    if not isinstance(claim, dict): return "item must be an object"
    if claim.get("kind") not in CLAIM_KINDS: return "unsupported kind"
    if not claim.get("statement") or not claim.get("excerpt"): return "missing required statement/excerpt fields"
    unexpected = set(claim) - CLAIM_KEYS
    if unexpected: return f"unsupported fields: {sorted(unexpected)}"
    if len(str(claim["excerpt"]).split()) > 15: return "excerpt exceeds 15 words"
    statement = str(claim["statement"]).strip()
    if "\n" in statement or "\r" in statement: return "statement must be single-line"
    if len(statement.split()) > 40: return "statement exceeds 40 words"
    if not isinstance(claim.get("page_number"), int) or claim["page_number"] < 1: return "invalid page_number"
    return _confidence_error(claim.get("confidence"))


def _scalar_error(fact):
    if not isinstance(fact, dict): return "item must be an object"
    if fact.get("field") not in SCALAR_FIELDS: return "unsupported field"
    if fact.get("value") in (None, ""): return "missing or empty value"
    if not fact.get("excerpt"): return "missing required excerpt field"
    unexpected = set(fact) - SCALAR_KEYS
    if unexpected: return f"unsupported fields: {sorted(unexpected)}"
    if len(str(fact["excerpt"]).split()) > 15: return "excerpt exceeds 15 words"
    if not isinstance(fact.get("page_number"), int) or fact["page_number"] < 1: return "invalid page_number"
    return _confidence_error(fact.get("confidence"))


def estimate_input_tokens(pages, system_prompt=SYSTEM_PROMPT):
    """One conservative estimator shared by inventory, history, and ongoing lanes."""
    text_chars = sum(len(page.get("text", "") if isinstance(page, dict) else page[1])
                     for page in pages)
    return (text_chars + 3) // 4 + (len(system_prompt) + 3) // 4


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


def write_extraction(conn, *, ipo_id: int, doc_id: int, extraction: dict[str, Any],
                     commit=True, validated=False):
    """Route only canonical sourced facts and evidenced insights; never valuation."""
    if already_extracted(conn, doc_id):
        return {"skipped": True, "facts": 0, "insights": 0}
    parsed = extraction if validated else parse_extraction(extraction, doc_id=doc_id)
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
