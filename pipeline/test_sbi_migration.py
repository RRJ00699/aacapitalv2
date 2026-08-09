import hashlib
import json
import pathlib
import runpy
import sys
import types
from datetime import datetime, timezone

import pytest

from pipeline import sbi_migration_verify as verify
from pipeline import sbi_sonnet as sonnet
from pipeline import sbi_ingest as ingest
from pipeline import sbi_bounded_ingest as bounded
from pipeline import company_identity
from pipeline import sbi_extraction_run as extraction_run


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


@pytest.mark.parametrize("response", [
    FIXTURE,
    json.dumps(FIXTURE),
    f"```json\n{json.dumps(FIXTURE)}\n```",
    f"```\n{json.dumps(FIXTURE)}\n```",
    f"Here is the requested JSON:\n{json.dumps(FIXTURE)}\nThanks.",
])
def test_json_object_accepts_only_supported_single_object_wrappers(response):
    assert sonnet.parse_extraction(response, doc_id=1)["claims"][0]["kind"] == "key_risk"


@pytest.mark.parametrize("response", [
    "{bad", "pure garbage", "[]", "{} {}", "```json\n{}\n```\n{}",
])
def test_json_object_rejects_malformed_array_multiple_and_mixed_output(response):
    with pytest.raises(sonnet.SBIExtractionError):
        sonnet.parse_extraction(response, doc_id=1)


def test_malformed_response_error_has_sanitized_prefix_only():
    with pytest.raises(sonnet.SBIExtractionError, match="prefix='secret malformed'"):
        sonnet.parse_extraction("secret\n malformed", doc_id=1)


@pytest.mark.parametrize("field", sorted(sonnet.FORBIDDEN_FIELDS))
def test_ai_cannot_write_deterministic_valuation_fields(field):
    with pytest.raises(sonnet.SBIExtractionError, match="deterministic fields"):
        sonnet.parse_extraction({field: 1, "claims": [], "scalar_facts": []}, doc_id=1)


def test_missing_page_or_excerpt_is_rejected():
    bad = json.loads(json.dumps(FIXTURE))
    bad["claims"][0].pop("excerpt")
    with pytest.raises(sonnet.SBIExtractionError, match="statement/excerpt"):
        sonnet.parse_extraction(bad, doc_id=1)


def test_prompt_v11_pins_literal_exact_schema_and_no_synonyms():
    assert sonnet.PROMPT_VERSION == "sbi-v1.1"
    for required in (
        '"kind": "key_risk"',
        '"statement": "One concise sentence explicitly supported by the note."',
        '"excerpt": "Verbatim excerpt of no more than fifteen words."',
        '"page_number": 3',
        '"field": "sbi_rating"',
        '"value": "SUBSCRIBE"',
        "Use exactly these field names.",
        "text, quote, description, citation, page, rating_text",
        "no Markdown fences, commentary, preamble",
    ):
        assert required in sonnet.SYSTEM_PROMPT


def test_claim_text_quote_schema_drift_is_rejected_without_aliasing():
    drifted = {"claims": [{"kind": "key_risk", "text": "Risk is high",
                            "quote": "verbatim risk", "page_number": 3}],
               "scalar_facts": []}
    with pytest.raises(sonnet.SBIExtractionError,
                       match=r"claims\[0\] lacks required statement/excerpt fields"):
        sonnet.parse_extraction(drifted, doc_id=1)


def test_scalar_quote_schema_drift_is_rejected_without_aliasing():
    drifted = {"claims": [], "scalar_facts": [{"field": "sbi_rating",
               "value": "SUBSCRIBE", "quote": "We recommend SUBSCRIBE",
               "page_number": 1}]}
    with pytest.raises(sonnet.SBIExtractionError,
                       match=r"scalar_facts\[0\] lacks required excerpt field"):
        sonnet.parse_extraction(drifted, doc_id=1)


def test_synonym_is_rejected_even_when_required_claim_fields_are_present():
    drifted = {"claims": [{"kind": "key_risk", "statement": "Risk is high.",
                            "excerpt": "verbatim risk", "quote": "duplicate alias",
                            "page_number": 3}], "scalar_facts": []}
    with pytest.raises(sonnet.SBIExtractionError,
                       match=r"claims\[0\] has unsupported fields: \['quote'\]"):
        sonnet.parse_extraction(drifted, doc_id=1)


def test_r3_output_bounds_remain_strict():
    claim = {"kind": "key_risk", "statement": "One supported risk.",
             "excerpt": "short excerpt", "page_number": 1}
    fact = {"field": "sbi_rating", "value": "SUBSCRIBE",
            "excerpt": "short excerpt", "page_number": 1}
    with pytest.raises(sonnet.SBIExtractionError, match="maximum of 10"):
        sonnet.parse_extraction({"claims": [claim] * 11, "scalar_facts": []}, doc_id=1)
    with pytest.raises(sonnet.SBIExtractionError, match="maximum of 3"):
        sonnet.parse_extraction({"claims": [], "scalar_facts": [fact] * 4}, doc_id=1)
    too_long = dict(claim, excerpt="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen")
    with pytest.raises(sonnet.SBIExtractionError, match="exceeds 15 words"):
        sonnet.parse_extraction({"claims": [too_long], "scalar_facts": []}, doc_id=1)
    exactly_40 = dict(claim, statement=" ".join(["word"] * 40))
    sonnet.parse_extraction({"claims": [exactly_40], "scalar_facts": []}, doc_id=1)
    too_many = dict(claim, statement=" ".join(["word"] * 41))
    with pytest.raises(sonnet.SBIExtractionError, match="exceeds 40 words"):
        sonnet.parse_extraction({"claims": [too_many], "scalar_facts": []}, doc_id=1)
    multiline = dict(claim, statement="First line\nsecond line")
    with pytest.raises(sonnet.SBIExtractionError, match="single-line"):
        sonnet.parse_extraction({"claims": [multiline], "scalar_facts": []}, doc_id=1)


@pytest.mark.parametrize("statement", [
    "The company plans to repay Rs. 300 crore of debt.",
    "ABC Ltd. plans to expand capacity using internal accruals.",
    "Approx. Rs. 125 crore will be used for debt repayment.",
])
def test_r4_financial_abbreviations_are_valid_single_line_statements(statement):
    claim = {"kind": "key_risk", "statement": statement,
             "excerpt": "short excerpt", "page_number": 1}
    parsed = sonnet.parse_extraction({"claims": [claim], "scalar_facts": []}, doc_id=1)
    assert parsed["claims"][0]["statement"] == statement


def test_evidence_must_be_verbatim_on_asserted_page():
    parsed = sonnet.parse_extraction(FIXTURE, doc_id=1)
    pages = [{"page_number": 1, "text": "We recommend SUBSCRIBE"},
             {"page_number": 7, "text": "The top ten customers contributed 82% of sales."}]
    extraction_run.validate_evidence(parsed, pages)
    pages[1]["text"] = "No supporting language here."
    with pytest.raises(ValueError, match="unsupported excerpt on page 7"):
        extraction_run.validate_evidence(parsed, pages)


def test_approved_cost_checkpoint_is_below_owner_cap(capsys):
    card = extraction_run.PriceCard(extraction_run.Decimal("3"), extraction_run.Decimal("15"),
                                    1000, extraction_run.Decimal("7"))
    extraction_run.print_cost_checkpoint(card)
    output = capsys.readouterr().out
    assert "documents to extract = 198" in output
    assert "maximum total estimate = $6.092169" in output
    assert extraction_run.cost(1_040_723, 198_000, card) < card.spend_cap


def test_v11_historical_maximum_exceeds_old_nine_dollar_authorization():
    card = extraction_run.PriceCard(extraction_run.Decimal("3"), extraction_run.Decimal("15"),
                                    2000, extraction_run.Decimal("9"))
    maximum = extraction_run.cost(1_040_723, 198 * 2000, card)
    assert maximum == extraction_run.Decimal("9.062169")
    with pytest.raises(SystemExit, match="exceeds .*9.00 cap"):
        extraction_run.print_cost_checkpoint(card)


def _eligible_rows(count):
    return [{"ipo_id": i + 1, "documents_object_key": f"key/{i}",
             "r2_sha_status": "VERIFIED", "extraction_tuple": None} for i in range(count)]


@pytest.mark.parametrize("count", [198, 2, 0])
def test_resumable_eligibility_accepts_full_partial_and_noop(count):
    assert len(extraction_run.eligible_scope(_eligible_rows(count))) == count


def test_resumable_eligibility_aborts_scope_creep():
    with pytest.raises(SystemExit, match="scope creep"):
        extraction_run.eligible_scope(_eligible_rows(199))


def test_pilot_limit_can_attempt_at_most_two_eligible_notes():
    assert len(extraction_run.eligible_scope(_eligible_rows(198), limit=2)) == 2
    assert len(extraction_run.eligible_scope(_eligible_rows(1), limit=2)) == 1


def test_owner_price_card_fails_closed_and_loads_explicit_values():
    with pytest.raises(SystemExit, match="OWNER-APPROVED PRICE CARD REQUIRED"):
        extraction_run.load_owner_price_card({})
    card = extraction_run.load_owner_price_card({
        "SBI_SONNET_INPUT_USD_PER_MTOK": "3",
        "SBI_SONNET_OUTPUT_USD_PER_MTOK": "15",
        "SBI_SONNET_OUTPUT_CAP": "1000",
        "SBI_SONNET_SPEND_CAP_USD": "7",
    })
    assert card.output_cap == 1000 and card.spend_cap == 7


def test_max_tokens_is_truncated_without_parse_or_write_path():
    called = []
    status, parsed = extraction_run.parse_complete_response(
        "incomplete JSON", doc_id=1, stop_reason="max_tokens",
        parser=lambda *args, **kwargs: called.append("parse"))
    assert status == "TRUNCATED" and parsed is None
    assert called == []


@pytest.mark.parametrize("failed", extraction_run.FAILURE_STATUSES)
def test_every_pilot_failure_blocks_full_run(failed):
    totals = extraction_run.Counter(calls=2, successes=1)
    totals[failed] = 1
    assert extraction_run.full_run_approval_blocked(totals) is True


def test_success_count_mismatch_blocks_full_run_even_without_failure_category():
    assert extraction_run.full_run_approval_blocked(
        extraction_run.Counter(calls=2, successes=1)) is True
    assert extraction_run.full_run_approval_blocked(
        extraction_run.Counter(calls=2, successes=2)) is False
    assert extraction_run.full_run_approval_blocked(
        extraction_run.Counter(selected=2, calls=1, successes=1, spend_stopped=1)) is True


def _complete_historical_rows():
    return [{"documents_id": i + 1, "r2_sha_status": "VERIFIED",
             "status": "VERIFIED_ALREADY_PRESENT", "extraction_tuple": [i + 1, "m", "p"]}
            for i in range(198)]


class _CutoverCursor:
    def __init__(self, conn): self.conn = conn; self.rowcount = 0
    def execute(self, sql, params=()):
        self.conn.sql.append(sql)
        if "SELECT max(fetched_at)" in sql:
            self.result = (datetime(2026, 8, 9, 12, tzinfo=timezone.utc),)
        elif "INSERT INTO platform_config" in sql:
            self.rowcount = 1 if not self.conn.inserted else 0
            self.conn.inserted = True
    def fetchone(self): return self.result


class _CutoverConn:
    def __init__(self): self.sql = []; self.inserted = False; self.commits = 0
    def cursor(self): return _CutoverCursor(self)
    def commit(self): self.commits += 1


@pytest.mark.parametrize("limit,updates", [
    (2, {}),
    (None, {"selected": 2, "calls": 1, "successes": 1}),
    (None, {"selected": 1, "calls": 1, "successes": 0, "PARSE_ERROR": 1}),
    (None, {"selected": 2, "calls": 1, "successes": 1, "spend_stopped": 1}),
])
def test_pilot_partial_failed_and_spend_stopped_runs_never_write_cutover(limit, updates):
    totals = extraction_run.Counter(updates)
    conn = _CutoverConn()
    assert extraction_run.maybe_write_cutover(
        conn, limit=limit, verified=_complete_historical_rows(), totals=totals) is None
    assert not any("INSERT INTO platform_config" in sql for sql in conn.sql)


def test_clean_unlimited_historical_completion_writes_cutover_exactly_once():
    conn = _CutoverConn(); totals = extraction_run.Counter()
    marker = extraction_run.maybe_write_cutover(
        conn, limit=None, verified=_complete_historical_rows(), totals=totals)
    assert marker == "2026-08-09T12:00:00+00:00"
    assert sum("INSERT INTO platform_config" in sql for sql in conn.sql) == 1
    assert conn.commits == 1


def test_historical_extraction_missing_never_writes_cutover():
    rows = _complete_historical_rows()
    rows[0].update(status="EXTRACTION_MISSING", extraction_tuple=None)
    conn = _CutoverConn()
    assert extraction_run.maybe_write_cutover(
        conn, limit=None, verified=rows, totals=extraction_run.Counter()) is None
    assert conn.sql == []


def test_anthropic_call_returns_stop_reason_and_usage(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps({"content": [{"type": "text", "text": "partial"}],
                               "usage": {"input_tokens": 12, "output_tokens": 1000},
                               "stop_reason": "max_tokens"}).encode()
    monkeypatch.setattr(extraction_run.urllib.request, "urlopen", lambda *a, **k: Response())
    text, itok, otok, reason = extraction_run.anthropic_call(
        pages=[{"page_number": 1, "text": "x"}], api_key="test", output_cap=1000)
    assert (text, itok, otok, reason) == ("partial", 12, 1000, "max_tokens")
    card = extraction_run.PriceCard(extraction_run.Decimal("3"), extraction_run.Decimal("15"),
                                    1000, extraction_run.Decimal("7"))
    assert extraction_run.cost(itok, otok, card) == extraction_run.Decimal("0.015036")


def test_holdout_manifest_tolerates_advisory_filename_mismatch(monkeypatch):
    monkeypatch.setattr(extraction_run, "unresolved_report", lambda rows, identities: [{
        "filename": "missing.pdf", "closest_name_suggestions_advisory_only": [],
        "group": "NO_CANONICAL_MATCH"}])
    report = extraction_run.deterministic_holdout_report([], ())
    assert report[0]["local_sha"] is None
    assert report[0]["deterministically_resolved"] is False


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


def test_inventory_and_historical_runner_share_one_input_estimator():
    assert bounded.estimate_input_tokens is sonnet.estimate_input_tokens
    assert extraction_run.estimate_input_tokens is sonnet.estimate_input_tokens
    pages = [{"text": "abcd" * 10}]
    without_prompt = sonnet.estimate_input_tokens(pages, system_prompt="")
    with_prompt = sonnet.estimate_input_tokens(pages)
    assert with_prompt - without_prompt == (len(sonnet.SYSTEM_PROMPT) + 3) // 4


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
