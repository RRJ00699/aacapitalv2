"""Canonical, evidence-first SBI note extraction.

Production extraction is schema-forced through one strict Anthropic client tool.
The legacy JSON text parser remains available for saved-response replay and tests,
but the paid transport never falls back to prose recovery.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "sbi-v1.3"
SOURCE_TYPE = "SBI"
TOOL_NAME = "record_sbi_extraction"

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
Use the record_sbi_extraction tool with exactly these field names.

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

Use exactly these field names. Do not use synonyms such as: text, quote, description, citation, page, rating_text. Do not answer with Markdown fences, commentary, preamble,
or prose outside the forced tool call.

Allowed scalar_facts fields: sbi_rating, sbi_fair_value, sbi_target_value. Fair or
target values are allowed only when SBI explicitly prints them. Allowed claim kinds:
valuation_observation, business_observation, key_positive, key_risk, verdict.

Every claim/fact must contain a positive integer page_number and a short contiguous
verbatim excerpt copied from that page. Target 8-12 words per excerpt; the hard server
ceiling remains 15 words. If the useful source sentence is longer, select a shorter
contiguous verbatim phrase. Never paraphrase evidence.

page_number MUST be the N from the synthetic `--- PAGE N ---` marker supplied in this
request. Do not use a printed footer number, report-internal page number, section number,
or any other pagination printed inside the PDF text.

Every claim needs statement and kind; every scalar fact needs field and value. Do not
calculate or infer house fair value, pro-forma EPS, P/E, ROE, ROCE, FCF, margin of
safety, interest savings, or any other deterministic valuation output. Omit unsupported
items; never fill gaps. Maximum 10 claims and maximum 3 scalar_facts. Each statement
must be a single concise line of no more than 40 words.

Call record_sbi_extraction exactly once. Do not answer with prose or Markdown."""

SBI_EXTRACTION_TOOL = {
    "name": TOOL_NAME,
    "description": "Record canonical, evidenced SBI claims and explicitly printed scalar facts.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "claims": {
                "type": "array",
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "kind": {"type": "string", "enum": list(CLAIM_KINDS)},
                        "statement": {"type": "string"},
                        "excerpt": {"type": "string"},
                        "page_number": {"type": "integer", "minimum": 1},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["kind", "statement", "excerpt", "page_number"],
                },
            },
            "scalar_facts": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string", "enum": sorted(SCALAR_FIELDS)},
                        "value": {"type": ["string", "number"]},
                        "excerpt": {"type": "string"},
                        "page_number": {"type": "integer", "minimum": 1},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["field", "value", "excerpt", "page_number"],
                },
            },
        },
        "required": ["claims", "scalar_facts"],
    },
}
TOOL_CHOICE = {
    "type": "tool",
    "name": TOOL_NAME,
    "disable_parallel_tool_use": True,
}


class SBIExtractionError(ValueError):
    """The model response cannot safely enter canonical writers."""


def build_page_text(pages: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"--- PAGE {page['page_number']} ---\n{page.get('text', '')}" for page in pages
    )


def build_tool_request(pages: list[dict[str, Any]], *, output_cap: int | None = None) -> dict[str, Any]:
    """Build the one canonical request shape used by Messages and token counting."""
    payload: dict[str, Any] = {
        "model": MODEL,
        "system": SYSTEM_PROMPT,
        "tools": [SBI_EXTRACTION_TOOL],
        "tool_choice": TOOL_CHOICE,
        "messages": [{"role": "user", "content": build_page_text(pages)}],
    }
    if output_cap is not None:
        payload["max_tokens"] = output_cap
        payload["temperature"] = 0
    return payload


def _json_object(response: str | bytes | dict[str, Any]) -> dict[str, Any]:
    """Legacy/offline parser. Paid production transport passes a tool input dict."""
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
    if isinstance(value, bool):
        return "invalid confidence"
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
    if not isinstance(claim.get("page_number"), int) or isinstance(claim.get("page_number"), bool) or claim["page_number"] < 1:
        return "invalid page_number"
    return _confidence_error(claim.get("confidence"))


def _scalar_error(fact):
    if not isinstance(fact, dict): return "item must be an object"
    if fact.get("field") not in SCALAR_FIELDS: return "unsupported field"
    if fact.get("value") in (None, ""): return "missing or empty value"
    if not fact.get("excerpt"): return "missing required excerpt field"
    unexpected = set(fact) - SCALAR_KEYS
    if unexpected: return f"unsupported fields: {sorted(unexpected)}"
    if len(str(fact["excerpt"]).split()) > 15: return "excerpt exceeds 15 words"
    if not isinstance(fact.get("page_number"), int) or isinstance(fact.get("page_number"), bool) or fact["page_number"] < 1:
        return "invalid page_number"
    return _confidence_error(fact.get("confidence"))


def estimate_input_tokens(pages, system_prompt=SYSTEM_PROMPT):
    """Legacy local approximation; never use it as an authorization ceiling."""
    text_chars = sum(len(page.get("text", "") if isinstance(page, dict) else page[1])
                     for page in pages)
    return (text_chars + 3) // 4 + (len(system_prompt) + 3) // 4


def completion_clause(doc_expression: str = "%s", *, model=MODEL,
                      prompt_version=PROMPT_VERSION):
    """Return the one facts-or-insights completion rule.

    ``doc_expression`` is either the bound ``%s`` used by the point lookup or the
    trusted ``d.id`` expression used by the correlated pending-documents query.
    Keeping this fragment here prevents selection, retries, and reporting from
    acquiring subtly different definitions of complete.
    """
    if doc_expression not in {"%s", "d.id"}:
        raise ValueError("unsupported document SQL expression")
    doc_params = (None,) if doc_expression == "%s" else ()
    clause = f"""EXISTS (
        SELECT 1 FROM insights i
         WHERE i.doc_id={doc_expression} AND i.source_type='SBI'
           AND i.model=%s AND i.prompt_version=%s
        UNION ALL
        SELECT 1 FROM source_facts sf
         WHERE sf.doc_id={doc_expression}
           AND sf.source LIKE %s
        LIMIT 1
    )"""
    return clause, doc_params


def extraction_predicate(doc_id: int, *, model=MODEL, prompt_version=PROMPT_VERSION):
    """Return a point lookup using the canonical completion rule."""
    clause, _ = completion_clause("%s", model=model, prompt_version=prompt_version)
    pattern = f"SBI:doc={doc_id}:page=%:model={model}:prompt={prompt_version}:%"
    # The document placeholder occurs once in each UNION arm.
    params = (doc_id, model, prompt_version, doc_id, pattern)
    return f"SELECT 1 WHERE {clause}", params


def pending_documents_query(*, model=MODEL, prompt_version=PROMPT_VERSION,
                            limit: int | None = None):
    """Select every ledgered SBI document not complete for this model/prompt."""
    clause, _ = completion_clause("d.id", model=model, prompt_version=prompt_version)
    sql = f"""SELECT d.id,d.ipo_id,d.object_key,d.sha256
                FROM documents d
               WHERE d.doc_type='sbi' AND d.ipo_id IS NOT NULL
                 AND d.object_key IS NOT NULL AND NOT {clause}
               ORDER BY d.fetched_at,d.id"""
    params: tuple[Any, ...] = (
        model, prompt_version,
        f"SBI:doc=%:page=%:model={model}:prompt={prompt_version}:%",
    )
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be zero or greater")
        sql += " LIMIT %s"
        params += (limit,)
    return sql, params


def already_extracted(conn, doc_id: int) -> bool:
    cur = conn.cursor()
    try:
        sql, params = extraction_predicate(doc_id)
        cur.execute(sql, params)
        return cur.fetchone() is not None
    finally:
        close = getattr(cur, "close", None)
        if close:
            close()


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
                        doc_id=doc_id, confidence=(fact.get("confidence") if fact.get("confidence") is not None else 1.0), commit=False)
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
