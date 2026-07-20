#!/usr/bin/env python3
"""Phase-6 (PR-B) tests: evidence rows flow payload -> card with provenance.
The modified cards query EXECUTES against Postgres via test_api_contract's
fixtures; here: payload contract + IpoCard evidence-gating contracts."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _read(*p):
    return open(os.path.join(REPO, *p), encoding="utf-8").read()


def test_payload_carries_current_insights_only():
    src = _read("app", "api", "ipo-command", "route.ts")
    assert "FROM ipo_insights s" in src
    assert "s.ipo_id = ii.id AND s.is_current" in src, "superseded rows must never reach the UI"
    for k in ("'category'", "'direction'", "'statement'", "'excerpt'", "'source'", "'locator'"):
        assert k in src


def test_card_risks_prefer_insights_with_fallback():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert 'i.category === "risk" && i.direction === "negative"' in src
    assert "top_3_material_risks" in src, "legacy fallback must survive until fan-out has run"
    assert src.index("insRisks.length") < src.index("top_3_material_risks"), "insights take precedence"


def test_card_ofs_prefers_structure_insight():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert 'i.category === "structure"' in src
    assert 'stIns.direction === "negative"' in src
    # non-negative evidence suppresses BOTH the negative and the pending line
    assert "not a confirmed negative" in src


def test_quoted_badge_carries_the_excerpt():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert "RHP · quoted" in src
    assert re.search(r'title=\{`RHP\$\{r\.loc', src), "hover must show locator + the source's words"


def test_no_unbadged_rhp_claims_reintroduced():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert "mostly promoter cash-out, not growth capital" not in src
