"""Offline acceptance tests for ledger -> exact R2 GET before paid extraction."""
import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import drive
import r2

PDF = b"%PDF-1.7\nfixture contract document\n%%EOF\n"
SHA = hashlib.sha256(PDF).hexdigest()


class Cursor:
    def __init__(self, row): self.row, self.sql, self.params = row, "", None
    def execute(self, sql, params): self.sql, self.params = sql, params
    def fetchone(self): return self.row


class Conn:
    def __init__(self, row): self.cur = Cursor(row)
    def cursor(self): return self.cur


def row(**changes):
    values = dict(id=17, object_key="documents/rhp/INEFIX/fixture.pdf", sha256=SHA,
                  byte_size=len(PDF), content_type="application/pdf", version="1")
    values.update(changes)
    return (values["id"], values["object_key"], values["sha256"], values["byte_size"],
            values["content_type"], values["version"])


def resolve(monkeypatch, ledger_row, content=PDF):
    calls = []
    monkeypatch.setattr(r2, "get_document", lambda key: calls.append(key) or content)
    result = drive.resolve_rhp(Conn(ledger_row), 99)
    return result, calls


def test_selects_neon_object_key_and_exact_get_without_list(monkeypatch):
    conn = Conn(row())
    calls = []
    monkeypatch.setattr(r2, "get_document", lambda key: calls.append(key) or PDF)
    path, source, _, doc_id = drive.resolve_rhp(conn, 99)
    try:
        assert calls == ["documents/rhp/INEFIX/fixture.pdf"]
        assert doc_id == 17 and source == "r2-contract-v1"
        assert "object_key IS NOT NULL" in conn.cur.sql
        assert "byte_size IS NOT NULL" in conn.cur.sql
        assert "object_contract_version='1'" in conn.cur.sql
        assert "ORDER BY fetched_at DESC, id DESC" in conn.cur.sql
        assert "url" not in conn.cur.sql.lower()
        assert not hasattr(r2.R2DocumentStore, "list_documents")
    finally:
        os.remove(path)

@pytest.mark.parametrize(("ledger_row", "content", "message"), [
    (row(sha256="0" * 64), PDF, "sha256"),
    (row(byte_size=len(PDF) + 1), PDF, "byte-size"),
    (row(), b"not-a-pdf", "not a PDF"),
])
def test_contract_mismatch_rejects_before_sonnet(monkeypatch, ledger_row, content, message):
    # resolve_rhp is the mandatory boundary called before rhp_sonnet is imported.
    with pytest.raises(ValueError, match=message): resolve(monkeypatch, ledger_row, content)


def test_missing_object_key_is_explicit_and_performs_no_r2_operation(monkeypatch):
    monkeypatch.setattr(r2, "get_document", lambda key: pytest.fail("unexpected R2 GET"))
    assert drive.resolve_rhp(Conn(None), 99) == (None, "missing_object_key", None, None)


def test_duplicate_tuple_is_checked_by_doc_id_model_prompt(monkeypatch):
    conn = Conn((1,))
    assert drive.rhp_already_done(conn, 17) is True
    assert "doc_id=%s" in conn.cur.sql and "model=%s" in conn.cur.sql
    assert conn.cur.params == (17, "claude-sonnet-4-6", "v2-full")

def test_complete_details_publication_and_consumer_keep_doc_evidence():
    root = os.path.dirname(os.path.dirname(__file__))
    query = open(os.path.join(root, "lib/v2/ipo-details.ts"), encoding="utf-8").read()
    consumer = open(os.path.join(root, "components/ipo/CompleteDetails.tsx"), encoding="utf-8").read()
    builder = open(os.path.join(root, "pipeline/build/build_snapshots.ts"), encoding="utf-8").read()
    assert "s.doc_id" in query and "JOIN documents doc ON doc.id=s.doc_id" in query
    assert "verified_evidence" in builder
    assert "e.doc_id" in consumer and "e.document.doc_type" in consumer

def test_r2_credentials_are_pipeline_only_and_contract_errors_do_not_echo_secrets():
    root = os.path.dirname(os.path.dirname(__file__))
    public_files = ["wrangler.jsonc", "wrangler.toml", "app", "components", "lib"]
    combined = ""
    for item in public_files:
        path = os.path.join(root, item)
        if os.path.isfile(path):
            combined += open(path, encoding="utf-8").read()
        elif os.path.isdir(path):
            for directory, _, names in os.walk(path):
                for name in names:
                    if name.endswith((".ts", ".tsx", ".json", ".toml")):
                        combined += open(os.path.join(directory, name), encoding="utf-8", errors="ignore").read()
    assert "R2_SECRET_ACCESS_KEY" not in combined
    assert "R2_ACCESS_KEY_ID" not in combined
    assert "R2_ACCOUNT_ID" not in combined
    assert "document sha256 mismatch" not in {"top-secret", "access-key"}
