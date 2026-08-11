import json

import pytest

from pipeline import sbi_sonnet as sonnet

PAGES = [
    {"page_number": 1, "text": "  exact spacing  \n\nSecond line\nPrinted ... ellipsis"},
    {"page_number": 2, "text": "Other page"},
]


def payload(refs=("P1:L001",)):
    return {"claims": [{"kind": "verdict", "statement": "Paraphrased conclusion.",
                         "evidence_refs": list(refs)}], "scalar_facts": []}


def test_source_units_are_stable_omit_empty_and_preserve_exact_text():
    units, index = sonnet.source_units(PAGES)
    assert [unit["ref"] for unit in units] == ["P1:L001", "P1:L002", "P1:L003", "P2:L001"]
    assert index["P1:L001"]["text"] == "  exact spacing  "
    assert "P1:L003 Printed ... ellipsis" in sonnet.build_page_text(PAGES)


def test_python_derives_exact_excerpt_and_synthetic_page_and_allows_paraphrased_statement():
    parsed = sonnet.parse_extraction(payload(("P1:L001", "P1:L002")), doc_id=7, pages=PAGES)
    assert parsed["claims"][0]["excerpt"] == "  exact spacing  \nSecond line"
    assert parsed["claims"][0]["page_number"] == 1
    assert parsed["claims"][0]["statement"] == "Paraphrased conclusion."


def test_three_bounded_refs_are_allowed_and_four_are_rejected():
    parsed = sonnet.parse_extraction(
        payload(("P1:L001", "P1:L002", "P1:L003")), doc_id=7, pages=PAGES)
    assert parsed["claims"][0]["page_number"] == 1
    pages = [{"page_number": 1, "text": "one\ntwo\nthree\nfour"}]
    with pytest.raises(sonnet.EvidenceReferenceError, match="too many evidence_refs"):
        sonnet.parse_extraction(
            payload(("P1:L001", "P1:L002", "P1:L003", "P1:L004")),
            doc_id=7, pages=pages)


def test_resolved_excerpt_retains_fifteen_word_ceiling():
    short = "valid evidence"
    long = " ".join(f"word{index}" for index in range(16))
    raw = {"claims": [
        {"kind": "verdict", "statement": "Valid.", "evidence_refs": ["P1:L001"]},
        {"kind": "verdict", "statement": "Too long.", "evidence_refs": ["P1:L002"]},
    ], "scalar_facts": []}
    parsed = sonnet.parse_extraction(
        raw, doc_id=7, pages=[{"page_number": 1, "text": f"{short}\n{long}"}])
    assert len(parsed["claims"]) == 1
    assert parsed["dropped_items"] == [
        {"item_type": "claim", "position": 1, "reason": "excerpt exceeds 15 words"}]


@pytest.mark.parametrize(("refs", "reason"), [
    ((), "missing"), (("P9:L001",), "unknown"),
    (("P1:L001", "P1:L001"), "duplicate"),
    (("P1:L002", "P1:L001"), "out-of-order"),
    (("P1:L001", "P1:L003"), "non-contiguous"),
    (("P1:L003", "P2:L001"), "cross-page"),
])
def test_invalid_references_reject_complete_response(refs, reason):
    with pytest.raises(sonnet.SBIExtractionError, match=reason):
        sonnet.parse_extraction(payload(refs), doc_id=1, pages=PAGES)


def test_tool_schema_has_refs_only_and_strict_transport():
    raw = json.dumps(sonnet.SBI_EXTRACTION_TOOL)
    assert "evidence_refs" in raw and '"excerpt"' not in raw and '"page_number"' not in raw
    assert sonnet.SBI_EXTRACTION_TOOL["strict"] is True
    assert sonnet.TOOL_CHOICE["disable_parallel_tool_use"] is True
    assert sonnet.EVIDENCE_TRANSPORT_VERSION == "sbi-evidence-refs-v1"


def test_v14_provenance_keeps_v13_completion_compatibility():
    sql, params = sonnet.pending_documents_query()
    assert sonnet.PROMPT_VERSION == "sbi-v1.4"
    assert sonnet.completion_prompt_versions() == ("sbi-v1.4", "sbi-v1.3")
    assert "sbi-v1.4" in params and "sbi-v1.3" in params
    assert sonnet.EVIDENCE_TRANSPORT_VERSION not in sql
    assert sonnet.EVIDENCE_TRANSPORT_VERSION not in params


def test_explicit_unrelated_version_does_not_gain_legacy_compatibility():
    _, params = sonnet.pending_documents_query(prompt_version="sbi-v1.2")
    assert "sbi-v1.2" in params
    assert "sbi-v1.3" not in params and "sbi-v1.4" not in params


@pytest.mark.parametrize(("field", "value", "line"), [
    ("sbi_rating", "SUBSCRIBE", "We recommend SUBSCRIBE"),
    ("sbi_rating", "NEUTRAL", "Our rating is NEUTRAL"),
    ("sbi_rating", "AVOID", "Recommendation AVOID"),
    ("sbi_rating", "NOT RATED", "The issue is NOT RATED"),
    ("sbi_rating", "NO RATING", "There is NO RATING"),
    ("sbi_fair_value", 100, "Our fair value is 100"),
    ("sbi_target_value", 120, "The target value is 120"),
])
def test_rating_and_value_evidence_guards(field, value, line):
    pages = [{"page_number": 1, "text": line}]
    raw = {"claims": [], "scalar_facts": [{"field": field, "value": value,
                                             "evidence_refs": ["P1:L001"]}]}
    assert sonnet.parse_extraction(raw, doc_id=1, pages=pages)["scalar_facts"]
