import hashlib
import json
import pathlib

import pytest

from pipeline import sbi_migration_verify as verify
from pipeline import sbi_sonnet as sonnet


FIXTURE = {
    "claims": [{"kind": "key_risk", "statement": "Customer concentration is high",
                "page_number": 7, "excerpt": "top ten customers contributed 82%",
                "confidence": 0.91}],
    "scalar_facts": [{"field": "sbi_rating", "value": "SUBSCRIBE",
                      "page_number": 1, "excerpt": "We recommend SUBSCRIBE"}],
}


def test_structured_extraction_preserves_required_provenance():
    parsed = sonnet.parse_extraction(json.dumps(FIXTURE), doc_id=42)
    for item in parsed["claims"] + parsed["scalar_facts"]:
        assert item["doc_id"] == 42
        assert item["page_number"] >= 1 and item["excerpt"]
        assert item["source_type"] == "SBI"
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


def test_missing_page_or_excerpt_is_rejected():
    bad = json.loads(json.dumps(FIXTURE))
    bad["claims"][0].pop("excerpt")
    with pytest.raises(sonnet.SBIExtractionError, match="statement/excerpt"):
        sonnet.parse_extraction(bad, doc_id=1)


def test_deterministic_model_stub_and_central_identity():
    calls = []
    def stub(**kwargs):
        calls.append(kwargs)
        return FIXTURE
    result = sonnet.extract(doc_id=9, pages=[{"page_number": 1, "text": "fixture"}],
                            model_client=stub)
    assert result["scalar_facts"][0]["value"] == "SUBSCRIBE"
    assert calls[0]["model"] == sonnet.MODEL
    assert calls[0]["prompt_version"] == sonnet.PROMPT_VERSION


def test_local_verifier_hashes_pdf_without_remote_io(tmp_path):
    body = b"%PDF-1.7\nfixture\n%%EOF"
    path = tmp_path / "Example Ltd_IPO Note.pdf"
    path.write_bytes(body)
    rows = verify.local_inventory(tmp_path)
    assert rows[0]["local_sha256"] == hashlib.sha256(body).hexdigest()
    assert verify.aggregate(rows)["TOTAL"] == 1


def test_production_lane_has_no_legacy_parser_or_tracked_runtime_path():
    root = pathlib.Path(__file__).resolve().parents[1]
    production = "\n".join((root / p).read_text(encoding="utf-8") for p in (
        "pipeline/sbi_sonnet.py", "pipeline/sbi_ingest.py", "pipeline/cron.py",
        "_scripts/job_runner.py", ".github/workflows/sbi-notes.yml"))
    assert "parse_sbi_notes" not in production
    assert "data/research_notes" not in production
    assert "store_document(" in (root / "pipeline/sbi_ingest.py").read_text()


def test_legacy_sbi_parse_absent_from_all_job_catalogs():
    root = pathlib.Path(__file__).resolve().parents[1]
    for path in ("_scripts/job_runner.py", "app/api/admin/jobs/route.ts",
                 "app/dashboard/admin/AdminConsoleClient.tsx"):
        assert "sbi_parse" not in (root / path).read_text(encoding="utf-8")
