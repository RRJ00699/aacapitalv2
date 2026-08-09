import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import cron, sbi_ongoing, sbi_sonnet


class Cursor:
    def __init__(self, ledger=None): self.ledger = ledger
    def execute(self, sql, params=()): self.sql, self.params = sql, params
    def fetchall(self):
        if "SELECT id,isin,name_display,name_norm FROM ipo" in self.sql:
            return ((1, "INE000TEST01", "Example Limited", "examplelimited"),)
        return []
    def fetchone(self): return self.ledger
    def close(self): pass


class Conn:
    def __init__(self, ledger=None): self.ledger = ledger; self.rollbacks = 0
    def cursor(self): return Cursor(self.ledger)
    def rollback(self): self.rollbacks += 1


ENV = {
    "SBI_SONNET_INPUT_USD_PER_MTOK": "3",
    "SBI_SONNET_OUTPUT_USD_PER_MTOK": "15",
    "SBI_SONNET_OUTPUT_CAP": "2000",
    "SBI_SONNET_SPEND_CAP_USD": "9",
    "SBI_SONNET_RUN_CAP_USD": "1",
    "ANTHROPIC_API_KEY": "test",
}
EMPTY_STORE = type("Store", (), {})()
REAL_PERSIST_MANIFEST = sbi_ongoing.persist_manifest
REAL_READ_CUTOVER = sbi_ongoing.read_cutover


@pytest.fixture(autouse=True)
def configured_cutover_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(sbi_ongoing, "read_cutover",
                        lambda conn: datetime(2026, 8, 9, tzinfo=timezone.utc))
    monkeypatch.setattr(sbi_ongoing, "persist_manifest",
                        lambda payload, directory: str(tmp_path / "ongoing-fixture.json"))


def _pdf(path):
    path.write_bytes(b"%PDF-1.7\nfixture")
    return path


def _extraction():
    return json.dumps({"claims": [{"kind": "verdict", "statement": "Subscribe",
        "page_number": 1, "excerpt": "We recommend Subscribe"}], "scalar_facts": []})


def test_new_note_uses_ledger_then_extracts_and_temp_is_gone(tmp_path, monkeypatch):
    path = _pdf(tmp_path / "Example Limited_IPO Note.pdf")
    calls = []
    def ingest(conn, incoming, **kwargs):
        calls.append(kwargs); Path(incoming).unlink()
        return {"status": "LEDGERED", "doc_id": 7, "created": True}
    monkeypatch.setattr(sbi_ongoing, "ingest_file", ingest)
    monkeypatch.setattr(sbi_ongoing, "already_extracted", lambda *a: False)
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [7])
    monkeypatch.setattr(sbi_ongoing, "pdf_pages", lambda body: [{"page_number": 1, "text": "We recommend Subscribe"}])
    writes = []
    monkeypatch.setattr(sbi_ongoing, "write_extraction", lambda *a, **k: writes.append(k))
    store = type("Store", (), {"get_document": lambda self, key: b"bytes"})()
    import hashlib
    conn = Conn((7, 1, "sbi/key", hashlib.sha256(b"bytes").hexdigest()))
    result = sbi_ongoing.run_sbi_lane(conn, directory=tmp_path, store=store, environ=ENV,
        model_call=lambda **kwargs: (_extraction(), 10, 20, "end_turn"))
    assert calls[0]["retain_source"] is False
    assert not path.exists() and result["summary"]["newly_ledgered"] == 1
    assert result["summary"]["extracted"] == 1 and writes[0]["doc_id"] == 7
    assert writes[0]["validated"] is True


def test_unresolved_identity_retains_pdf_and_never_extracts(tmp_path, monkeypatch):
    path = _pdf(tmp_path / "Unknown_IPO Note.pdf")
    monkeypatch.setattr(sbi_ongoing, "ingest_file", lambda *a, **k: {
        "status": "UNRESOLVED", "identity_resolution": "UNRESOLVED", "ambiguous_count": 0})
    model = []
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=EMPTY_STORE, environ=ENV,
        model_call=lambda **kwargs: model.append(kwargs))
    assert path.exists() and result["summary"]["unresolved"] == 1 and model == []


def test_already_extracted_makes_zero_model_calls(tmp_path, monkeypatch):
    _pdf(tmp_path / "Example Limited_IPO Note.pdf")
    monkeypatch.setattr(sbi_ongoing, "ingest_file", lambda *a, **k: {
        "status": "LEDGERED", "doc_id": 7, "created": False})
    monkeypatch.setattr(sbi_ongoing, "already_extracted", lambda *a: True)
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [7])
    model = []
    result = sbi_ongoing.run_sbi_lane(Conn((7, 1, "key", "sha")), directory=tmp_path,
        store=EMPTY_STORE, environ=ENV, model_call=lambda **kwargs: model.append(kwargs))
    assert result["summary"]["already_ledgered"] == 1
    assert result["summary"]["already_extracted"] == 1 and model == []


def test_ledgered_extraction_failure_retries_without_local_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [7])
    monkeypatch.setattr(sbi_ongoing, "already_extracted", lambda *a: False)
    monkeypatch.setattr(sbi_ongoing, "pdf_pages", lambda body: [{"page_number": 1, "text": "We recommend Subscribe"}])
    monkeypatch.setattr(sbi_ongoing.hashlib, "sha256", lambda body: type("H", (), {"hexdigest": lambda self: "sha"})())
    writes = []
    monkeypatch.setattr(sbi_ongoing, "write_extraction", lambda *a, **k: writes.append(k))
    store = type("Store", (), {"get_document": lambda self, key: b"bytes"})()
    result = sbi_ongoing.run_sbi_lane(Conn((7, 1, "key", "sha")), directory=tmp_path,
        store=store, environ=ENV,
        model_call=lambda **kwargs: (_extraction(), 10, 20, "end_turn"))
    assert result["summary"]["downloaded"] == 0
    assert result["summary"]["extracted"] == 1 and writes[0]["doc_id"] == 7


def test_one_model_failure_does_not_stop_following_note(tmp_path, monkeypatch):
    for name in ("A_IPO Note.pdf", "B_IPO Note.pdf"): _pdf(tmp_path / name)
    ids = iter((7, 8))
    monkeypatch.setattr(sbi_ongoing, "ingest_file", lambda *a, **k: {
        "status": "LEDGERED", "doc_id": next(ids), "created": True})
    monkeypatch.setattr(sbi_ongoing, "_ledger_row", lambda conn, doc_id: (doc_id, 1, "key", "sha"))
    monkeypatch.setattr(sbi_ongoing, "already_extracted", lambda *a: False)
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [7, 8])
    monkeypatch.setattr(sbi_ongoing, "pdf_pages", lambda body: [{"page_number": 1, "text": "We recommend Subscribe"}])
    monkeypatch.setattr(sbi_ongoing.hashlib, "sha256", lambda body: type("H", (), {"hexdigest": lambda self: "sha"})())
    monkeypatch.setattr(sbi_ongoing, "write_extraction", lambda *a, **k: None)
    calls = []
    def model(**kwargs):
        calls.append(1)
        if len(calls) == 1: raise RuntimeError("isolated")
        return _extraction(), 10, 20, "end_turn"
    store = type("Store", (), {"get_document": lambda self, key: b"bytes"})()
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=store,
                                      environ=ENV, model_call=model)
    assert len(calls) == 2 and result["summary"]["MODEL_ERROR"] == 1
    assert result["summary"]["extracted"] == 1


def test_ongoing_cap_is_required_and_stops_before_call(tmp_path, monkeypatch):
    assert sbi_ongoing.ongoing_configuration({}).status == "SKIPPED_OWNER_NOT_CONFIGURED"
    partial = {"SBI_SONNET_OUTPUT_CAP": "2000"}
    assert sbi_ongoing.ongoing_configuration(partial).status == "WARNING_CONFIGURATION_ERROR"
    invalid = dict(ENV); invalid["SBI_SONNET_RUN_CAP_USD"] = "bad"
    assert sbi_ongoing.ongoing_configuration(invalid).status == "WARNING_CONFIGURATION_ERROR"
    assert sbi_ongoing.ongoing_configuration(ENV).status == "CONFIGURED"


def test_failed_storage_retains_source_for_diagnosis(tmp_path, monkeypatch):
    path = _pdf(tmp_path / "Example Limited_IPO Note.pdf")
    monkeypatch.setattr(sbi_ongoing, "ingest_file",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("R2 down")))
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=EMPTY_STORE,
                                      environ=ENV, model_call=lambda **kwargs: None)
    assert path.exists() and result["summary"]["ingest_errors"] == 1


def test_per_run_spend_cap_stops_additional_calls(tmp_path, monkeypatch):
    for name in ("A_IPO Note.pdf", "B_IPO Note.pdf"): _pdf(tmp_path / name)
    ids = iter((7, 8))
    monkeypatch.setattr(sbi_ongoing, "ingest_file", lambda *a, **k: {
        "status": "LEDGERED", "doc_id": next(ids), "created": True})
    monkeypatch.setattr(sbi_ongoing, "_ledger_row", lambda conn, doc_id: (doc_id, 1, "key", "sha"))
    monkeypatch.setattr(sbi_ongoing, "already_extracted", lambda *a: False)
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [7, 8])
    monkeypatch.setattr(sbi_ongoing, "pdf_pages", lambda body: [{"page_number": 1, "text": "We recommend Subscribe"}])
    monkeypatch.setattr(sbi_ongoing.hashlib, "sha256", lambda body: type("H", (), {"hexdigest": lambda self: "sha"})())
    monkeypatch.setattr(sbi_ongoing, "write_extraction", lambda *a, **k: None)
    env = dict(ENV); env["SBI_SONNET_RUN_CAP_USD"] = "0.0316"
    calls = []
    store = type("Store", (), {"get_document": lambda self, key: b"bytes"})()
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=store, environ=env,
        model_call=lambda **kwargs: calls.append(1) or (_extraction(), 10, 20, "end_turn"))
    assert len(calls) == 1 and result["summary"]["spend_stopped"] == 1


def test_cron_sbi_source_is_runner_temp_and_failure_isolation_contract():
    source = Path(cron.__file__).read_text(encoding="utf-8")
    assert 'RUNNER_TEMP' in source and '"sbi-notes"' in source
    assert "from sbi_ongoing import ongoing_configuration, run_sbi_lane" in source
    assert "except (Exception, SystemExit)" in source
    assert source.index("isolated SBI lane failure") < source.index('"3. NSE per-IPO lifecycle"')
    assert "data/research_notes" not in source
    assert "parse_sbi_notes" not in source
    assert '"manifest_path": sbi_result.get("manifest_path")' in source


def test_missing_cutover_allows_ingest_but_skips_all_extraction(tmp_path, monkeypatch):
    _pdf(tmp_path / "Example Limited_IPO Note.pdf")
    monkeypatch.setattr(sbi_ongoing, "ingest_file", lambda *a, **k: {
        "status": "LEDGERED", "doc_id": 7, "ipo_id": 1, "created": True})
    monkeypatch.setattr(sbi_ongoing, "read_cutover", lambda conn: None)
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids",
                        lambda *a: (_ for _ in ()).throw(AssertionError("backlog query forbidden")))
    calls = []
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=EMPTY_STORE,
        environ=ENV, model_call=lambda **kwargs: calls.append(kwargs))
    assert result["summary"]["newly_ledgered"] == 1 and calls == []
    assert result["cutover_status"] == "SKIPPED_CUTOVER_NOT_CONFIGURED"


def test_invalid_cutover_fails_closed_with_zero_model_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(sbi_ongoing, "read_cutover", lambda conn: (_ for _ in ()).throw(
        sbi_ongoing.CutoverConfigurationError("invalid ISO timestamp")))
    calls = []
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=EMPTY_STORE,
        environ=ENV, model_call=lambda **kwargs: calls.append(kwargs))
    assert calls == [] and result["cutover_status"] == "WARNING_INVALID_CUTOVER"


def test_cutover_query_excludes_old_and_includes_at_or_after_marker():
    marker = datetime(2026, 8, 9, tzinfo=timezone.utc)
    rows = [(1, datetime(2026, 8, 8, tzinfo=timezone.utc)),
            (2, marker), (3, datetime(2026, 8, 10, tzinfo=timezone.utc))]
    class DateCursor:
        def execute(self, sql, params):
            assert "fetched_at >= %s" in sql
            self.result = [(doc_id,) for doc_id, fetched in rows if fetched >= params[0]]
        def fetchall(self): return self.result
    class DateConn:
        def cursor(self): return DateCursor()
    assert sbi_ongoing.pending_sbi_doc_ids(DateConn(), marker) == [2, 3]


def test_pre_cutover_historical_document_causes_zero_r2_gets_and_model_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [])
    calls, gets = [], []
    store = type("Store", (), {"get_document": lambda self, key: gets.append(key)})()
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=store,
        environ=ENV, model_call=lambda **kwargs: calls.append(kwargs))
    assert result["summary"]["extraction_attempted"] == 0
    assert gets == [] and calls == []


@pytest.mark.parametrize("value", ["not-a-date", "2026-08-09T12:00:00"])
def test_cutover_value_requires_strict_aware_iso_timestamp(value):
    class ConfigCursor:
        def execute(self, sql, params=()): pass
        def fetchone(self): return (value,)
    class ConfigConn:
        def cursor(self): return ConfigCursor()
    with pytest.raises(sbi_ongoing.CutoverConfigurationError):
        REAL_READ_CUTOVER(ConfigConn())


def test_missing_ledger_row_survives_manifest_without_write_error_or_call(tmp_path, monkeypatch):
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn, cutover: [99])
    monkeypatch.setattr(sbi_ongoing, "persist_manifest", REAL_PERSIST_MANIFEST)
    calls = []
    manifest_dir = tmp_path / "manifests"
    secret_env = dict(ENV, ANTHROPIC_API_KEY="anthropic-secret-xyz",
                      DATABASE_URL="postgres-secret-xyz",
                      R2_ACCESS_KEY_ID="r2-access-secret-xyz",
                      R2_SECRET_ACCESS_KEY="r2-secret-xyz")
    result = sbi_ongoing.run_sbi_lane(Conn(None), directory=tmp_path, store=EMPTY_STORE,
        environ=secret_env, model_call=lambda **kwargs: calls.append(kwargs),
        manifest_directory=manifest_dir)
    files = list(manifest_dir.glob("ongoing-*.json"))
    assert len(files) == 1 and result["manifest_path"] == str(files[0])
    manifest = json.loads(files[0].read_text())
    assert manifest["summary"] == result["summary"]
    assert manifest["model"] == "claude-sonnet-4-6"
    assert manifest["prompt_version"] == "sbi-v1.1"
    assert manifest["output_cap"] == 2000 and manifest["run_spend_cap"] == "1"
    assert manifest["cutover_at"] == "2026-08-09T00:00:00+00:00"
    assert manifest["actual_sbi_spend"] == "0.000000"
    assert manifest["spend_stopped"] is False
    assert manifest["summary"]["missing_ledger_rows"] == 1
    assert manifest["summary"]["write_errors"] == 0 and calls == []
    assert {"doc_id": 99, "status": "MISSING_LEDGER_ROW"} in manifest["records"]
    serialized = files[0].read_text()
    assert not any(secret in serialized for secret in (
        "anthropic-secret-xyz", "postgres-secret-xyz", "r2-access-secret-xyz",
        "r2-secret-xyz"))


def test_shared_estimator_includes_system_prompt_identically():
    pages = [{"page_number": 1, "text": "abcd" * 10}]
    expected = 10 + (len(sbi_sonnet.SYSTEM_PROMPT) + 3) // 4
    assert sbi_ongoing.estimate_input_tokens(pages) == expected


def test_cron_configuration_states_are_typed():
    assert cron.classify_sbi_configuration(sbi_ongoing.ongoing_configuration({})) == "skipped"
    assert cron.classify_sbi_configuration(sbi_ongoing.ongoing_configuration(
        {"SBI_SONNET_OUTPUT_CAP": "2000"})) == "warning"
    invalid = dict(ENV); invalid["SBI_SONNET_OUTPUT_CAP"] = "0"
    assert cron.classify_sbi_configuration(sbi_ongoing.ongoing_configuration(invalid)) == "warning"
    assert cron.classify_sbi_configuration(sbi_ongoing.ongoing_configuration(ENV)) == "configured"
