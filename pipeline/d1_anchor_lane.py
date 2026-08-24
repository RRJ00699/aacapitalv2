#!/usr/bin/env python3
"""NSE anchor-allocation PDF -> strict Sonnet facts -> D1, with no PDF retention.

Owner policy: anchor PDFs are transient.  The bytes are hashed for provenance, parsed,
routed to anchor_summary/anchor_allocations and then discarded.  They are never uploaded
to R2 and never inserted into the documents ledger.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any

import pymupdf
from curl_cffi import requests as cffi

from d1_ingest import D1IngestClient, fingerprint
from nse_fetch import fetch_one, prime
from sbi_sonnet import source_units

MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "anchor-v1"
TOOL = "record_anchor_allocation"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def _find_anchor_url(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if "anchor" in str(key).lower() and isinstance(child, str) and ".pdf" in child.lower():
                return child
        for child in value.values():
            found = _find_anchor_url(child)
            if found: return found
    elif isinstance(value, list):
        for child in value:
            found = _find_anchor_url(child)
            if found: return found
    elif isinstance(value, str) and "anchor" in value.lower() and ".pdf" in value.lower():
        return value
    return None


def _absolute(url: str) -> str:
    if url.startswith("//"): return "https:" + url
    if url.startswith("/"): return "https://www.nseindia.com" + url
    return url


def _pages(body: bytes):
    with pymupdf.open(stream=body, filetype="pdf") as doc:
        return [{"page_number": i + 1, "text": page.get_text()} for i, page in enumerate(doc)]


ANCHOR_TOOL = {
    "name": TOOL,
    "description": "Record only anchor-allocation facts explicitly printed in the NSE report.",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "summary": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "shares": {"type": ["integer", "null"]},
                    "amount_cr": {"type": ["number", "null"]},
                    "investor_count": {"type": ["integer", "null"]},
                    "allocation_pct": {"type": ["number", "null"]},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["shares", "amount_cr", "investor_count", "allocation_pct", "evidence_refs"],
            },
            "allocations": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "investor_name_raw": {"type": "string"},
                        "shares": {"type": ["integer", "null"]},
                        "price_rs": {"type": ["number", "null"]},
                        "amount_cr": {"type": ["number", "null"]},
                        "allocation_pct": {"type": ["number", "null"]},
                        "derived_class": {"type": ["string", "null"]},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["investor_name_raw", "shares", "price_rs", "amount_cr", "allocation_pct", "derived_class", "evidence_refs"],
                },
            },
        },
        "required": ["summary", "allocations"],
    },
}

SYSTEM = """Extract only facts explicitly printed in this NSE anchor allocation report.
Use the forced record_anchor_allocation tool once. Never infer an investor, share count,
price, amount, allocation percentage, or investor class. Preserve investor names exactly
as printed. Use one to three contiguous evidence_refs from one page for every summary or
allocation item. If a scalar is absent, return null. Do not calculate missing values.
Do not return prose outside the tool call."""


def _resolve_refs(items: list[dict[str, Any]], pages: list[dict[str, Any]]):
    _, index = source_units(pages)
    out = []
    for position, item in enumerate(items):
        refs = item.get("evidence_refs") or []
        if not isinstance(refs, list) or not refs or len(refs) > 3:
            raise ValueError(f"item {position} invalid evidence_refs")
        try: units = [index[r] for r in refs]
        except KeyError as exc: raise ValueError(f"unknown evidence ref {exc.args[0]}") from exc
        if len({u["page_number"] for u in units}) != 1:
            raise ValueError(f"item {position} cross-page evidence")
        nums = [u["line_number"] for u in units]
        if nums != list(range(nums[0], nums[0] + len(nums))):
            raise ValueError(f"item {position} non-contiguous evidence")
        out.append({**{k:v for k,v in item.items() if k != "evidence_refs"},
                    "page_number": units[0]["page_number"],
                    "evidence_excerpt": "\n".join(u["text"] for u in units)})
    return out


def _call(pages: list[dict[str, Any]], api_key: str):
    units, _ = source_units(pages)
    text = "\n".join(f"{u['ref']} {u['text']}" for u in units)
    payload = {
        "model": MODEL, "system": SYSTEM, "max_tokens": 12000, "temperature": 0,
        "tools": [ANCHOR_TOOL],
        "tool_choice": {"type": "tool", "name": TOOL, "disable_parallel_tool_use": True},
        "messages": [{"role": "user", "content": text}],
    }
    req = urllib.request.Request(MESSAGES_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as res: result = json.load(res)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Anthropic HTTP {exc.code}: {exc.read().decode(errors='replace')[:600]}") from None
    content = result.get("content") or []
    blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == TOOL]
    if result.get("stop_reason") != "tool_use" or len(blocks) != 1 or not isinstance(blocks[0].get("input"), dict):
        raise RuntimeError("anchor extraction did not return exactly one forced tool call")
    usage = result.get("usage") or {}
    return blocks[0]["input"], int(usage.get("input_tokens",0)), int(usage.get("output_tokens",0))


def _ops(ipo_id: int, digest: str, extracted: dict[str, Any], pages: list[dict[str, Any]]):
    summary_items = _resolve_refs([extracted.get("summary") or {}], pages)
    summary = summary_items[0]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    ops = [{
        "op": "anchor_summary_upsert", "ipo_id": ipo_id, "shares": summary.get("shares"),
        "amount_cr": summary.get("amount_cr"), "investor_count": summary.get("investor_count"),
        "allocation_pct": summary.get("allocation_pct"), "document_sha256": digest,
        "observed_at": now,
    }]
    allocations = _resolve_refs(extracted.get("allocations") or [], pages)
    for idx, row in enumerate(allocations, 1):
        name = str(row.get("investor_name_raw") or "").strip()
        if not name: continue
        ops.append({
            "op": "anchor_allocation_insert", "ipo_id": ipo_id, "allocation_row": idx,
            "investor_name_raw": name, "shares": row.get("shares"), "price_rs": row.get("price_rs"),
            "amount_cr": row.get("amount_cr"), "allocation_pct": row.get("allocation_pct"),
            "document_sha256": digest, "page": row.get("page_number"),
            "derived_class": row.get("derived_class"),
        })
    return ops


def run(*, limit: int = 20, apply: bool = False, client: D1IngestClient | None = None):
    client = client or D1IngestClient.from_env()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if apply and not api_key: raise RuntimeError("ANTHROPIC_API_KEY not configured")
    session = prime(cffi)
    report = {"selected": 0, "anchor_urls": 0, "extracted": 0, "allocations": 0,
              "pdfs_retained": 0, "failures": []}
    rows = client.active_ipos(limit=limit, lookback_days=100)
    for row in rows:
        symbol = row.get("nse_symbol")
        if not symbol: continue
        report["selected"] += 1
        try:
            payload = fetch_one(session, str(symbol).upper())
            url = _find_anchor_url(payload)
            if not url: continue
            report["anchor_urls"] += 1
            response = session.get(_absolute(url), timeout=30)
            if response.status_code != 200: raise RuntimeError(f"anchor PDF HTTP {response.status_code}")
            body = bytes(response.content)
            if not body.startswith(b"%PDF-"): raise RuntimeError("anchor response is not PDF")
            digest = hashlib.sha256(body).hexdigest()
            pages = _pages(body)
            if apply:
                extracted, _itok, _otok = _call(pages, api_key)
                ops = _ops(int(row["id"]), digest, extracted, pages)
                client.batch(ops)
                report["extracted"] += 1
                report["allocations"] += max(0, len(ops)-1)
            # no file write, no R2 call, no documents row: bytes die at end of iteration.
            del body
        except Exception as exc:
            report["failures"].append({"ipo_id": row.get("id"), "symbol": symbol,
                                       "error": f"{type(exc).__name__}:{exc}"})
    return report


def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=20); ap.add_argument("--apply",action="store_true")
    a=ap.parse_args(argv); rep=run(limit=max(1,min(a.limit,100)),apply=a.apply)
    print("D1_ANCHOR_SUMMARY="+json.dumps(rep,sort_keys=True,default=str))
    return 1 if rep["failures"] else 0

if __name__ == "__main__": raise SystemExit(main())
