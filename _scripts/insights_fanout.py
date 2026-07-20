#!/usr/bin/env python3
"""_scripts/insights_fanout.py — PR-A: explode Sonnet full_json into ipo_insights.

Zero new Anthropic spend: mines evidence the caps already paid for. Pure
extraction (`fanout`) is separated from the writer (`store_insights`) so the
mapping is unit-testable offline.

Provenance rule (operating directive): an insight row exists ONLY with its
source excerpt — a claim without the RHP's words never becomes a row. Rows
supersede (is_current=false), never delete.
"""
from __future__ import annotations

from typing import Any

RHP = "RHP"

# (json_path, category, direction_fn) — direction derives from the flag, the
# STATEMENT is always the model's own quoted detail. No detail → no row.
def _neg_if(flag: Any) -> str:
    return "negative" if flag is True else ("neutral" if flag is False else "incomplete")


def _get(d: dict, *path):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def fanout(full_json: dict) -> list[dict]:
    """full_json (rhp_sonnet output) -> list of insight dicts (no ipo_id/run
    metadata — the writer adds those). Every row carries source_excerpt."""
    rows: list[dict] = []

    def add(category: str, direction: str, statement: str, excerpt: str, locator: str | None = None):
        statement = (statement or "").strip()
        excerpt = (excerpt or "").strip()
        if not statement or not excerpt:
            return  # provenance rule: no excerpt, no row
        rows.append({"category": category, "direction": direction,
                     "statement": statement[:300], "source_type": RHP,
                     "source_excerpt": excerpt[:500], "source_locator": locator})

    # structure / OFS — the exact field the #262 UI repair reads
    st = _get(full_json, "structure") or {}
    if isinstance(st, dict) and st.get("detail"):
        add("structure", _neg_if(st.get("ofs_heavy")), st["detail"], st["detail"])

    uop = _get(full_json, "use_of_proceeds") or {}
    if isinstance(uop, dict) and uop.get("detail"):
        # vague/repayment-heavy proceeds read negative only if the model flagged it
        add("use_of_proceeds", _neg_if(uop.get("flag")), uop["detail"], uop["detail"])

    pledge = _get(full_json, "promoter_pledge") or {}
    if isinstance(pledge, dict) and pledge.get("detail"):
        add("governance", _neg_if(pledge.get("flag")), pledge["detail"], pledge["detail"])

    skin = _get(full_json, "promoter_skin") or {}
    if isinstance(skin, dict) and skin.get("detail"):
        add("governance", "neutral", skin["detail"], skin["detail"])

    risks = full_json.get("top_3_material_risks")
    if isinstance(risks, list):
        for r in risks:
            if isinstance(r, str) and r.strip():
                add("risk", "negative", r, r)
            elif isinstance(r, dict) and (r.get("risk") or r.get("detail")):
                add("risk", "negative", r.get("risk") or r.get("detail"),
                    r.get("quote") or r.get("detail") or r.get("risk"), r.get("section"))
    return rows


def store_insights(cur, ipo_id: int, rows: list[dict], *, analysis_run_id: str,
                   analysis_model: str | None, pdf_sha256: str | None,
                   source_url: str | None = None) -> int:
    """Supersede prior current RHP insights for this ipo, insert the new set.
    Caller owns the transaction. Returns rows written."""
    cur.execute("""UPDATE ipo_insights SET is_current = FALSE
                   WHERE ipo_id = %s AND source_type = %s AND is_current""",
                (ipo_id, RHP))
    n = 0
    for r in rows:
        cur.execute("""INSERT INTO ipo_insights
            (ipo_id, category, statement, direction, source_type, source_name,
             source_document_id, source_url, source_locator, source_excerpt,
             analysis_model, analysis_run_id, is_current)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)""",
            (ipo_id, r["category"], r["statement"], r["direction"], RHP,
             "rhp_sonnet", pdf_sha256, source_url, r.get("source_locator"),
             r["source_excerpt"], analysis_model, analysis_run_id))
        n += 1
    return n
