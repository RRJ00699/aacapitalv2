import json
from pathlib import Path

from pipeline import cron, sbi_ongoing


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
    model = []
    result = sbi_ongoing.run_sbi_lane(Conn((7, 1, "key", "sha")), directory=tmp_path,
        store=EMPTY_STORE, environ=ENV, model_call=lambda **kwargs: model.append(kwargs))
    assert result["summary"]["already_ledgered"] == 1
    assert result["summary"]["already_extracted"] == 1 and model == []


def test_ledgered_extraction_failure_retries_without_local_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(sbi_ongoing, "pending_sbi_doc_ids", lambda conn: [7])
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
    env = dict(ENV); env.pop("SBI_SONNET_RUN_CAP_USD")
    try:
        sbi_ongoing.ongoing_price_card(env)
    except SystemExit as exc:
        assert "SBI_SONNET_RUN_CAP_USD" in str(exc)
    else:
        raise AssertionError("missing run cap must fail closed")


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
    monkeypatch.setattr(sbi_ongoing, "pdf_pages", lambda body: [{"page_number": 1, "text": "We recommend Subscribe"}])
    monkeypatch.setattr(sbi_ongoing.hashlib, "sha256", lambda body: type("H", (), {"hexdigest": lambda self: "sha"})())
    monkeypatch.setattr(sbi_ongoing, "write_extraction", lambda *a, **k: None)
    env = dict(ENV); env["SBI_SONNET_RUN_CAP_USD"] = "0.03005"
    calls = []
    store = type("Store", (), {"get_document": lambda self, key: b"bytes"})()
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=store, environ=env,
        model_call=lambda **kwargs: calls.append(1) or (_extraction(), 10, 20, "end_turn"))
    assert len(calls) == 1 and result["summary"]["spend_stopped"] == 1


def test_cron_sbi_source_is_runner_temp_and_failure_isolation_contract():
    source = Path(cron.__file__).read_text(encoding="utf-8")
    assert 'RUNNER_TEMP' in source and '"sbi-notes"' in source
    assert "from sbi_ongoing import ongoing_price_card, run_sbi_lane" in source
    assert "except (Exception, SystemExit)" in source
    assert source.index("isolated SBI lane failure") < source.index('"3. NSE per-IPO lifecycle"')
    assert "data/research_notes" not in source
    assert "parse_sbi_notes" not in source
