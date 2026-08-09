import hashlib
import json
import pathlib
import runpy
import sys
import types

import pytest

from pipeline import sbi_migration_verify as verify
from pipeline import sbi_sonnet as sonnet
from pipeline import sbi_ingest as ingest
from pipeline import sbi_bounded_ingest as bounded
from pipeline import company_identity


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


def test_verifier_reports_every_required_status_without_collapsing_categories():
    rows = [{"status": status} for status in verify.STATUSES]
    counts = verify.aggregate(rows)
    assert counts["TOTAL"] == len(verify.STATUSES)
    assert set(counts) == {"TOTAL", "RESOLVED_IPO", "AMBIGUOUS_IDENTITY", *verify.STATUSES}
    assert all(counts[status] == 1 for status in verify.STATUSES)


def test_remote_preflight_has_zero_write_and_model_budget(tmp_path):
    note = tmp_path / "note.pdf"
    note.write_bytes(b"%PDF-1.7\nfixture\n%%EOF")
    budget = verify.preflight(verify.local_inventory(tmp_path))
    assert budget["tracked_pdf_count"] == 1
    assert budget["r2_put_count"] == budget["neon_writes"] == budget["sonnet_calls"] == 0


def test_bounded_unresolved_report_separates_ambiguous_from_no_match():
    identity_rows = (
        (1, "ISIN1", "Example Limited", "example limited"),
        (2, "ISIN2", "Example Ltd", "example ltd"),
        (3, "ISIN3", "Different Industries", "different industries"),
    )
    rows = [
        {"local_path": "data/research_notes/Example Company_IPO Note.pdf",
         "status": "IPO_UNRESOLVED", "identity_ambiguous_count": 2},
        {"local_path": "data/research_notes/Unknown Holdings_IPO Note.pdf",
         "status": "IPO_UNRESOLVED", "identity_ambiguous_count": 0},
    ]

    report = bounded.unresolved_report(rows, identity_rows)

    assert report[0]["group"] == "AMBIGUOUS"
    assert report[0]["ambiguity_count"] == 2
    assert set(report[0]["closest_name_suggestions_advisory_only"]) == {
        "Example Limited", "Example Ltd"}
    assert report[1]["group"] == "NO_CANONICAL_MATCH"
    assert len(report[1]["closest_name_suggestions_advisory_only"]) == 3
    assert rows[0]["status"] == "IPO_UNRESOLVED" and rows[0].get("ipo_id") is None
    assert rows[1]["status"] == "IPO_UNRESOLVED" and rows[1].get("ipo_id") is None


def test_extraction_failure_is_explicit_and_never_estimated():
    rows = [{"local_path": "data/research_notes/broken.pdf", "bytes": 10,
             "r2_sha_status": "VERIFIED", "extraction_tuple": None}]

    def fail(_path):
        raise RuntimeError("unreadable PDF")

    inventory = bounded.extraction_inventory(rows, extract_text=fail)

    assert inventory["notes"][0]["extraction_status"] == "TEXT_EXTRACTION_FAILED"
    assert inventory["notes"][0]["estimated_input_tokens"] is None
    assert inventory["text_extraction_failed"] == 1
    assert inventory["text_extraction_success"] == 0
    assert inventory["estimated_input_tokens_total"] == 0
    assert inventory["token_estimate_status"] == "LOWER_BOUND / INCOMPLETE"


def test_extraction_inventory_uses_pymupdf_result_without_poppler():
    rows = [{"local_path": "data/research_notes/note.pdf", "bytes": 20,
             "r2_sha_status": "VERIFIED", "extraction_tuple": None}]
    inventory = bounded.extraction_inventory(rows, extract_text=lambda _path: (2, "abcd" * 25))
    note = inventory["notes"][0]

    assert note["extraction_method"] == "PyMuPDF"
    assert note["page_count"] == 2 and note["text_chars"] == 100
    assert note["extraction_status"] == "TEXT_EXTRACTION_SUCCEEDED"
    assert note["estimated_input_tokens"] is not None
    assert inventory["notes_total"] == inventory["text_extraction_success"] == 1
    assert inventory["text_extraction_failed"] == 0
    assert inventory["token_estimate_status"] == "COMPLETE"


def test_preflight_itemizes_document_ledger_reads_and_writes():
    rows = [{"bytes": 10}, {"bytes": 20}, {"bytes": 30}]
    scope = rows[:2]

    preflight = bounded.preflight_contract(rows, scope, pre_ingest_classification_reads=3)
    neon = preflight["expected Neon statements"]

    assert neon == {"identity_set_load": 1,
                    "pre_ingest_classification_reads": 3,
                    "per_document_ledger_select": 2,
                    "per_document_insert": 2,
                    "post_ingest_verification_reads": 5,
                    "expected_total_reads": 11,
                    "expected_total_writes": 2}


def test_next_owner_approval_uses_dynamic_unresolved_count():
    assert "2 unresolved identities" in bounded.next_owner_approval([{}, {}])
    assert "43 unresolved identities" not in bounded.next_owner_approval([{}, {}])


def test_counting_s3_client_counts_actual_wire_methods_only():
    class Client:
        def head_object(self, **kwargs): return {"Metadata": {}}
        def get_object(self, **kwargs): return {"Body": b"pdf"}
        def put_object(self, **kwargs): return {}

    client = bounded.CountingS3Client(Client())
    client.head_object(Key="key")
    client.get_object(Key="key")
    client.put_object(Key="key")

    assert (client.heads, client.gets, client.puts) == (1, 1, 1)


def test_two_pdf_verification_loads_identity_spine_once_and_matches_preflight():
    identity_rows = (
        (1, "ISIN1", "Yatra Online Limited", "yatra online limited"),
        (2, "ISIN2", "Zaggle Prepaid Ocean Services Limited",
         "zaggle prepaid ocean services limited"),
        (3, "ISIN3", "Zaggle Prepaid Ocean Services Ltd",
         "zaggle prepaid ocean services ltd"),
    )
    queries = []

    class Cursor:
        def execute(self, sql, params):
            queries.append(sql.strip())
            self.rows = identity_rows if sql.strip() == company_identity.IDENTITY_SET_SQL else []
        def fetchone(self):
            return None
        def fetchall(self):
            return self.rows
        def close(self):
            pass
    class Connection:
        def cursor(self):
            return Cursor()

    conn = Connection()
    counter = verify.OperationCounter()
    cur = conn.cursor()
    loaded = company_identity.load_company_identity_set(
        cur, execute=lambda sql, params: verify._counted_execute(
            cur, counter, sql, params))
    cur.close()
    inputs = [
        {"local_path": "Yatra Online Ltd_IPO Note.pdf", "local_sha256": "a" * 64,
         "bytes": 1},
        {"local_path": "Zaggle Prepaid Ocean Services Company_IPO Note.pdf",
         "local_sha256": "b" * 64, "bytes": 1},
    ]
    results = [verify.verify_remote(row, conn, object(), counter, loaded)
               for row in inputs]

    assert results[0]["status"] == "LEDGER_MISSING"
    assert results[0]["identity_resolution"] == "CANONICAL_NAME"
    assert results[1]["status"] == "IPO_UNRESOLVED"
    assert results[1]["identity_resolution"] == "AMBIGUOUS"
    assert queries.count(company_identity.IDENTITY_SET_SQL) == 1
    assert counter.neon_reads == 3  # one identity load + one ledger lookup per PDF
    budget = verify.preflight(inputs)["expected_neon_reads"]
    assert budget["components"]["identity_set_load"] == 1
    assert budget["components"]["ledger_lookup"] == 2
    assert budget["total"] == "3 minimum; 7 maximum"


def test_ingest_main_reuses_one_identity_set_for_two_files(monkeypatch):
    identity_rows = ((1, "ISIN1", "Yatra Online Limited", "yatra online limited"),)
    queries = []
    received = []

    class Cursor:
        def execute(self, sql, params):
            queries.append(sql.strip())
        def fetchall(self):
            return identity_rows
        def close(self):
            pass
    class Connection:
        def cursor(self):
            return Cursor()
        def close(self):
            pass
    fake_psycopg2 = types.SimpleNamespace(connect=lambda url: Connection())
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setenv("DATABASE_URL", "postgresql://read-only-fixture")
    monkeypatch.setattr(ingest, "ingest_file", lambda conn, path, **kwargs:
                        received.append(kwargs["identity_rows"]) or {"status": "READY"})

    assert ingest.main(["one.pdf", "two.pdf"]) == 0
    assert queries == [company_identity.IDENTITY_SET_SQL]
    assert received == [identity_rows, identity_rows]


def test_script_mode_imports_start_up_and_reach_real_remote_classification(monkeypatch):
    """The documented file command must not depend on repo-root package imports."""
    root = pathlib.Path(__file__).resolve().parents[1]
    pipeline_dir = root / "pipeline"
    script = pipeline_dir / "sbi_migration_verify.py"
    script_path = str(script)
    search_path = [str(pipeline_dir)] + [
        entry for entry in sys.path
        if entry and pathlib.Path(entry).resolve() != root
        and pathlib.Path(entry).resolve() != pipeline_dir
    ]
    monkeypatch.setattr(sys, "path", search_path)
    for name in ("fill_ipo", "company_identity", "sbi_ingest", "sbi_sonnet", "document_ledger",
                 "document_contract", "r2"):
        monkeypatch.delitem(sys.modules, name, raising=False)

    namespace = runpy.run_path(script_path, run_name="sbi_migration_verify_script_mode")
    assert callable(namespace["company_from_filename"])
    assert callable(namespace["_norm"])

    class Cursor:
        def __init__(self):
            self.result = None
        def execute(self, sql, params):
            self.result = (7, "INE000TEST01", "Example Ltd") if "FROM ipo WHERE name_norm" in sql else None
        def fetchone(self):
            return self.result
        def close(self):
            pass
    class Connection:
        def cursor(self):
            return Cursor()

    row = {"local_path": "data/research_notes/Example Ltd_IPO Note.pdf",
           "local_sha256": "a" * 64, "bytes": 1}
    result = namespace["verify_remote"](
        row, Connection(), object(), namespace["OperationCounter"]())
    assert result["status"] == "LEDGER_MISSING"
    assert "ModuleNotFoundError" not in result.get("error", "")


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


class _Stored:
    id = 81
    object_key = "sbi/INE000TEST01/2023-04-03/digest.pdf"
    sha256 = "digest"
    created = True


def _successful_store(calls):
    def fake_store_document(*args, **kwargs):
        calls.append(kwargs)
        temporary = kwargs.get("temporary_path")
        if temporary is not None:
            pathlib.Path(temporary).unlink()
        return _Stored()
    return fake_store_document


def test_tracked_source_survives_successful_ingest(monkeypatch, tmp_path):
    source = tmp_path / "Example Ltd_IPO Note_03-04-2023.pdf"
    source.write_bytes(b"%PDF-1.7\ntracked\n%%EOF")
    calls = []
    monkeypatch.setattr(ingest, "resolve_ipo", lambda *a, **k: type("R", (), {"row": (7, "INE000TEST01", "Example Ltd")})())
    monkeypatch.setattr(ingest, "is_git_tracked", lambda path: True)
    monkeypatch.setattr(ingest, "store_document", _successful_store(calls))

    result = ingest.ingest_file(object(), source, owner_approved=True)

    assert result["status"] == "LEDGERED" and result["source_retained"] is True
    assert source.exists(), "tracked source was deleted before three-way SHA proof"
    assert calls[0]["temporary_path"] is None
    assert calls[0]["document_date"] == ingest.dt.date(2023, 4, 3)


def test_real_ingest_file_accepts_preloaded_identity_without_extra_identity_sql(monkeypatch, tmp_path):
    source = tmp_path / "Example Ltd_IPO Note.pdf"
    source.write_bytes(b"%PDF-1.7\ntracked\n%%EOF")
    queries, store_calls = [], []

    class Cursor:
        def execute(self, sql, params):
            queries.append(sql)
            raise AssertionError("preloaded identity resolution must not query Neon")
        def close(self):
            pass
    class Connection:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(ingest, "store_document", _successful_store(store_calls))
    identity_rows = ((7, "INE000TEST01", "Example Ltd", "example ltd"),)

    result = ingest.ingest_file(Connection(), source, owner_approved=True,
                                retain_source=True, identity_rows=identity_rows)

    assert result["status"] == "LEDGERED" and result["ipo_id"] == 7
    assert queries == []
    assert source.exists()
    assert store_calls[0]["temporary_path"] is None


def test_ephemeral_source_keeps_post_commit_cleanup_behavior(monkeypatch, tmp_path):
    source = tmp_path / "download.pdf"
    source.write_bytes(b"%PDF-1.7\nephemeral\n%%EOF")
    calls = []
    monkeypatch.setattr(ingest, "resolve_ipo", lambda *a, **k: type("R", (), {"row": (7, "INE000TEST01", "Example Ltd")})())
    monkeypatch.setattr(ingest, "is_git_tracked", lambda path: False)
    monkeypatch.setattr(ingest, "store_document", _successful_store(calls))

    result = ingest.ingest_file(object(), source, owner_approved=True,
                                document_date=ingest.dt.date(2026, 8, 8))

    assert result["status"] == "LEDGERED" and result["source_retained"] is False
    assert not source.exists()
    assert calls[0]["temporary_path"] == source


@pytest.mark.parametrize(("name", "expected"), [
    ("Issuer_IPO Note_03-04-2023.pdf", ingest.dt.date(2023, 4, 3)),
    ("Issuer_IPO Note_31-02-2023.pdf", None),
    ("Issuer_IPO Note_2023-04-03.pdf", None),
    ("Issuer_IPO Note.pdf", None),
])
def test_document_date_uses_only_valid_dd_mm_yyyy(name, expected):
    assert ingest.document_date_from_filename(pathlib.Path(name)) == expected
