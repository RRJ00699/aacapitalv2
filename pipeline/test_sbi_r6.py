import json
import math
import sys
import types

import pytest

from pipeline import fill_ipo, fill_v2, sbi_extraction_run as run, sbi_sonnet as sonnet


def test_v13_prompt_and_strict_tool_contract():
    assert sonnet.PROMPT_VERSION == "sbi-v1.3"
    assert "8-12 words" in sonnet.SYSTEM_PROMPT
    assert "--- PAGE N ---" in sonnet.SYSTEM_PROMPT
    assert sonnet.SBI_EXTRACTION_TOOL["strict"] is True
    schema = sonnet.SBI_EXTRACTION_TOOL["input_schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["claims"]["maxItems"] == 10
    assert schema["properties"]["scalar_facts"]["maxItems"] == 3
    assert sonnet.TOOL_CHOICE == {
        "type": "tool", "name": "record_sbi_extraction", "disable_parallel_tool_use": True}
    payload = sonnet.build_tool_request([{"page_number": 1, "text": "fixture"}], output_cap=2000)
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 2000
    assert payload["tools"][0]["strict"] is True


def _urlopen_response(payload):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return json.dumps(payload).encode()
    return Response()


def test_paid_transport_accepts_only_one_named_tool_use(monkeypatch):
    valid = {"claims": [{"kind": "verdict", "statement": "Supported.",
                          "excerpt": "short evidence", "page_number": 1}],
             "scalar_facts": []}
    response = {"content": [{"type": "tool_use", "id": "toolu_1",
                              "name": sonnet.TOOL_NAME, "input": valid}],
                "usage": {"input_tokens": 100, "output_tokens": 40},
                "stop_reason": "tool_use"}
    monkeypatch.setattr(run.urllib.request, "urlopen",
                        lambda *a, **k: _urlopen_response(response))
    payload, itok, otok, reason = run.anthropic_call(
        pages=[{"page_number": 1, "text": "short evidence"}], api_key="x", output_cap=2000)
    assert payload == valid and (itok, otok, reason) == (100, 40, "tool_use")


@pytest.mark.parametrize("response", [
    {"content": [{"type": "text", "text": "{}"}], "usage": {}, "stop_reason": "end_turn"},
    {"content": [], "usage": {}, "stop_reason": "tool_use"},
    {"content": [{"type": "tool_use", "name": "wrong", "input": {}}],
     "usage": {}, "stop_reason": "tool_use"},
    {"content": [{"type": "tool_use", "name": sonnet.TOOL_NAME, "input": {}},
                 {"type": "tool_use", "name": sonnet.TOOL_NAME, "input": {}}],
     "usage": {}, "stop_reason": "tool_use"},
])
def test_paid_transport_fails_closed_without_prose_fallback(monkeypatch, response):
    monkeypatch.setattr(run.urllib.request, "urlopen",
                        lambda *a, **k: _urlopen_response(response))
    with pytest.raises(run.ModelError):
        run.anthropic_call(pages=[{"page_number": 1, "text": "x"}],
                           api_key="x", output_cap=2000)


def test_max_tokens_remains_truncated(monkeypatch):
    response = {"content": [{"type": "text", "text": "partial"}],
                "usage": {"input_tokens": 12, "output_tokens": 2000},
                "stop_reason": "max_tokens"}
    monkeypatch.setattr(run.urllib.request, "urlopen",
                        lambda *a, **k: _urlopen_response(response))
    body, _, _, reason = run.anthropic_call(
        pages=[{"page_number": 1, "text": "x"}], api_key="x", output_cap=2000)
    status, parsed = run.parse_complete_response(body, doc_id=1, stop_reason=reason)
    assert status == "TRUNCATED" and parsed is None


def test_count_tokens_uses_same_model_system_tools_choice_and_pages(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return b'{"input_tokens":321}'
    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data)
        return Response()
    monkeypatch.setattr(run.urllib.request, "urlopen", fake_urlopen)
    pages = [{"page_number": 1, "text": "fixture"}]
    assert run.count_tokens_call(pages=pages, api_key="x") == 321
    expected = sonnet.build_tool_request(pages)
    assert captured["url"].endswith("/v1/messages/count_tokens")
    assert captured["payload"] == expected
    assert "temperature" not in captured["payload"] and "max_tokens" not in captured["payload"]


def test_shared_extraction_predicate_covers_insights_and_source_facts():
    sql, params = sonnet.extraction_predicate(42)
    assert "FROM insights" in sql and "FROM source_facts" in sql
    assert "source_type='SBI'" in sql and "doc_id=%s" in sql
    assert sonnet.MODEL in params and sonnet.PROMPT_VERSION in params
    assert any("SBI:doc=42:page=%" in str(value) for value in params)


class FactCursor:
    def __init__(self, existing=None):
        self.existing = existing
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
    def fetchone(self):
        return self.existing


def test_source_fact_writer_persists_doc_id_and_model_confidence():
    cur = FactCursor()
    fill_ipo._log_fact(cur, 1, "sbi_rating", "SUBSCRIBE", "SBI:doc=7", doc_id=7,
                       confidence=0.73)
    insert_sql, insert_params = cur.calls[-1]
    assert "doc_id,confidence" in insert_sql.replace(" ", "").replace("\n", "")
    assert insert_params[-2:] == (7, 0.73)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, "bad", True, math.inf, math.nan])
def test_source_fact_writer_rejects_invalid_confidence_before_sql(confidence):
    cur = FactCursor()
    with pytest.raises(ValueError, match="confidence must be numeric between 0 and 1"):
        fill_ipo._log_fact(cur, 1, "sbi_rating", "SUBSCRIBE", "sbi",
                           doc_id=7, confidence=confidence)
    assert cur.calls == []


def test_fill_v2_wrapper_passes_doc_id_and_confidence(monkeypatch):
    calls = []
    monkeypatch.setattr(fill_v2, "_log_fact", lambda *args, **kwargs: calls.append((args, kwargs)))
    conn = types.SimpleNamespace(cursor=lambda: object(), commit=lambda: None)
    fill_v2.log_source_fact(conn, 1, "sbi_rating", "SUBSCRIBE", "sbi",
                            doc_id=7, confidence=0.73, commit=False)
    assert calls[0][1] == {"doc_id": 7, "confidence": 0.73}


def test_drop_counter_is_single_application_and_blocks_pilot():
    totals = run.Counter(selected=1, calls=1, successes=1, pilot=1)
    dropped = [{"item_type": "claim", "position": 1, "reason": "excerpt exceeds 15 words"}]
    run.count_drops(totals, dropped)
    assert totals["dropped_items_total"] == totals["dropped_claims"] == 1
    assert run.full_run_approval_blocked(totals) is True


def test_input_token_reserve_exceeded_blocks_historical_approval():
    totals = run.Counter(selected=2, calls=2, successes=2, pilot=1,
                         input_reserve_exceeded=1)
    assert run.full_run_approval_blocked(totals) is True


def test_frozen_count_scope_requires_exactly_198_verified_documents():
    rows = [{"ipo_id": i + 1, "documents_object_key": f"sbi/{i}",
             "r2_sha_status": "VERIFIED"} for i in range(198)]
    assert len(run.frozen_verified_scope(rows)) == 198
    with pytest.raises(SystemExit, match="expected frozen 198"):
        run.frozen_verified_scope(rows[:-1])


def test_count_only_pricing_does_not_require_a_spend_ceiling():
    env = {
        "SBI_SONNET_INPUT_USD_PER_MTOK": "3",
        "SBI_SONNET_OUTPUT_USD_PER_MTOK": "15",
        "SBI_SONNET_OUTPUT_CAP": "2000",
    }
    card = run.load_count_price_card(env)
    assert (card.input_usd_per_mtok, card.output_usd_per_mtok, card.output_cap) == (
        run.Decimal("3"), run.Decimal("15"), 2000)
    with pytest.raises(SystemExit, match="SBI_SONNET_SPEND_CAP_USD"):
        run.load_owner_price_card(env)


def test_sbi_write_path_passes_document_and_model_confidence(monkeypatch):
    captured = []
    monkeypatch.setattr(sonnet, "already_extracted", lambda *a, **k: False)
    monkeypatch.setattr(fill_v2, "log_source_fact",
                        lambda *args, **kwargs: captured.append((args, kwargs)))
    monkeypatch.setattr(fill_v2, "upsert_insights",
                        lambda *args, **kwargs: (0, 0, None))
    conn = types.SimpleNamespace(cursor=lambda: object(), commit=lambda: None)
    parsed = sonnet.parse_extraction({
        "claims": [],
        "scalar_facts": [{"field": "sbi_rating", "value": "SUBSCRIBE",
                           "excerpt": "We recommend SUBSCRIBE", "page_number": 1,
                           "confidence": 0.73}],
    }, doc_id=42)
    sonnet.write_extraction(conn, ipo_id=9, doc_id=42, extraction=parsed, validated=True)
    _, kwargs = captured[0]
    assert kwargs["doc_id"] == 42
    assert kwargs["confidence"] == 0.73
    assert kwargs["commit"] is False


def test_facts_only_extraction_is_complete_to_remote_verifier(monkeypatch):
    from pipeline import sbi_migration_verify as verify

    class Resolution:
        method = "EXACT_NAME"
        ambiguous_count = 0
        row = (9, "INE000TEST01", "Example Limited")

    monkeypatch.setattr(verify, "company_from_filename", lambda path: "Example Limited")
    monkeypatch.setattr(verify, "resolve_ipo", lambda *a, **k: Resolution())

    digest = "a" * 64

    class Cursor:
        def __init__(self): self.result = None
        def execute(self, sql, params=()):
            if "FROM documents" in sql:
                self.result = (42, digest, "sbi/key", 9)
            elif "FROM insights" in sql and "FROM source_facts" in sql:
                # Simulate a facts-only v1.3 extraction returned by the shared UNION.
                self.result = (42, sonnet.MODEL, sonnet.PROMPT_VERSION)
            elif "SELECT id,isin FROM ipo" in sql:
                self.result = (9, "INE000TEST01")
            else:
                self.result = None
        def fetchone(self): return self.result
        def close(self): pass

    class Conn:
        def cursor(self): return Cursor()

    class Store:
        def head_document(self, key): return {"Metadata": {"sha256": digest}}

    row = {"local_path": "Example Limited_IPO Note.pdf",
           "local_sha256": digest, "bytes": 1}
    result = verify.verify_remote(row, Conn(), Store(), verify.OperationCounter())
    assert result["status"] == "VERIFIED_ALREADY_PRESENT"
    assert result["extraction_tuple"] == [42, sonnet.MODEL, sonnet.PROMPT_VERSION]
    assert verify.aggregate([result])["EXTRACTION_MISSING"] == 0


def test_ongoing_evidence_rejection_retains_and_counts_dropped_items(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from pipeline import sbi_ongoing as ongoing

    monkeypatch.setattr(ongoing, "downloaded_pdfs", lambda directory: [])
    monkeypatch.setattr(ongoing, "load_company_identity_set", lambda cur: ())
    monkeypatch.setattr(ongoing, "read_cutover",
                        lambda conn: datetime(2026, 8, 9, tzinfo=timezone.utc))
    monkeypatch.setattr(ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [7])
    monkeypatch.setattr(ongoing, "already_extracted", lambda conn, doc_id: False)
    digest = __import__("hashlib").sha256(b"bytes").hexdigest()
    monkeypatch.setattr(ongoing, "_ledger_row", lambda conn, doc_id: (7, 1, "key", digest))
    monkeypatch.setattr(ongoing, "pdf_pages",
                        lambda body: [{"page_number": 1, "text": "different evidence"}])
    monkeypatch.setattr(ongoing, "persist_manifest",
                        lambda payload, directory: str(tmp_path / "ongoing.json"))

    class Conn:
        def cursor(self): return types.SimpleNamespace(close=lambda: None)
        def rollback(self): pass

    class Store:
        def get_document(self, key): return b"bytes"

    response = {
        "claims": [
            {"kind": "verdict", "statement": "Supported.",
             "excerpt": "missing evidence", "page_number": 1},
            {"kind": "key_risk", "statement": "Too long excerpt is dropped.",
             "excerpt": "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen",
             "page_number": 1},
        ],
        "scalar_facts": [],
    }
    env = {
        "SBI_SONNET_INPUT_USD_PER_MTOK": "3",
        "SBI_SONNET_OUTPUT_USD_PER_MTOK": "15",
        "SBI_SONNET_OUTPUT_CAP": "2000",
        "SBI_SONNET_RUN_CAP_USD": "1",
        "ANTHROPIC_API_KEY": "offline-test",
    }
    result = ongoing.run_sbi_lane(
        Conn(), directory=tmp_path, store=Store(), environ=env,
        model_call=lambda **kwargs: (response, 10, 20, "tool_use"))
    assert result["summary"]["EVIDENCE_REJECTED"] == 1
    assert result["summary"]["dropped_items_total"] == 1
    record = next(item for item in result["records"] if item.get("status") == "EVIDENCE_REJECTED")
    assert record["dropped_items"] == [
        {"item_type": "claim", "position": 1, "reason": "excerpt exceeds 15 words"}]


def test_guarded_input_tokens_uses_floor_and_percentage_reserve():
    assert run.guarded_input_tokens(5_000) == 6_024
    assert run.guarded_input_tokens(20_000) == 22_000
