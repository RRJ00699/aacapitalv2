"""Pure routing from already-validated model output into D1 ingest operations.

No network and no database access live here.  RHP and SBI model transports stay in their
existing evidence-tested modules; this file only maps their normalized output to the D1
functional model.  Unsupported/missing facts remain absent rather than guessed.
"""
from __future__ import annotations

import hashlib
import json
from statistics import median
from typing import Any

from d1_ingest import fingerprint
from rhp_writer import normalize_canonical_fact, to_crore


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fact_op(*, ipo_id: int, field: str, raw_value: Any, normalized: Any,
             unit: str | None, source: str, document_sha256: str | None,
             observed_at: str, parser_version: str, confidence: Any = None):
    fp = fingerprint("fact", ipo_id, field, normalized, unit, source, document_sha256,
                     observed_at, parser_version)
    return {
        "op": "source_fact_insert", "ipo_id": ipo_id,
        "target_table": "source_facts", "target_field": field,
        "raw_value": raw_value, "normalized_value": normalized, "unit": unit,
        "source_name": source, "document_sha256": document_sha256,
        "observed_at": observed_at, "parser_version": parser_version,
        "confidence": confidence, "observation_fingerprint": fp,
    }


def rhp_ops(*, ipo_id: int, document_sha256: str, data: dict[str, Any],
            model: str, prompt_version: str, observed_at: str,
            input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0):
    """Route source-backed RHP output.  Qualitative prose stays in extraction_runs.

    The legacy RHP prompt is rich but not reference-ID forced like SBI.  We therefore
    route only fields that carry their own page/excerpt or are structured table values;
    the complete normalized response is retained in extraction_runs for inspection.
    """
    ops: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    st = data.get("structured") or {}
    default_unit = st.get("unit_as_printed")

    # Financial statement rows are accepted only with an explicit period/basis/page and
    # use the same unit conversion discipline as the battle-tested Postgres writer.
    money = {
        "revenue_from_operations": "revenue_cr", "total_income": "total_income_cr",
        "ebitda": "ebitda_cr", "pat": "pat_cr", "net_worth": "net_worth_cr",
        "total_debt": "debt_cr", "total_assets": "assets_cr", "cash": "cash_cr",
    }
    for row in st.get("financials") or []:
        period, basis, page = row.get("period"), row.get("basis"), row.get("page")
        excerpt = str(row.get("excerpt") or "").strip()
        if not period or basis not in {"consolidated", "standalone"} or not isinstance(page, int) or not excerpt:
            skipped.append({"kind": "financial", "period": period, "reason": "missing_period_basis_page_excerpt"})
            continue
        op = {"op": "financial_upsert", "ipo_id": ipo_id, "period": period,
              "basis": basis, "document_sha256": document_sha256, "page": page}
        for src, dst in money.items():
            if row.get(src) is None:
                continue
            converted, note = to_crore(row[src], row.get("unit_as_printed") or default_unit)
            if note:
                skipped.append({"kind": "financial", "period": period, "field": src, "reason": note})
            else:
                op[dst] = converted
        ops.append(op)

    # Canonical facts carry their own printed unit/page/excerpt.  Store normalized crore
    # value plus the exact printed value/unit for provenance.
    for field, fact in (st.get("canonical_facts") or {}).items():
        normalized, note = normalize_canonical_fact(fact)
        if note:
            skipped.append({"kind": "canonical_fact", "field": field, "reason": note})
            continue
        ops.append(_fact_op(
            ipo_id=ipo_id, field=field, raw_value=fact.get("value"), normalized=normalized,
            unit="crore", source="rhp", document_sha256=document_sha256,
            observed_at=observed_at, parser_version=prompt_version,
            confidence=data.get("confidence"),
        ))
        # Objects-of-issue facts remain inspectable as rows, without converting intent to earnings.
        if field in {"debt_repayment_cr", "capex_cr"}:
            ops.append({
                "op": "object_upsert", "ipo_id": ipo_id,
                "row_order": 100 if field == "debt_repayment_cr" else 110,
                "purpose_code": "DEBT_REPAYMENT" if field == "debt_repayment_cr" else "CAPEX",
                "purpose_raw": str(fact.get("excerpt")), "amount_cr": normalized,
                "document_sha256": document_sha256, "page": fact.get("page"),
            })

    # KPI values are scalar source facts.  Page/excerpt are required because this prompt
    # is not evidence-ref forced.
    kpi = st.get("kpi") or {}
    kpage, kexcerpt = kpi.get("page"), str(kpi.get("excerpt") or "").strip()
    if isinstance(kpage, int) and kexcerpt:
        for src, target, unit in (
            ("roe_pct", "roe_pct", "pct"), ("ronw_pct", "ronw_pct", "pct"),
            ("roce_pct", "roce_pct", "pct"), ("nav_per_share", "nav_per_share", "rs/share"),
            ("eps_basic_pre", "eps_pre", "rs/share"), ("eps_post", "eps_post", "rs/share"),
            ("ebitda_margin_pct", "ebitda_margin_pct", "pct"),
            ("pat_margin_pct", "pat_margin_pct", "pct"),
        ):
            value = _num(kpi.get(src))
            if value is not None:
                ops.append(_fact_op(ipo_id=ipo_id, field=target, raw_value=value,
                    normalized=value, unit=unit, source="rhp", document_sha256=document_sha256,
                    observed_at=observed_at, parser_version=prompt_version,
                    confidence=data.get("confidence")))

    # Peer table: preserve each peer.  Median is recalculated from >=3 actual peer P/Es;
    # do not trust a model-generated 'median of two'.
    pa = st.get("peer_analysis") or {}
    ppage, pexcerpt = pa.get("page"), str(pa.get("excerpt") or "").strip()
    pe_values: list[float] = []
    if isinstance(ppage, int) and pexcerpt:
        for peer in pa.get("peers") or []:
            name = str(peer.get("name") or "").strip()
            if not name:
                continue
            pe = _num(peer.get("pe"))
            if pe is not None:
                pe_values.append(pe)
            ops.append({
                "op": "peer_upsert", "ipo_id": ipo_id, "peer_name_raw": name,
                "pe_x": pe, "pb_x": _num(peer.get("pb")),
                "ronw_pct": _num(peer.get("ronw_pct")), "as_of_date": pa.get("as_of_date"),
                "document_sha256": document_sha256, "page": ppage,
            })
        if len(pe_values) >= 3:
            med = float(median(pe_values))
            ops.append(_fact_op(ipo_id=ipo_id, field="peer_median_pe", raw_value=med,
                normalized=med, unit="x", source="rhp", document_sha256=document_sha256,
                observed_at=observed_at, parser_version=prompt_version,
                confidence=data.get("confidence")))

    # Price-band facts may arrive in an RHP supplement.  NSE remains authoritative for
    # ipo_issue; RHP band is retained only as provenance, never used to overwrite NSE.
    band = st.get("issue_price_band") or {}
    if isinstance(band.get("page"), int) and str(band.get("excerpt") or "").strip():
        for field in ("floor", "cap", "face_value"):
            value = _num(band.get(field))
            if value is not None:
                ops.append(_fact_op(ipo_id=ipo_id, field=f"rhp_price_{field}", raw_value=value,
                    normalized=value, unit="rs/share", source="rhp", document_sha256=document_sha256,
                    observed_at=observed_at, parser_version=prompt_version,
                    confidence=data.get("confidence")))

    status = "EXTRACTED_WITH_DROPS" if skipped else "EXTRACTED"
    efp = fingerprint("extract", document_sha256, model, prompt_version)
    ops.append({
        "op": "extraction_run_insert", "ipo_id": ipo_id,
        "document_sha256": document_sha256, "source_type": "RHP",
        "model": model, "prompt_version": prompt_version, "extracted_at": observed_at,
        "status": status, "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": cost_usd, "output_json": {**data, "_d1_route_skipped": skipped},
        "extraction_fingerprint": efp,
    })
    return ops, skipped


def sbi_ops(*, ipo_id: int, document_sha256: str, parsed: dict[str, Any],
            model: str, prompt_version: str, observed_at: str,
            raw_output: Any, input_tokens: int, output_tokens: int, cost_usd: Any):
    """Route SBI's strict evidence-resolved claims and scalar facts."""
    ops: list[dict[str, Any]] = []
    for claim in parsed.get("claims") or []:
        statement = str(claim.get("statement") or "").strip()
        excerpt = str(claim.get("excerpt") or "").strip()
        if not statement or not excerpt or not isinstance(claim.get("page_number"), int):
            continue
        cfp = fingerprint("sbi-finding", ipo_id, document_sha256, claim.get("kind"),
                          statement, excerpt, claim.get("page_number"), prompt_version)
        direction = {
            "key_positive": "positive", "key_risk": "negative",
            "valuation_observation": "neutral", "business_observation": "neutral",
            "verdict": "neutral",
        }.get(claim.get("kind"), "neutral")
        ops.append({
            "op": "research_finding_insert", "ipo_id": ipo_id,
            "category": claim.get("kind"), "finding_text": statement, "direction": direction,
            "document_sha256": document_sha256, "page": claim.get("page_number"),
            "evidence_excerpt": excerpt, "model": model, "prompt_version": prompt_version,
            "confidence": claim.get("confidence"), "content_fingerprint": cfp,
        })
    for fact in parsed.get("scalar_facts") or []:
        field = str(fact.get("field") or "").strip()
        if not field:
            continue
        ops.append(_fact_op(ipo_id=ipo_id, field=field, raw_value=fact.get("value"),
            normalized=fact.get("value"), unit=None, source="sbi", document_sha256=document_sha256,
            observed_at=observed_at, parser_version=prompt_version,
            confidence=fact.get("confidence")))
    dropped = parsed.get("dropped_items") or []
    status = "EXTRACTED_WITH_DROPS" if dropped else "EXTRACTED"
    efp = fingerprint("extract", document_sha256, model, prompt_version)
    ops.append({
        "op": "extraction_run_insert", "ipo_id": ipo_id,
        "document_sha256": document_sha256, "source_type": "SBI",
        "model": model, "prompt_version": prompt_version, "extracted_at": observed_at,
        "status": status, "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": str(cost_usd), "output_json": {"raw": raw_output, "parsed": parsed},
        "extraction_fingerprint": efp,
    })
    return ops
