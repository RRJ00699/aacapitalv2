"""Deterministic PDF extraction and offline ipo-profile:v1 assembly.

The production caller must pass bytes returned by the verified document-store read.
No model is invoked here; optional qualitative analysis is merged only into the five
AI-owned fields and cannot replace facts carrying document/page provenance.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import fitz

SCHEMA_VERSION = "ipo-profile:v1"
AI_FIELDS = frozenset({"qualitative_risk", "governance", "rhp_verdict", "sbi_verdict", "business_quality"})
MONEY = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)", re.I)

@dataclass(frozen=True)
class Page:
    number: int
    text: str

def verified_pdf_pages(body: bytes, *, expected_sha256: str) -> list[Page]:
    """Hash-check an R2 response before parsing; this is the extraction trust boundary."""
    import hashlib
    if hashlib.sha256(body).hexdigest() != expected_sha256:
        raise ValueError("verified object read failed: sha256 mismatch")
    if not body.startswith(b"%PDF-"):
        raise ValueError("verified object read failed: invalid PDF")
    with fitz.open(stream=body, filetype="pdf") as document:
        return [Page(i + 1, page.get_text("text")) for i, page in enumerate(document)]

def _fact(value: Any, doc_id: int, page: Page, excerpt: str) -> dict[str, Any]:
    return {"classification": "VERIFIED_FACT", "value": value, "provenance": {"document_id": doc_id, "page": page.number, "excerpt": excerpt.strip()[:500]}}

def _first(pages: Iterable[Page], pattern: str, doc_id: int, flags=re.I) -> dict[str, Any] | None:
    rx = re.compile(pattern, flags)
    for page in pages:
        match = rx.search(page.text)
        if match:
            return _fact(match.group(1).strip(), doc_id, page, match.group(0))
    return None

def extract_rhp(pages: list[Page], doc_id: int) -> dict[str, Any]:
    """Conservative labels-first extraction. Missing labels remain UNKNOWN."""
    fields = {
        "company": _first(pages, r"(?:name of (?:our )?company|issuer)\s*[:\-]\s*([^\n]+)", doc_id),
        "fresh_issue": _first(pages, r"fresh issue[^\n]{0,80}?(?:₹|Rs\.?|INR)\s*([\d,.]+\s*(?:crore|cr))", doc_id),
        "ofs": _first(pages, r"offer for sale[^\n]{0,80}?(?:₹|Rs\.?|INR)\s*([\d,.]+\s*(?:crore|cr))", doc_id),
        "eps": _first(pages, r"(?:diluted\s+)?EPS\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,.()\-]+)", doc_id),
        "nav": _first(pages, r"(?:NAV|net asset value per equity share)\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,.()\-]+)", doc_id),
        "ronw": _first(pages, r"(?:RoNW|return on net worth)\s*[:\-]?\s*([\d,.()\-]+%?)", doc_id),
        "debt": _first(pages, r"(?:total borrowings|total debt)\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,.()\-]+)", doc_id),
        "cash": _first(pages, r"cash and cash equivalents\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,.()\-]+)", doc_id),
        "interest_expense": _first(pages, r"(?:finance costs|interest expense)\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,.()\-]+)", doc_id),
    }
    # Evidence-rich sections are retained without pretending prose is a numeric fact.
    sections = {}
    for key, heading in {"objects":"objects of the offer", "litigation":"outstanding litigation", "contingent_liabilities":"contingent liabilities", "related_businesses":"related party transactions", "peers":"comparison with listed industry peers"}.items():
        hit = _first(pages, rf"({heading}[^\n]*(?:\n[^\n]+){{0,8}})", doc_id)
        if hit: sections[key] = hit
    return {**{k:v for k,v in fields.items() if v}, **sections}

def extract_anchor(pages: list[Page], doc_id: int) -> list[dict[str, Any]]:
    rows=[]
    rx=re.compile(r"^\s*(.+?)\s{2,}([\d,]+)\s{2,}(?:₹|Rs\.?)?\s*([\d,.]+)\s{2,}([\d.]+%)\s*$")
    for page in pages:
        for line in page.text.splitlines():
            match=rx.match(line)
            if match:
                rows.append(_fact({"investor":match[1],"shares":int(match[2].replace(",","")),"amount":match[3],"allocation_pct":match[4]},doc_id,page,line))
    return rows

def extract_sbi(pages: list[Page], doc_id: int) -> dict[str, Any]:
    return {k:v for k,v in {
        "rating":_first(pages,r"(?:recommendation|rating)\s*[:\-]\s*([^\n]+)",doc_id),
        "fair_value":_first(pages,r"(?:fair value|target price)\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,.]+)",doc_id),
        "valuation_observation":_first(pages,r"(at the (?:upper|lower) price band[^\n]+)",doc_id),
    }.items() if v}

def build_profile(*, ipo_id: int, isin: str, identity: dict[str, Any], documents: list[dict[str, Any]], rhp: dict[str, Any] | None=None, anchor: list[dict[str, Any]] | None=None, sbi: dict[str, Any] | None=None, ai: dict[str, Any] | None=None, generated_at: str | None=None) -> dict[str, Any]:
    if ipo_id <= 0 or not re.fullmatch(r"IN[A-Z0-9]{9}[0-9]", isin): raise ValueError("verified ipo_id and ISIN are required")
    rejected=set(ai or {})-AI_FIELDS
    if rejected: raise ValueError(f"AI attempted to write deterministic fields: {sorted(rejected)}")
    rhp=rhp or {}; sbi=sbi or {}
    empty={"state":"UNKNOWN","reason":"not deterministically extracted"}
    return {"schema_version":SCHEMA_VERSION,"ipo_id":ipo_id,"isin":isin,"identity":identity,"company":rhp.get("company",empty),"promoters":[],"business":empty,"issue":{"fresh":rhp.get("fresh_issue",empty),"ofs":rhp.get("ofs",empty)},"timetable":{},"objects":rhp.get("objects",empty),"expenses":empty,"selling_shareholders":[],"shareholding":empty,"reservation":empty,"anchor":anchor or [],"subscriptions":[],"financials":{"debt":rhp.get("debt",empty),"cash":rhp.get("cash",empty),"interest_expense":rhp.get("interest_expense",empty)},"kpis":{"eps":rhp.get("eps",empty),"nav":rhp.get("nav",empty),"ronw":rhp.get("ronw",empty)},"peers":rhp.get("peers",empty),"documents":documents,"rhp_analysis":{k:v for k,v in (ai or {}).items() if k in {"qualitative_risk","governance","rhp_verdict","business_quality"}},"sbi_analysis":{**sbi,**({"sbi_verdict":ai["sbi_verdict"]} if ai and "sbi_verdict" in ai else {})},"economic_transformations":[],"valuation":{"status":"INSUFFICIENT_DATA"},"listing":{},"market":{},"provenance":{"deterministic":True,"ai_fields":sorted(set(ai or {}))},"generated_at":generated_at or dt.datetime.now(dt.timezone.utc).isoformat()}

def main() -> None:
    parser=argparse.ArgumentParser(description="Bounded offline ipo-profile:v1 builder")
    parser.add_argument("--input",type=Path,required=True,help="JSON array of already verified/extracted IPO inputs")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--ipo-id",type=int)
    parser.add_argument("--limit",type=int,default=25)
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    if not 1 <= args.limit <= 100: parser.error("--limit must be between 1 and 100")
    rows=json.loads(args.input.read_text())
    selected=[r for r in rows if args.ipo_id is None or r["ipo_id"]==args.ipo_id][:args.limit]
    profiles=[build_profile(**r) for r in selected]
    report={"selected":len(selected),"profiles":profiles if not args.dry_run else [],"dry_run":args.dry_run}
    rendered=json.dumps(report,indent=2)
    if args.output and not args.dry_run: args.output.write_text(rendered)
    print(rendered)

if __name__ == "__main__": main()
