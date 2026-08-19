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


def test_three_ref_resolved_excerpt_of_forty_words_is_accepted():
    """D7: the owner's 08-19 pilot dropped 9 of 10 claims on "excerpt exceeds 15 words".

    Those excerpts were RESOLVED — up to three source lines joined by Python from real
    page bytes. A word budget written to stop paraphrase cannot apply to text the model
    never wrote, and three joined lines of a research note routinely run past fifteen
    words.
    """
    lines = [" ".join(f"word{index}" for index in range(row * 14, row * 14 + 14))
             for row in range(3)]
    raw = {"claims": [{"kind": "verdict", "statement": "Valid.",
                       "evidence_refs": ["P1:L001", "P1:L002", "P1:L003"]}],
           "scalar_facts": []}
    parsed = sonnet.parse_extraction(raw, doc_id=7,
                                     pages=[{"page_number": 1, "text": "\n".join(lines)}])
    assert parsed["dropped_items"] == []
    excerpt = parsed["claims"][0]["excerpt"]
    assert len(excerpt.split()) == 42 > sonnet.MAX_EVIDENCE_WORDS
    assert excerpt == "\n".join(lines)          # byte-true, in order, one page


def test_the_structural_evidence_guarantees_are_unchanged():
    """What actually protects a resolved excerpt: refs, page, order, contiguity."""
    pages = [{"page_number": 1, "text": "one\ntwo\nthree\nfour"},
             {"page_number": 2, "text": "five"}]

    def claim(refs):
        return {"claims": [{"kind": "verdict", "statement": "S.", "evidence_refs": list(refs)}],
                "scalar_facts": []}

    with pytest.raises(sonnet.EvidenceReferenceError, match="too many evidence_refs"):
        sonnet.parse_extraction(claim(["P1:L001", "P1:L002", "P1:L003", "P1:L004"]),
                                doc_id=7, pages=pages)
    with pytest.raises(sonnet.EvidenceReferenceError, match="non-contiguous"):
        sonnet.parse_extraction(claim(["P1:L001", "P1:L003"]), doc_id=7, pages=pages)
    with pytest.raises(sonnet.EvidenceReferenceError, match="cross-page"):
        sonnet.parse_extraction(claim(["P1:L004", "P2:L001"]), doc_id=7, pages=pages)
    with pytest.raises(sonnet.EvidenceReferenceError, match="out-of-order"):
        sonnet.parse_extraction(claim(["P1:L002", "P1:L001"]), doc_id=7, pages=pages)


def test_a_resolved_excerpt_is_still_bounded_by_size():
    """The replacement cap bounds payload, it does not police wording."""
    pages = [{"page_number": 1,
              "text": "kept evidence\n" + "x" * (sonnet.MAX_EVIDENCE_CHARS + 1)}]
    parsed = sonnet.parse_extraction(
        {"claims": [{"kind": "verdict", "statement": "Kept.", "evidence_refs": ["P1:L001"]},
                    {"kind": "verdict", "statement": "Oversized.", "evidence_refs": ["P1:L002"]}],
         "scalar_facts": []}, doc_id=7, pages=pages)
    assert len(parsed["claims"]) == 1
    assert parsed["dropped_items"] == [
        {"item_type": "claim", "position": 1,
         "reason": f"excerpt exceeds {sonnet.MAX_EVIDENCE_CHARS} characters"}]


def test_a_model_authored_excerpt_still_faces_the_word_ceiling():
    """parse_extraction without pages is the model-authored path; paraphrase is capped."""
    parsed = sonnet.parse_extraction(
        {"claims": [
            {"kind": "verdict", "statement": "Valid.", "excerpt": "short evidence",
             "page_number": 1},
            {"kind": "verdict", "statement": "Too long.", "page_number": 1,
             "excerpt": " ".join(f"word{index}" for index in range(16))},
         ], "scalar_facts": []}, doc_id=7)
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


def test_v15_provenance_distinguishes_the_regimes_without_re_paying_for_v14():
    """The identity change must not turn every completed document back into pending."""
    sql, params = sonnet.pending_documents_query()
    assert sonnet.PROMPT_VERSION == "sbi-v1.5"
    assert sonnet.completion_prompt_versions() == ("sbi-v1.5", "sbi-v1.4", "sbi-v1.3")
    assert "sbi-v1.5" in params and "sbi-v1.4" in params and "sbi-v1.3" in params
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
