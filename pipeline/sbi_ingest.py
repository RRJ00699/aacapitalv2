#!/usr/bin/env python3
"""Owner-gated SBI PDF -> document ledger -> immutable R2 ingestion."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import sys
import tempfile

if __package__:
    from .document_ledger import store_document
    from .fill_ipo import _norm, resolve_ipo_id
else:
    from document_ledger import store_document
    from fill_ipo import _norm, resolve_ipo_id


def company_from_filename(path: pathlib.Path) -> str:
    return path.stem.split("_IPO Note", 1)[0].split("_IPO NOTE", 1)[0].strip()


def resolve_ipo(conn, *, isin: str | None, company: str | None):
    """Exact ISIN then exact canonical spine name; never fuzzy and never create."""
    cur = conn.cursor()
    ipo_id = resolve_ipo_id(cur, isin=isin, name_norm=_norm(company) if company else None)
    if ipo_id is None:
        return None
    cur.execute("SELECT id, isin, name_display FROM ipo WHERE id=%s", (ipo_id,))
    return cur.fetchone()


def ingest_file(conn, path, *, source_url=None, isin=None, store=None,
                owner_approved=False, document_date=None):
    path = pathlib.Path(path)
    owner = resolve_ipo(conn, isin=isin, company=company_from_filename(path))
    if owner is None:
        return {"status": "UNRESOLVED", "path": str(path)}
    if not owner_approved:
        return {"status": "READY_FOR_INGEST", "path": str(path), "ipo_id": owner[0]}
    content = path.read_bytes()
    saved = store_document(conn, ipo_id=owner[0], isin=owner[1], doc_type="sbi",
                           document_date=document_date or dt.date.today(),
                           source_url=source_url, content=content, store=store,
                           temporary_path=path)
    return {"status": "LEDGERED", "doc_id": saved.id, "object_key": saved.object_key,
            "sha256": saved.sha256, "created": saved.created, "ipo_id": owner[0]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--owner-approved", action="store_true")
    a = ap.parse_args(argv)
    if a.owner_approved and os.environ.get("SBI_OWNER_APPROVED") != "YES":
        sys.exit("real ingest requires both --owner-approved and SBI_OWNER_APPROVED=YES")
    import psycopg2
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is required for identity/ledger lookup")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    failed = 0
    try:
        for name in a.paths:
            try:
                print(ingest_file(conn, name, owner_approved=a.owner_approved))
            except Exception as exc:
                failed += 1
                print({"status": "FAILED", "path": name, "error": str(exc)}, file=sys.stderr)
    finally:
        conn.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
