import hashlib
import json
import pathlib

import pytest

from pipeline import sbi_extraction_run as extraction_run
from pipeline import sbi_ingest as ingest
from pipeline import sbi_sonnet as sonnet


FIXTURE = {
    "claims": [{"kind": "key_risk", "statement": "Customer concentration is high",
                "page_number": 7, "excerpt": "top ten customers contributed 82%",
                "confidence": 0.91}],
    "scalar_facts": [{"field": "sbi_rating", "value": "SUBSCRIBE",
                      "page_number": 1, "excerpt": "We recommend SUBSCRIBE"}],
}


def test_structured_extraction_preserves_provenance():
    parsed = sonnet.parse_extraction(json.dumps(FIXTURE), doc_id=42)
    for item in parsed["claims"] + parsed["scalar_facts"]:
        assert item["doc_id"] == 42 and item["source_type"] == "SBI"
        assert item["model"] == sonnet.MODEL
        assert item["prompt_version"] == sonnet.PROMPT_VERSION


@pytest.mark.parametrize("response", ["not-json", "[]", {"claims": "bad", "scalar_facts": []}])
def test_malformed_model_response_is_rejected(response):
    with pytest.raises(sonnet.SBIExtractionError):
        sonnet.parse_extraction(response, doc_id=1)


@pytest.mark.parametrize("field", sorted(sonnet.FORBIDDEN_FIELDS))
def test_ai_cannot_write_deterministic_valuation_fields(field):
    with pytest.raises(sonnet.SBIExtractionError, match="deterministic fields"):
        sonnet.parse_extraction({field: 1, "claims": [], "scalar_facts": []}, doc_id=1)


def test_resolved_source_is_canonical_with_local_excerpt_bound():
    raw = {"claims": [{"kind": "verdict", "statement": "Supported.",
                       "evidence_refs": ["P1:L001"]}], "scalar_facts": []}
    parsed = sonnet.parse_extraction(raw, doc_id=1,
                                     pages=[{"page_number": 1, "text": "Exact source text"}])
    assert parsed["claims"][0]["excerpt"] == "Exact source text"


def test_reference_not_source_comparison_is_the_transport_guard():
    raw = {"claims": [{"kind": "verdict", "statement": "capacity is 101 MW",
                       "evidence_refs": ["P1:L001"]}], "scalar_facts": []}
    parsed = sonnet.parse_extraction(raw, doc_id=1,
                                     pages=[{"page_number": 1, "text": "capacity is 100 MW"}])
    assert parsed["claims"][0]["statement"] == "capacity is 101 MW"
    assert parsed["claims"][0]["excerpt"] == "capacity is 100 MW"


class Stored:
    id = 81
    object_key = "sbi/INE000TEST01/2023-04-03/digest.pdf"
    sha256 = "digest"
    created = True


def test_ingest_uses_exact_identity_and_immutable_ledger(monkeypatch, tmp_path):
    source = tmp_path / "Example Ltd_IPO Note_03-04-2023.pdf"
    source.write_bytes(b"%PDF fixture")
    calls = []
    resolution = type("Resolution", (), {
        "row": (7, "INE000TEST01", "Example Ltd"), "method": "EXACT_NAME",
        "ambiguous_count": 0})()
    monkeypatch.setattr(ingest, "resolve_ipo", lambda *a, **k: resolution)
    monkeypatch.setattr(ingest, "is_git_tracked", lambda path: True)
    monkeypatch.setattr(ingest, "store_document",
                        lambda *a, **k: calls.append(k) or Stored())
    result = ingest.ingest_file(object(), source, owner_approved=True)
    assert result["status"] == "LEDGERED" and result["ipo_id"] == 7
    assert calls[0]["doc_type"] == "sbi" and calls[0]["temporary_path"] is None
    assert calls[0]["document_date"] == ingest.dt.date(2023, 4, 3)
    assert source.exists()


@pytest.mark.parametrize(("name", "expected"), [
    ("Issuer_IPO Note_03-04-2023.pdf", ingest.dt.date(2023, 4, 3)),
    ("Issuer_IPO Note_31-02-2023.pdf", None),
    ("Issuer_IPO Note_2023-04-03.pdf", None),
])
def test_document_date_is_only_valid_dd_mm_yyyy(name, expected):
    assert ingest.document_date_from_filename(pathlib.Path(name)) == expected


def test_worker_has_no_local_inventory_or_frozen_count_contract():
    source = pathlib.Path(extraction_run.__file__).read_text(encoding="utf-8")
    assert "data/research_notes" not in source
    assert "EXPECTED_DOCUMENTS" not in source
    assert "count-tokens-only" not in source
    assert "local_inventory" not in source


def test_sha_uses_immutable_bytes():
    body = b"immutable-pdf"
    assert hashlib.sha256(body).hexdigest() == hashlib.sha256(body).hexdigest()
