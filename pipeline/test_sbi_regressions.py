"""Preserved SBI safety contracts that remain valid after orchestration redesign."""
import json
import pathlib
import sys
import types

import pytest

from pipeline import (company_identity, cron, sbi_bounded_ingest as bounded,
                      sbi_extraction_run as run, sbi_ingest as ingest,
                      sbi_migration_verify as verify, sbi_sonnet as sonnet)


CLAIM = {"kind": "verdict", "statement": "Supported.",
         "excerpt": "Exact supporting evidence", "page_number": 1}
FACT = {"field": "sbi_rating", "value": "SUBSCRIBE",
        "excerpt": "We recommend SUBSCRIBE", "page_number": 1}


@pytest.mark.parametrize("response", [
    {"claims": [CLAIM], "scalar_facts": []},
    json.dumps({"claims": [CLAIM], "scalar_facts": []}),
    f"```json\n{json.dumps({'claims': [CLAIM], 'scalar_facts': []})}\n```",
    f"Here is the requested JSON:\n{json.dumps({'claims': [CLAIM], 'scalar_facts': []})}\nThanks.",
])
def test_supported_single_object_wrappers_remain_offline_replay_compatible(response):
    assert sonnet.parse_extraction(response, doc_id=1)["claims"][0]["kind"] == "verdict"


@pytest.mark.parametrize("response", ["{bad", "pure garbage", "[]", "{} {}",
                                      "```json\n{}\n```\n{}"])
def test_malformed_array_multiple_and_mixed_output_rejected(response):
    with pytest.raises(sonnet.SBIExtractionError):
        sonnet.parse_extraction(response, doc_id=1)


def test_malformed_response_diagnostic_is_sanitized_prefix_only():
    with pytest.raises(sonnet.SBIExtractionError, match="prefix='secret malformed'"):
        sonnet.parse_extraction("secret\n malformed", doc_id=1)


@pytest.mark.parametrize("payload", [
    {"claims": [{"kind": "key_risk", "text": "Risk", "quote": "evidence",
                 "page_number": 3}], "scalar_facts": []},
    {"claims": [], "scalar_facts": [{"field": "sbi_rating", "value": "SUBSCRIBE",
                                      "quote": "evidence", "page_number": 1}]},
    {"claims": [{**CLAIM, "quote": "duplicate alias"}], "scalar_facts": []},
])
def test_schema_drift_and_synonyms_are_rejected(payload):
    with pytest.raises(sonnet.SBIExtractionError, match="no valid extraction items remain"):
        sonnet.parse_extraction(payload, doc_id=1)


def test_schema_item_limits_and_statement_bounds_remain_strict():
    with pytest.raises(sonnet.SBIExtractionError, match="maximum of 10"):
        sonnet.parse_extraction({"claims": [CLAIM] * 11, "scalar_facts": []}, doc_id=1)
    with pytest.raises(sonnet.SBIExtractionError, match="maximum of 3"):
        sonnet.parse_extraction({"claims": [], "scalar_facts": [FACT] * 4}, doc_id=1)
    parsed = sonnet.parse_extraction(
        {"claims": [CLAIM, {**CLAIM, "statement": "word " * 41}],
         "scalar_facts": []}, doc_id=1)
    assert parsed["dropped_items"][0]["reason"] == "statement exceeds 40 words"
    parsed = sonnet.parse_extraction(
        {"claims": [CLAIM, {**CLAIM, "statement": "line one\nline two"}],
         "scalar_facts": []}, doc_id=1)
    assert parsed["dropped_items"][0]["reason"] == "statement must be single-line"


@pytest.mark.parametrize("statement", [
    "The company plans to repay Rs. 300 crore of debt.",
    "ABC Ltd. plans to expand capacity using internal accruals.",
    "Approx. Rs. 125 crore will be used for debt repayment.",
])
def test_financial_abbreviations_remain_valid_single_line_statements(statement):
    parsed = sonnet.parse_extraction(
        {"claims": [{**CLAIM, "statement": statement}], "scalar_facts": []}, doc_id=1)
    assert parsed["claims"][0]["statement"] == statement


@pytest.mark.parametrize(("change", "reason"), [
    ({"quote": "alias"}, "unsupported fields: ['quote']"),
    ({"page_number": 0}, "invalid page_number"),
    ({"confidence": "bad"}, "invalid confidence"),
    ({"confidence": 2}, "invalid confidence"),
])
def test_malformed_page_confidence_and_extra_fields_have_drop_diagnostics(change, reason):
    parsed = sonnet.parse_extraction(
        {"claims": [CLAIM, {**CLAIM, **change}], "scalar_facts": []}, doc_id=1)
    assert parsed["dropped_items"] == [
        {"item_type": "claim", "position": 1, "reason": reason}]


def test_unknown_reference_is_not_reassigned_to_another_page():
    with pytest.raises(sonnet.EvidenceReferenceError, match="unknown"):
        sonnet.parse_extraction(
            {"claims": [{"kind": "verdict", "statement": "Supported.",
                         "evidence_refs": ["P2:L002"]}], "scalar_facts": []},
            doc_id=1, pages=[{"page_number": 2, "text": "Other"},
                             {"page_number": 3, "text": "Exact supporting evidence"}])


def _response(payload):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps(payload).encode()
    return Response()


def test_multiple_tool_use_blocks_are_rejected(monkeypatch):
    payload = {"content": [
        {"type": "tool_use", "name": sonnet.TOOL_NAME, "input": {}},
        {"type": "tool_use", "name": sonnet.TOOL_NAME, "input": {}}],
        "usage": {}, "stop_reason": "tool_use"}
    monkeypatch.setattr(run.urllib.request, "urlopen", lambda *a, **k: _response(payload))
    with pytest.raises(run.ModelError, match="exactly one"):
        run.anthropic_call(pages=[{"page_number": 1, "text": "x"}],
                           api_key="offline", output_cap=100)


def test_max_tokens_is_truncated_and_parser_is_never_called(monkeypatch):
    payload = {"content": [{"type": "text", "text": "partial"}],
               "usage": {"input_tokens": 12, "output_tokens": 100},
               "stop_reason": "max_tokens"}
    monkeypatch.setattr(run.urllib.request, "urlopen", lambda *a, **k: _response(payload))
    body, itok, otok, reason = run.anthropic_call(
        pages=[{"page_number": 1, "text": "x"}], api_key="offline", output_cap=100)
    called = []
    status, parsed = run.parse_complete_response(
        body, doc_id=1, stop_reason=reason,
        parser=lambda *a, **k: called.append("parse"))
    assert (itok, otok, status, parsed, called) == (12, 100, "TRUNCATED", None, [])


def test_count_and_generation_share_identical_model_system_tools_choice_and_pages():
    pages = [{"page_number": 1, "text": "fixture"}]
    counted = sonnet.build_tool_request(pages)
    generated = sonnet.build_tool_request(pages, output_cap=100)
    for key in ("model", "system", "tools", "tool_choice", "messages"):
        assert counted[key] == generated[key]
    assert generated["temperature"] == 0 and generated["max_tokens"] == 100
    assert "temperature" not in counted and "max_tokens" not in counted


def test_owner_price_card_requires_complete_positive_configuration():
    with pytest.raises(SystemExit, match="OWNER-APPROVED PRICE CARD REQUIRED"):
        run.load_owner_price_card({})
    card = run.load_owner_price_card({
        "SBI_SONNET_INPUT_USD_PER_MTOK": "3",
        "SBI_SONNET_OUTPUT_USD_PER_MTOK": "15",
        "SBI_SONNET_OUTPUT_CAP": "1000",
        "SBI_SONNET_RUN_CAP_USD": "7",
    })
    assert card.output_cap == 1000 and card.spend_cap == 7


def test_advisory_lock_uses_stable_session_lock_and_explicit_unlock():
    calls = []
    class Cursor:
        def execute(self, sql, params): calls.append((sql, params))
        def fetchone(self): return (True,)
        def close(self): pass
    conn = types.SimpleNamespace(cursor=lambda: Cursor())
    assert run.try_acquire_worker_lock(conn) is True
    run.release_worker_lock(conn)
    assert calls == [
        ("SELECT pg_try_advisory_lock(%s,%s)", run.SBI_WORKER_LOCK),
        ("SELECT pg_advisory_unlock(%s,%s)", run.SBI_WORKER_LOCK),
    ]


def test_deterministic_model_stub_and_central_identity():
    calls = []
    result = sonnet.extract(
        doc_id=9, pages=[{"page_number": 1, "text": "SUBSCRIBE fixture"}],
        model_client=lambda **kwargs: calls.append(kwargs) or {
            "claims": [], "scalar_facts": [{"field": "sbi_rating", "value": "SUBSCRIBE",
                                               "evidence_refs": ["P1:L001"]}]})
    assert result["scalar_facts"][0]["value"] == "SUBSCRIBE"
    assert calls[0]["model"] == sonnet.MODEL
    assert calls[0]["prompt_version"] == sonnet.PROMPT_VERSION


def test_cron_configuration_states_remain_typed():
    assert cron.classify_sbi_configuration(run.worker_configuration({})) == "skipped"
    assert cron.classify_sbi_configuration(run.worker_configuration(
        {"SBI_SONNET_OUTPUT_CAP": "100"})) == "warning"


def test_local_migration_verifier_hash_statuses_and_zero_write_preflight(tmp_path):
    body = b"%PDF-1.7\nfixture\n%%EOF"
    path = tmp_path / "Example Ltd_IPO Note.pdf"; path.write_bytes(body)
    rows = verify.local_inventory(tmp_path)
    assert rows[0]["local_sha256"] == __import__("hashlib").sha256(body).hexdigest()
    statuses = [{"status": status} for status in verify.STATUSES]
    counts = verify.aggregate(statuses)
    assert all(counts[status] == 1 for status in verify.STATUSES)
    budget = verify.preflight(rows)
    assert budget["r2_put_count"] == budget["neon_writes"] == budget["sonnet_calls"] == 0


def test_bounded_unresolved_report_is_advisory_only():
    identities = ((1, "ISIN1", "Example Limited", "example limited"),
                  (2, "ISIN2", "Example Ltd", "example ltd"))
    rows = [{"local_path": "data/research_notes/Unknown_IPO Note.pdf",
             "status": "IPO_UNRESOLVED", "identity_ambiguous_count": 0}]
    report = bounded.unresolved_report(rows, identities)
    assert report[0]["group"] == "NO_CANONICAL_MATCH"
    assert rows[0].get("ipo_id") is None and rows[0]["status"] == "IPO_UNRESOLVED"


def test_bounded_preflight_and_wire_counter_contracts():
    rows = [{"bytes": 10}, {"bytes": 20}, {"bytes": 30}]
    neon = bounded.preflight_contract(
        rows, rows[:2], pre_ingest_classification_reads=3)["expected Neon statements"]
    assert neon["expected_total_reads"] == 11 and neon["expected_total_writes"] == 2
    class Client:
        def head_object(self, **kwargs): return {}
        def get_object(self, **kwargs): return {}
        def put_object(self, **kwargs): return {}
    counter = bounded.CountingS3Client(Client())
    counter.head_object(); counter.get_object(); counter.put_object()
    assert (counter.heads, counter.gets, counter.puts) == (1, 1, 1)


def test_ingest_main_reuses_one_identity_set(monkeypatch):
    rows = ((1, "ISIN1", "Example Limited", "example limited"),)
    queries, received = [], []
    class Cursor:
        def execute(self, sql, params): queries.append(sql)
        def fetchall(self): return rows
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass
    monkeypatch.setitem(sys.modules, "psycopg2",
                        types.SimpleNamespace(connect=lambda url: Connection()))
    monkeypatch.setenv("DATABASE_URL", "postgresql://offline")
    monkeypatch.setattr(ingest, "ingest_file", lambda conn, path, **kwargs:
                        received.append(kwargs["identity_rows"]) or {"status": "READY"})
    assert ingest.main(["one.pdf", "two.pdf"]) == 0
    assert queries == [company_identity.IDENTITY_SET_SQL]
    assert received == [rows, rows]


def test_preloaded_identity_avoids_extra_sql_and_ephemeral_cleanup(monkeypatch, tmp_path):
    source = tmp_path / "Example Ltd_IPO Note.pdf"; source.write_bytes(b"%PDF fixture")
    calls = []
    class Stored:
        id, object_key, sha256, created = 81, "sbi/key", "digest", True
    class Cursor:
        def execute(self, *args): raise AssertionError("unexpected identity SQL")
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
    def store(*args, **kwargs):
        calls.append(kwargs)
        pathlib.Path(kwargs["temporary_path"]).unlink()
        return Stored()
    monkeypatch.setattr(ingest, "store_document", store)
    result = ingest.ingest_file(
        Connection(), source, owner_approved=True, retain_source=False,
        identity_rows=((7, "INE000TEST01", "Example Ltd", "example ltd"),))
    assert result["status"] == "LEDGERED" and not source.exists()
    assert calls[0]["temporary_path"] == source


def test_no_legacy_parser_in_production_lane_or_job_catalogs():
    root = pathlib.Path(__file__).resolve().parents[1]
    production = "\n".join((root / path).read_text(encoding="utf-8") for path in (
        "pipeline/sbi_sonnet.py", "pipeline/sbi_ingest.py", "pipeline/cron.py"))
    assert "parse_sbi_notes" not in production
    for path in ("_scripts/job_runner.py", "app/api/admin/jobs/route.ts",
                 "app/dashboard/admin/AdminConsoleClient.tsx"):
        assert "sbi_parse" not in (root / path).read_text(encoding="utf-8")
