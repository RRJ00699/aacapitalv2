"""Bounded offline ipo-profile:v1 producer over canonical V2 facts only.

Extraction ownership is deliberately outside this module:
RHP/SBI -> approved AI extraction writers; anchor -> official anchor document writer.
This module neither reads PDFs nor parses financial facts from prose.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parents[1] / "lib" / "intelligence" / "ipo-profile.schema.json"
AI_FIELDS = frozenset({"qualitative_risk", "governance", "rhp_verdict", "sbi_verdict", "business_quality"})

def profile_schema() -> dict[str, Any]:
    """The checked-in JSON Schema is the sole cross-runtime contract owner."""
    return json.loads(SCHEMA_PATH.read_text())

def validate_profile(profile: dict[str, Any]) -> None:
    """Dependency-free validation of the closed v1 shape defined by JSON Schema."""
    schema = profile_schema()
    missing = set(schema["required"]) - set(profile)
    extra = set(profile) - set(schema["properties"])
    if missing or extra:
        raise ValueError(f"profile schema mismatch; missing={sorted(missing)} extra={sorted(extra)}")
    if profile["schema_version"] != schema["properties"]["schema_version"]["const"]:
        raise ValueError("profile schema_version mismatch")
    if not isinstance(profile["ipo_id"], int) or profile["ipo_id"] <= 0:
        raise ValueError("verified ipo_id is required")
    if not re.fullmatch(schema["properties"]["isin"]["pattern"], profile["isin"]):
        raise ValueError("verified ISIN is required")
    for name, definition in schema["properties"].items():
        expected = definition.get("type")
        if expected == "object" and not isinstance(profile[name], dict): raise ValueError(f"{name} must be object")
        if expected == "array" and not isinstance(profile[name], list): raise ValueError(f"{name} must be array")

def canonical_anchor_facts(documents: list[dict[str, Any]], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept anchor rows only when provenance resolves to an official anchor document."""
    anchor_ids = {d["id"] for d in documents if d.get("doc_type") == "anchor" and d.get("verified") is True}
    return [f for f in facts if f.get("document_id") in anchor_ids]

def build_profile(*, ipo_id: int, isin: str, identity: dict[str, Any], company: dict[str, Any], issue: dict[str, Any],
                  documents: list[dict[str, Any]], financials: dict[str, Any], kpis: dict[str, Any], valuation: dict[str, Any],
                  transformations: list[dict[str, Any]] | None = None, anchor_facts: list[dict[str, Any]] | None = None,
                  rhp_analysis: dict[str, Any] | None = None, sbi_analysis: dict[str, Any] | None = None,
                  ai: dict[str, Any] | None = None, generated_at: str | None = None, **sections: Any) -> dict[str, Any]:
    rejected = set(ai or {}) - AI_FIELDS
    if rejected: raise ValueError(f"AI attempted to write deterministic fields: {sorted(rejected)}")
    profile = {"schema_version":"ipo-profile:v1","ipo_id":ipo_id,"isin":isin,"identity":identity,"company":company,
      "promoters":sections.get("promoters",[]),"business":sections.get("business",{}),"issue":issue,"timetable":sections.get("timetable",{}),
      "objects":sections.get("objects",[]),"expenses":sections.get("expenses",{}),"selling_shareholders":sections.get("selling_shareholders",[]),
      "shareholding":sections.get("shareholding",{}),"reservation":sections.get("reservation",{}),
      "anchor":canonical_anchor_facts(documents,anchor_facts or []),"subscriptions":sections.get("subscriptions",[]),
      "financials":financials,"kpis":kpis,"peers":sections.get("peers",[]),"documents":documents,
      "rhp_analysis":{**(rhp_analysis or {}),**{k:v for k,v in (ai or {}).items() if k in {"qualitative_risk","governance","rhp_verdict","business_quality"}}},
      "sbi_analysis":{**(sbi_analysis or {}),**({"sbi_verdict":ai["sbi_verdict"]} if ai and "sbi_verdict" in ai else {})},
      "economic_transformations":transformations or [],"valuation":valuation,"listing":sections.get("listing",{}),"market":sections.get("market",{}),
      "provenance":{"fact_owners":{"financials":"financial_statements","valuation":"valuation","rhp":"rhp_findings/insights/source_facts","sbi":"ipo_research_notes","anchor":"documents(doc_type=anchor)"}},
      "generated_at":generated_at or dt.datetime.now(dt.timezone.utc).isoformat()}
    validate_profile(profile)
    return profile

def main() -> None:
    parser=argparse.ArgumentParser(description="Bounded canonical-fact ipo-profile:v1 builder")
    parser.add_argument("--input",type=Path,required=True); parser.add_argument("--output",type=Path)
    parser.add_argument("--ipo-id",type=int); parser.add_argument("--limit",type=int,default=25); parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    if not 1 <= args.limit <= 100: parser.error("--limit must be between 1 and 100")
    rows=json.loads(args.input.read_text()); selected=[r for r in rows if args.ipo_id is None or r["ipo_id"]==args.ipo_id][:args.limit]
    profiles=[build_profile(**r) for r in selected]; rendered=json.dumps({"selected":len(selected),"profiles":[] if args.dry_run else profiles,"dry_run":args.dry_run},indent=2)
    if args.output and not args.dry_run: args.output.write_text(rendered)
    print(rendered)

if __name__ == "__main__": main()
