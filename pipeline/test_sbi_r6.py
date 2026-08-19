import json
import math
import types

import pytest

from pipeline import fill_ipo, fill_v2, sbi_extraction_run as run, sbi_sonnet as sonnet


def test_prompt_and_strict_tool_contract():
    assert sonnet.MODEL == "claude-sonnet-4-6"
    assert sonnet.PROMPT_VERSION == "sbi-v1.5"
    assert "evidence_refs" in sonnet.SYSTEM_PROMPT
    assert sonnet.SBI_EXTRACTION_TOOL["strict"] is True
    assert sonnet.TOOL_CHOICE == {
        "type": "tool", "name": sonnet.TOOL_NAME,
        "disable_parallel_tool_use": True}
    payload = sonnet.build_tool_request(
        [{"page_number": 1, "text": "fixture"}], output_cap=2000)
    assert payload["temperature"] == 0 and payload["max_tokens"] == 2000


def test_wire_schema_excludes_unsupported_strict_constraints():
    schema = sonnet.build_tool_request(
        [{"page_number": 1, "text": "fixture"}])["tools"][0]["input_schema"]
    unsupported = {
        "maxItems", "minimum", "maximum",
        "minLength", "maxLength", "pattern",
    }
    found = []
    def walk(value):
        if isinstance(value, dict):
            found.extend(unsupported.intersection(value))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)
    assert found == []


def test_local_validation_retains_bounds_removed_from_wire_schema():
    claim = {"kind": "verdict", "statement": "Supported.",
             "excerpt": "Exact evidence", "page_number": 1}
    fact = {"field": "sbi_rating", "value": "SUBSCRIBE",
            "excerpt": "Exact evidence", "page_number": 1}
    with pytest.raises(sonnet.SBIExtractionError, match="maximum of 10"):
        sonnet.parse_extraction({"claims": [claim] * 11, "scalar_facts": []}, doc_id=1)
    with pytest.raises(sonnet.SBIExtractionError, match="maximum of 3"):
        sonnet.parse_extraction({"claims": [], "scalar_facts": [fact] * 4}, doc_id=1)
    for invalid in ({**claim, "page_number": 0},
                    {**claim, "confidence": -0.1},
                    {**claim, "confidence": 1.1}):
        parsed = sonnet.parse_extraction(
            {"claims": [claim, invalid], "scalar_facts": []}, doc_id=1)
        assert parsed["dropped_items"][0]["reason"] in {
            "invalid page_number", "invalid confidence"}


def _urlopen_response(payload):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return json.dumps(payload).encode()
    return Response()


def test_transport_accepts_only_one_named_tool_use(monkeypatch):
    value = {"claims": [{"kind": "verdict", "statement": "Supported.",
                          "excerpt": "short evidence", "page_number": 1}],
             "scalar_facts": []}
    response = {"content": [{"type": "tool_use", "name": sonnet.TOOL_NAME,
                              "input": value}],
                "usage": {"input_tokens": 100, "output_tokens": 40},
                "stop_reason": "tool_use"}
    monkeypatch.setattr(run.urllib.request, "urlopen",
                        lambda *a, **k: _urlopen_response(response))
    assert run.anthropic_call(pages=[{"page_number": 1, "text": "short evidence"}],
                              api_key="x", output_cap=2000) == (
                                  value, 100, 40, "tool_use")


@pytest.mark.parametrize("response", [
    {"content": [{"type": "text", "text": "{}"}], "usage": {},
     "stop_reason": "end_turn"},
    {"content": [], "usage": {}, "stop_reason": "tool_use"},
    {"content": [{"type": "tool_use", "name": "wrong", "input": {}}],
     "usage": {}, "stop_reason": "tool_use"},
])
def test_transport_fails_closed_without_prose_fallback(monkeypatch, response):
    monkeypatch.setattr(run.urllib.request, "urlopen",
                        lambda *a, **k: _urlopen_response(response))
    with pytest.raises(run.ModelError):
        run.anthropic_call(pages=[{"page_number": 1, "text": "x"}],
                           api_key="x", output_cap=2000)


def test_count_tokens_uses_exact_strict_request(monkeypatch):
    captured = {}
    def fake(req, timeout):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data)
        return _urlopen_response({"input_tokens": 321})
    monkeypatch.setattr(run.urllib.request, "urlopen", fake)
    pages = [{"page_number": 1, "text": "fixture"}]
    assert run.count_tokens_call(pages=pages, api_key="x") == 321
    assert captured["payload"] == sonnet.build_tool_request(pages)
    assert captured["url"].endswith("/v1/messages/count_tokens")


def test_shared_completion_covers_facts_and_insights_in_pending_and_point_lookup():
    point, point_params = sonnet.extraction_predicate(42)
    pending, pending_params = sonnet.pending_documents_query()
    for sql in (point, pending):
        assert "FROM insights" in sql and "FROM source_facts" in sql
    assert "NOT EXISTS" in pending
    assert sonnet.MODEL in point_params and sonnet.MODEL in pending_params


class FactCursor:
    def __init__(self): self.calls = []
    def execute(self, sql, params=()): self.calls.append((sql, params))
    def fetchone(self): return None


def test_source_fact_writer_persists_doc_id_and_confidence():
    cur = FactCursor()
    fill_ipo._log_fact(cur, 1, "sbi_rating", "SUBSCRIBE", "SBI:doc=7",
                       doc_id=7, confidence=0.73)
    sql, params = cur.calls[-1]
    assert "doc_id,confidence" in sql.replace(" ", "").replace("\n", "")
    assert params[-2:] == (7, 0.73)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, "bad", True, math.inf, math.nan])
def test_source_fact_writer_rejects_invalid_confidence(confidence):
    cur = FactCursor()
    with pytest.raises(ValueError, match="confidence must be numeric between 0 and 1"):
        fill_ipo._log_fact(cur, 1, "sbi_rating", "SUBSCRIBE", "sbi",
                           doc_id=7, confidence=confidence)
    assert cur.calls == []


def test_fill_v2_wrapper_passes_doc_id_and_confidence(monkeypatch):
    calls = []
    monkeypatch.setattr(fill_v2, "_log_fact",
                        lambda *args, **kwargs: calls.append(kwargs))
    conn = types.SimpleNamespace(cursor=lambda: object(), commit=lambda: None)
    fill_v2.log_source_fact(conn, 1, "sbi_rating", "SUBSCRIBE", "sbi",
                            doc_id=7, confidence=0.73, commit=False)
    assert calls == [{"doc_id": 7, "confidence": 0.73}]


def test_guarded_input_tokens_floor_and_percentage():
    assert run.guarded_input_tokens(5_000) == 6_024
    assert run.guarded_input_tokens(20_000) == 22_000
