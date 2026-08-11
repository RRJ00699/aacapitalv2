import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from pipeline import cron, sbi_extraction_run as worker, sbi_ongoing, sbi_sonnet


CARD = worker.PriceCard(Decimal("3"), Decimal("15"), 100, Decimal("10"))
ENV = {
    "SBI_SONNET_INPUT_USD_PER_MTOK": "3",
    "SBI_SONNET_OUTPUT_USD_PER_MTOK": "15",
    "SBI_SONNET_OUTPUT_CAP": "100",
    "SBI_SONNET_RUN_CAP_USD": "10",
    "ANTHROPIC_API_KEY": "offline-test",
}
BODY = b"immutable-pdf"
DIGEST = hashlib.sha256(BODY).hexdigest()
PAGES = [{"page_number": 1, "text": "We recommend Subscribe"}]


def extraction(claims=True, facts=False):
    return {
        "claims": ([{"kind": "verdict", "statement": "Subscribe.",
                     "evidence_refs": ["P1:L001"],
                     "confidence": 0.8}] if claims else []),
        "scalar_facts": ([{"field": "sbi_rating", "value": "SUBSCRIBE",
                          "evidence_refs": ["P1:L001"],
                          "confidence": 0.7}] if facts else []),
    }


class Store:
    def __init__(self, bodies=None):
        self.bodies = bodies or {}
        self.gets = []
    def get_document(self, key):
        self.gets.append(key)
        if key not in self.bodies:
            raise FileNotFoundError(key)
        return self.bodies[key]


class Conn:
    def __init__(self):
        self.rollbacks = 0
    def cursor(self):
        return type("Cursor", (), {"close": lambda self: None})()
    def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def fake_worker_lock(monkeypatch):
    monkeypatch.setattr(worker, "try_acquire_worker_lock", lambda conn: True)
    monkeypatch.setattr(worker, "release_worker_lock", lambda conn: None)


def install_queue(monkeypatch, documents, completed, writes, *, write_error=None):
    monkeypatch.setattr(worker, "select_pending_documents", lambda conn, limit=None: [
        row for row in documents if row[0] not in completed][:limit])
    monkeypatch.setattr(worker, "already_extracted",
                        lambda conn, doc_id: doc_id in completed)
    def write(conn, *, doc_id, **kwargs):
        if write_error == doc_id:
            raise RuntimeError("write failed")
        writes.append(kwargs | {"doc_id": doc_id})
        completed.add(doc_id)
    monkeypatch.setattr(worker, "write_extraction", write)


def run_local(conn, store, **kwargs):
    return worker.run_pending_worker(
        conn, store=store, card=kwargs.pop("card", CARD), environ=ENV,
        page_reader=lambda body: PAGES,
        token_counter=kwargs.pop("token_counter", lambda **k: 10),
        model_call=kwargs.pop("model_call", lambda **k: (extraction(), 10, 20, "tool_use")),
        **kwargs)


def test_pending_query_is_db_only_and_uses_shared_completion_rule():
    sql, params = sbi_sonnet.pending_documents_query()
    assert "FROM documents d" in sql
    assert "d.doc_type='sbi'" in sql and "d.ipo_id IS NOT NULL" in sql
    assert "d.object_key IS NOT NULL" in sql and "NOT EXISTS" in sql
    assert "FROM insights" in sql and "FROM source_facts" in sql
    assert sbi_sonnet.MODEL in params and sbi_sonnet.PROMPT_VERSION in params
    source = Path(worker.__file__).read_text(encoding="utf-8")
    assert "data/research_notes" not in source
    assert "cutover" not in source.lower() and "historical" not in source.lower()


def test_198_without_local_pdfs_restart_70_then_128_and_future_document(monkeypatch, tmp_path):
    documents = [(i, i, f"key/{i}", DIGEST) for i in range(1, 199)]
    completed, writes = set(), []
    install_queue(monkeypatch, documents, completed, writes)
    store = Store({row[2]: BODY for row in documents})
    first = run_local(Conn(), store, limit=70)
    assert first["summary"]["selected"] == first["summary"]["EXTRACTED"] == 70
    second = run_local(Conn(), store)
    assert second["summary"]["selected"] == second["summary"]["EXTRACTED"] == 128
    documents.append((199, 199, "key/199", DIGEST)); store.bodies["key/199"] = BODY
    third = run_local(Conn(), store)
    assert third["summary"]["selected"] == third["summary"]["EXTRACTED"] == 1
    assert third["records"][0]["doc_id"] == 199
    assert list(tmp_path.glob("*.pdf")) == []


def test_completed_rerun_has_zero_model_calls(monkeypatch):
    completed, calls = {1}, []
    documents = [(1, 1, "key/1", DIGEST)]
    install_queue(monkeypatch, documents, completed, [])
    result = run_local(Conn(), Store({"key/1": BODY}),
                       model_call=lambda **k: calls.append(k))
    assert result["summary"]["selected"] == 0 and calls == []


def test_sha_mismatch_has_zero_model_calls(monkeypatch):
    docs, completed, calls = [(1, 1, "key/1", "wrong")], set(), []
    install_queue(monkeypatch, docs, completed, [])
    result = run_local(Conn(), Store({"key/1": BODY}),
                       model_call=lambda **k: calls.append(k))
    assert result["records"][0]["status"] == "SHA_MISMATCH" and calls == []


def test_insufficient_remaining_budget_stops_this_and_later_generation(monkeypatch):
    docs = [(i, i, f"key/{i}", DIGEST) for i in (1, 2)]
    install_queue(monkeypatch, docs, set(), [])
    calls = []
    tiny = worker.PriceCard(Decimal("3"), Decimal("15"), 100, Decimal("0.000001"))
    result = run_local(Conn(), Store({r[2]: BODY for r in docs}), card=tiny,
                       model_call=lambda **k: calls.append(k))
    assert calls == []
    assert [r["status"] for r in result["records"]] == ["SPEND_STOPPED"] * 2


def test_one_evidence_failure_does_not_stop_following_document(monkeypatch):
    docs = [(i, i, f"key/{i}", DIGEST) for i in (1, 2)]
    completed, writes, calls = set(), [], []
    install_queue(monkeypatch, docs, completed, writes)
    def model(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            bad = extraction(); bad["claims"][0]["evidence_refs"] = ["P1:L999"]
            return bad, 10, 20, "tool_use"
        return extraction(), 10, 20, "tool_use"
    result = run_local(Conn(), Store({r[2]: BODY for r in docs}), model_call=model)
    assert [r["status"] for r in result["records"]] == [
        "EVIDENCE_REJECTED", "EXTRACTED"]
    assert [w["doc_id"] for w in writes] == [2]


def test_model_error_stops_later_token_model_and_write_calls(monkeypatch):
    docs = [(i, i, f"key/{i}", DIGEST) for i in (1, 2)]
    completed, writes, token_calls, model_calls = set(), [], [], []
    install_queue(monkeypatch, docs, completed, writes)
    def model(**kwargs):
        model_calls.append(1)
        raise RuntimeError("delivery unknown")
    result = run_local(
        Conn(), Store({r[2]: BODY for r in docs}), model_call=model,
        token_counter=lambda **k: token_calls.append(1) or 10)
    assert [r["status"] for r in result["records"]] == [
        "MODEL_ERROR", "SPEND_STOPPED"]
    assert token_calls == [1] and model_calls == [1] and writes == []
    assert result["summary"]["spend_stopped"] is True


def test_last_selected_model_error_still_marks_spend_stopped(monkeypatch):
    docs, completed, writes = [(1, 1, "key/1", DIGEST)], set(), []
    install_queue(monkeypatch, docs, completed, writes)
    result = run_local(
        Conn(), Store({"key/1": BODY}),
        model_call=lambda **k: (_ for _ in ()).throw(RuntimeError("unknown spend")))
    assert [r["status"] for r in result["records"]] == ["MODEL_ERROR"]
    assert result["summary"]["SPEND_STOPPED"] == 0
    assert result["summary"]["spend_stopped"] is True


@pytest.mark.parametrize(("payload", "facts", "insights"), [
    (extraction(claims=False, facts=True), 1, 0),
    (extraction(claims=True, facts=False), 0, 1),
])
def test_facts_only_and_insights_only_count_complete(monkeypatch, payload, facts, insights):
    completed, writes = set(), []
    docs = [(1, 1, "key/1", DIGEST)]
    install_queue(monkeypatch, docs, completed, writes)
    result = run_local(Conn(), Store({"key/1": BODY}),
                       model_call=lambda **k: (payload, 10, 20, "tool_use"))
    assert result["records"][0]["status"] == "EXTRACTED"
    assert 1 in completed
    sql, _ = sbi_sonnet.extraction_predicate(1)
    assert "FROM insights" in sql and "FROM source_facts" in sql
    assert (len(payload["scalar_facts"]), len(payload["claims"])) == (facts, insights)


def test_doc_id_confidence_persist_and_write_is_atomic(monkeypatch):
    from pipeline import fill_v2
    calls = []
    monkeypatch.setattr(sbi_sonnet, "already_extracted", lambda *a: False)
    monkeypatch.setattr(fill_v2, "log_source_fact",
                        lambda *a, **k: calls.append(("fact", k)))
    monkeypatch.setattr(fill_v2, "upsert_insights",
                        lambda *a, **k: calls.append(("insight", k)) or (1, 0, "run"))
    conn = type("WriteConn", (), {"commits": 0, "cursor": lambda self: object(),
        "commit": lambda self: setattr(self, "commits", self.commits + 1)})()
    parsed = sbi_sonnet.parse_extraction(extraction(claims=True, facts=True), doc_id=7, pages=PAGES)
    sbi_sonnet.write_extraction(conn, ipo_id=9, doc_id=7,
                                extraction=parsed, validated=True)
    assert calls[0][1]["doc_id"] == 7 and calls[0][1]["confidence"] == 0.7
    assert calls[1][1]["doc_id"] == 7
    assert all(call[1]["commit"] is False for call in calls)
    assert conn.commits == 1


def test_evidence_rejection_makes_no_canonical_write(monkeypatch):
    docs, completed, writes = [(1, 1, "key/1", DIGEST)], set(), []
    install_queue(monkeypatch, docs, completed, writes)
    bad = extraction(); bad["claims"][0]["evidence_refs"] = ["P1:L999"]
    result = run_local(Conn(), Store({"key/1": BODY}),
                       model_call=lambda **k: (bad, 10, 20, "tool_use"))
    assert result["records"][0]["status"] == "EVIDENCE_REJECTED"
    assert writes == [] and completed == set()


def test_write_failure_rolls_back_and_document_remains_pending(monkeypatch):
    docs, completed, writes = [(1, 1, "key/1", DIGEST)], set(), []
    install_queue(monkeypatch, docs, completed, writes, write_error=1)
    conn = Conn()
    first = run_local(conn, Store({"key/1": BODY}))
    assert first["records"][0]["status"] == "WRITE_ERROR" and conn.rollbacks == 1
    assert completed == set()
    second = run_local(conn, Store({"key/1": BODY}))
    assert second["summary"]["selected"] == 1


def test_cron_invokes_single_worker_and_isolates_sbi_failure():
    source = Path(cron.__file__).read_text(encoding="utf-8")
    ongoing_source = Path(sbi_ongoing.__file__).read_text(encoding="utf-8")
    assert "run_sbi_lane" in source and "run_pending_worker" in ongoing_source
    assert "read_cutover" not in ongoing_source and "pending_sbi_doc_ids" not in ongoing_source
    assert source.index("isolated SBI lane failure") < source.index('"3. NSE per-IPO lifecycle"')


def test_lane_ingests_then_invokes_worker_with_no_real_io(tmp_path, monkeypatch):
    pdf = tmp_path / "Example Limited_IPO Note.pdf"; pdf.write_bytes(b"pdf")
    events = []
    monkeypatch.setattr(sbi_ongoing, "load_company_identity_set", lambda cur: ())
    monkeypatch.setattr(sbi_ongoing, "ingest_file", lambda *a, **k:
                        events.append("ingest") or {"status": "LEDGERED", "doc_id": 1,
                                                   "created": True})
    monkeypatch.setattr(sbi_ongoing, "run_pending_worker", lambda *a, **k:
                        events.append("worker") or {"summary": {"selected": 1}, "records": []})
    monkeypatch.setattr(sbi_ongoing, "persist_manifest", lambda *a, **k: "manifest.json")
    result = sbi_ongoing.run_sbi_lane(Conn(), directory=tmp_path, store=Store(),
                                      environ=ENV, model_call=lambda **k: None,
                                      token_counter=lambda **k: 1)
    assert events == ["ingest", "worker"] and result["summary"]["selected"] == 1


def test_no_sonnet_config_still_ingests_with_zero_paid_calls(tmp_path, monkeypatch):
    pdf = tmp_path / "Example Limited_IPO Note.pdf"; pdf.write_bytes(b"pdf")
    events = []
    monkeypatch.setattr(sbi_ongoing, "load_company_identity_set", lambda cur: ())
    monkeypatch.setattr(sbi_ongoing, "ingest_file", lambda *a, **k:
                        events.append("ingest") or {"status": "LEDGERED", "doc_id": 1,
                                                   "created": True})
    monkeypatch.setattr(sbi_ongoing, "run_pending_worker",
                        lambda *a, **k: events.append("worker"))
    monkeypatch.setattr(sbi_ongoing, "persist_manifest", lambda *a, **k: "manifest.json")
    token_calls, model_calls = [], []
    result = sbi_ongoing.run_sbi_lane(
        Conn(), directory=tmp_path, store=Store(), environ={},
        token_counter=lambda **k: token_calls.append(k),
        model_call=lambda **k: model_calls.append(k))
    assert events == ["ingest"]
    assert token_calls == model_calls == []
    assert result["summary"]["extraction_status"] == "SKIPPED_OWNER_NOT_CONFIGURED"


def test_production_worker_requires_owner_approval_with_zero_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "select_pending_documents",
                        lambda *a, **k: calls.append("select"))
    monkeypatch.setattr(worker, "write_extraction",
                        lambda *a, **k: calls.append("write"))
    result = worker.run_pending_worker(
        Conn(), store=Store({"key/1": BODY}), card=CARD, environ=ENV)
    assert result["summary"]["status"] == "OWNER_NOT_APPROVED"
    assert result["summary"]["actual_sbi_spend"] == "0.000000"
    assert calls == []


def test_cron_lane_cannot_bypass_owner_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(sbi_ongoing, "load_company_identity_set", lambda cur: ())
    monkeypatch.setattr(sbi_ongoing, "persist_manifest", lambda *a, **k: "manifest.json")
    calls = []
    monkeypatch.setattr(worker, "select_pending_documents",
                        lambda *a, **k: calls.append("select"))
    result = sbi_ongoing.run_sbi_lane(
        Conn(), directory=tmp_path, store=Store(), environ=ENV)
    assert result["summary"]["status"] == "OWNER_NOT_APPROVED"
    assert result["summary"]["extraction_status"] == "OWNER_NOT_APPROVED"
    assert calls == []


def test_cost_preflight_is_emitted_before_model_call(monkeypatch, capsys):
    docs, completed, writes = [(1, 1, "key/1", DIGEST)], set(), []
    install_queue(monkeypatch, docs, completed, writes)
    def model(**kwargs):
        output = capsys.readouterr().out
        assert "SBI PREFLIGHT" in output
        assert "selected=1" in output
        assert "generation=OWNER APPROVED" in output
        return extraction(), 10, 20, "tool_use"
    result = run_local(Conn(), Store({"key/1": BODY}), model_call=model)
    assert result["summary"]["EXTRACTED"] == 1


def test_read_transactions_end_before_external_io(monkeypatch):
    events = []
    class OrderedConn(Conn):
        def commit(self): events.append("commit")
    conn = OrderedConn()
    monkeypatch.setattr(worker, "select_pending_documents",
                        lambda conn, limit=None: events.append("pending_select") or [
                            (1, 1, "key/1", DIGEST)])
    monkeypatch.setattr(worker, "already_extracted",
                        lambda conn, doc_id: events.append("already_read") or False)
    monkeypatch.setattr(worker, "write_extraction",
                        lambda *a, **k: events.append("write"))
    class OrderedStore:
        def get_document(self, key): events.append("r2"); return BODY
    result = worker._run_pending_worker_locked(
        conn, store=OrderedStore(), card=CARD, environ=ENV,
        page_reader=lambda body: PAGES,
        token_counter=lambda **k: events.append("tokens") or 10,
        model_call=lambda **k: events.append("model") or (
            extraction(), 10, 20, "tool_use"))
    assert result["summary"]["EXTRACTED"] == 1
    assert events == ["pending_select", "commit", "already_read", "commit",
                      "r2", "tokens", "model", "write"]
    assert "remaining_pending" not in result["summary"]
    assert result["summary"]["retryable_selected"] == 0


def test_no_test_calls_real_network_or_production(monkeypatch):
    monkeypatch.setattr(worker, "_anthropic_request",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert worker.worker_configuration(ENV).status == "CONFIGURED"


def test_worker_lock_acquired_runs_normally(monkeypatch):
    calls = []
    class CommitConn(Conn):
        def commit(self): calls.append("commit")
    monkeypatch.setattr(worker, "try_acquire_worker_lock",
                        lambda conn: calls.append("acquire") or True)
    monkeypatch.setattr(worker, "release_worker_lock",
                        lambda conn: calls.append("release"))
    monkeypatch.setattr(worker, "_run_pending_worker_locked",
                        lambda conn, **kwargs: calls.append("run") or {
                            "summary": {"selected": 0}, "records": []})
    result = worker.run_pending_worker(CommitConn())
    assert result["summary"]["selected"] == 0
    assert calls == ["acquire", "commit", "run", "release", "commit"]


def test_worker_lock_unavailable_is_busy_with_zero_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "try_acquire_worker_lock", lambda conn: False)
    monkeypatch.setattr(worker, "_run_pending_worker_locked",
                        lambda *a, **k: calls.append("worker"))
    result = worker.run_pending_worker(
        Conn(), token_counter=lambda **k: calls.append("tokens"),
        model_call=lambda **k: calls.append("model"))
    assert result["summary"]["status"] == "WORKER_BUSY"
    assert result["summary"]["actual_sbi_spend"] == "0.000000"
    assert calls == []


def test_worker_exception_attempts_lock_release(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "try_acquire_worker_lock", lambda conn: True)
    monkeypatch.setattr(worker, "release_worker_lock",
                        lambda conn: calls.append("release"))
    monkeypatch.setattr(worker, "_run_pending_worker_locked",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        worker.run_pending_worker(Conn())
    assert calls == ["release"]


def test_lock_does_not_change_restart_idempotency(monkeypatch):
    documents = [(1, 1, "key/1", DIGEST)]
    completed, writes = set(), []
    install_queue(monkeypatch, documents, completed, writes)
    first = run_local(Conn(), Store({"key/1": BODY}))
    second = run_local(Conn(), Store({"key/1": BODY}))
    assert first["summary"]["EXTRACTED"] == 1
    assert second["summary"]["selected"] == 0
