from hashlib import sha256
from pathlib import Path
from collections import Counter

import pytest

import document_ledger as ledger
from document_contract import CONTRACT_VERSION, PDF_CONTENT_TYPE
from pipeline.sbi_bounded_ingest import CountingConnection


PDF = b"%PDF-1.7\n" + b"x" * (100 * 1024)


class FakeStore:
    def __init__(self, *, put_error=None, verify_error=None):
        self.put_error = put_error
        self.verify_error = verify_error
        self.objects = {}
        self.put_calls = 0
        self.verify_calls = 0

    def put_document_if_absent(self, key, content, digest, **_kwargs):
        if self.put_error:
            raise self.put_error
        if key not in self.objects:
            self.put_calls += 1
            if isinstance(content, (bytes, bytearray, memoryview)):
                size = len(content)
            else:
                start = content.tell()
                content.seek(0, 2)
                size = content.tell() - start
                content.seek(start)
            self.objects[key] = (digest, size)
        self.verify_document(key, *self.objects[key])
        return "r2://unit/" + key

    def verify_document(self, key, digest, size):
        self.verify_calls += 1
        if self.verify_error:
            raise self.verify_error
        assert self.objects.get(key) == (digest, size)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = None

    def execute(self, sql, params):
        if self.conn.fail_db and ("INSERT INTO documents" in sql or "UPDATE documents" in sql):
            raise RuntimeError("db failed")
        if "SELECT id, ipo_id" in sql:
            row = self.conn.rows.get(params[0])
            self.result = None if row is None else (
                row["id"], row["ipo_id"], row["doc_type"], row.get("object_key"),
                row.get("byte_size"), row.get("content_type"), row.get("version"),
            )
        elif "INSERT INTO documents" in sql:
            ipo_id, doc_type, source_url, key, digest, size, mime, version, page_count = params
            if digest in self.conn.rows:
                self.result = None
            else:
                doc_id = len(self.conn.rows) + 1
                self.conn.rows[digest] = dict(id=doc_id, ipo_id=ipo_id, doc_type=doc_type,
                    source_url=source_url, object_key=key, byte_size=size,
                    content_type=mime, version=version, url=None, page_count=page_count)
                self.result = (doc_id,)
        elif "UPDATE documents" in sql:
            source_url, key, size, mime, version, page_count, doc_id = params
            row = next(r for r in self.conn.rows.values() if r["id"] == doc_id)
            row.update(source_url=row.get("source_url") or source_url,
                       object_key=row.get("object_key") or key,
                       byte_size=row.get("byte_size") or size,
                       content_type=row.get("content_type") or mime,
                       version=row.get("version") or version,
                       page_count=row.get("page_count") or page_count)
            self.result = (doc_id,)

    def fetchone(self):
        return self.result

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None, fail_db=False):
        self.rows = rows or {}
        self.fail_db = fail_db
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def save(conn, store, content=PDF, **kwargs):
    return ledger.store_document(conn, ipo_id=7, isin="INE17IR01028", doc_type="rhp",
        document_date="2026-08-06", source_url="https://www.sebi.gov.in/official",
        content=content, store=store, **kwargs)


def test_same_pdf_is_one_object_and_one_ledger_identity():
    conn, store = FakeConn(), FakeStore()
    first = save(conn, store)
    second = save(conn, store)
    assert first.id == second.id and len(conn.rows) == 1 and store.put_calls == 1
    row = next(iter(conn.rows.values()))
    assert row["source_url"].startswith("https://www.sebi.gov.in/")
    assert row["url"] is None
    assert row["content_type"] == PDF_CONTENT_TYPE and row["version"] == CONTRACT_VERSION


def test_new_sha_is_a_new_immutable_object():
    conn, store = FakeConn(), FakeStore()
    save(conn, store)
    save(conn, store, content=PDF + b"new")
    assert len(conn.rows) == 2 and store.put_calls == 2


def test_two_new_documents_each_execute_one_ledger_read_and_one_write():
    counts = Counter()
    conn, store = CountingConnection(FakeConn(), counts), FakeStore()

    save(conn, store, content=PDF + b"one")
    save(conn, store, content=PDF + b"two")

    assert counts["document_ledger_reads"] == 2
    assert counts["document_ledger_writes"] == 2
    assert counts["neon_reads"] == 2
    assert counts["neon_writes"] == 2


def test_invalid_pdf_is_rejected_before_r2_or_ledger():
    conn, store = FakeConn(), FakeStore()
    with pytest.raises(ValueError, match="magic"):
        save(conn, store, content=b"wrong" + b"x" * (100 * 1024))
    assert store.put_calls == 0 and conn.rows == {}


@pytest.mark.parametrize("failure", ["put", "verify"])
def test_r2_failure_never_writes_ledger(failure):
    store = FakeStore(put_error=RuntimeError("put") if failure == "put" else None,
                      verify_error=RuntimeError("head") if failure == "verify" else None)
    conn = FakeConn()
    with pytest.raises(RuntimeError):
        save(conn, store)
    assert conn.rows == {} and conn.commits == 0


def test_db_failure_after_upload_is_retryable_without_second_put():
    store = FakeStore()
    failed = FakeConn(fail_db=True)
    with pytest.raises(RuntimeError, match="db failed"):
        save(failed, store)
    assert store.put_calls == 1 and failed.rollbacks == 1
    recovered = FakeConn()
    save(recovered, store)
    assert store.put_calls == 1 and len(recovered.rows) == 1


def test_temp_cleanup_only_after_commit(tmp_path: Path):
    temp = tmp_path / "download.pdf"
    temp.write_bytes(PDF)
    with temp.open("rb") as source:
        save(FakeConn(), FakeStore(), content=source, temporary_path=temp)
    assert not temp.exists()

    retained = tmp_path / "failed.pdf"
    retained.write_bytes(PDF)
    with retained.open("rb") as source, pytest.raises(RuntimeError):
        save(FakeConn(fail_db=True), FakeStore(), content=source, temporary_path=retained)
    assert retained.exists()


def test_global_sha_owner_mismatch_fails_closed():
    digest = sha256(PDF).hexdigest()
    rows = {digest: dict(id=1, ipo_id=99, doc_type="rhp", object_key=None,
                         byte_size=None, content_type=None, version=None)}
    with pytest.raises(ledger.DocumentLedgerError, match="different document owner"):
        save(FakeConn(rows), FakeStore())
