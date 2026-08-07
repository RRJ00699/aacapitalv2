"""The single orchestration boundary for immutable document storage.

Callers provide an owner selected from Neon and downloaded PDF bytes.  This module
alone validates and hashes the bytes, creates/verifies the R2 object, and commits the
``documents`` ledger row.  R2 verification deliberately precedes every ledger write.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

if __package__:
    from . import r2
    from .document_contract import CONTRACT_VERSION, PDF_CONTENT_TYPE, document_key, validate_pdf_source
else:
    import r2
    from document_contract import CONTRACT_VERSION, PDF_CONTENT_TYPE, document_key, validate_pdf_source


class DocumentLedgerError(RuntimeError):
    """The verified object cannot safely be represented by the live ledger."""


@dataclass(frozen=True)
class StoredDocument:
    id: int
    object_key: str
    sha256: str
    byte_size: int
    created: bool


def _sha256(source: bytes | bytearray | memoryview | BinaryIO) -> str:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return hashlib.sha256(source).hexdigest()
    start = source.tell()
    digest = hashlib.sha256()
    try:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    finally:
        source.seek(start)
    return digest.hexdigest()


def store_document(
    conn,
    *,
    ipo_id: int,
    isin: str | None,
    doc_type: str,
    document_date: dt.date | dt.datetime | str,
    source_url: str | None,
    content: bytes | bytearray | memoryview | BinaryIO,
    content_type: str = PDF_CONTENT_TYPE,
    page_count: int | None = None,
    store: r2.R2DocumentStore | None = None,
    temporary_path: str | os.PathLike[str] | None = None,
    retain_path: str | os.PathLike[str] | None = None,
) -> StoredDocument:
    """Verify immutable R2 storage, then atomically insert/fill its ledger row.

    ``temporary_path`` is removed only after a successful commit.  A failed attempt
    retains it for diagnosis/retry and never changes an existing valid ledger row.
    """
    digest = _sha256(content)
    validated = validate_pdf_source(content, doc_type, digest, content_type=content_type)
    key = document_key(doc_type, digest, document_date, isin=isin, ipo_id=ipo_id)
    active_store = store or r2.R2DocumentStore()
    active_store.put_document_if_absent(
        key, validated.body, digest, doc_type=doc_type, content_type=content_type
    )

    cur = conn.cursor()
    created = False
    try:
        cur.execute(
            """SELECT id, ipo_id, doc_type, object_key, byte_size, content_type,
                      object_contract_version
                 FROM documents WHERE sha256=%s FOR UPDATE""",
            (digest,),
        )
        row = cur.fetchone()
        if row:
            doc_id, owner_id, existing_type, old_key, old_size, old_mime, old_version = row
            if owner_id != ipo_id or existing_type != doc_type:
                raise DocumentLedgerError("global sha256 row belongs to a different document owner")
            conflicts = (
                (old_key is not None and old_key != key)
                or (old_size is not None and old_size != validated.size)
                or (old_mime is not None and old_mime != PDF_CONTENT_TYPE)
                or (old_version is not None and old_version != CONTRACT_VERSION)
            )
            if conflicts:
                raise DocumentLedgerError("existing ledger metadata conflicts with verified R2 object")
            cur.execute(
                """UPDATE documents
                      SET source_url=COALESCE(source_url,%s),
                          object_key=COALESCE(object_key,%s),
                          byte_size=COALESCE(byte_size,%s),
                          content_type=COALESCE(content_type,%s),
                          object_contract_version=COALESCE(object_contract_version,%s),
                          page_count=COALESCE(page_count,%s)
                    WHERE id=%s RETURNING id""",
                (source_url, key, validated.size, PDF_CONTENT_TYPE, CONTRACT_VERSION, page_count, doc_id),
            )
            doc_id = cur.fetchone()[0]
        else:
            cur.execute(
                """INSERT INTO documents
                       (ipo_id,doc_type,url,source_url,object_key,sha256,byte_size,
                        content_type,object_contract_version,page_count,fetched_at)
                     VALUES (%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,now())
                     ON CONFLICT (sha256) DO NOTHING RETURNING id""",
                (ipo_id, doc_type, source_url, key, digest, validated.size,
                 PDF_CONTENT_TYPE, CONTRACT_VERSION, page_count),
            )
            inserted = cur.fetchone()
            if not inserted:
                raise DocumentLedgerError("concurrent sha256 insert; retry to verify ledger ownership")
            doc_id = inserted[0]
            created = True
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

    if temporary_path is not None:
        temporary = Path(temporary_path)
        if retain_path is None:
            temporary.unlink(missing_ok=True)
        else:
            destination = Path(retain_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.replace(destination)
    return StoredDocument(doc_id, key, digest, validated.size, created)
