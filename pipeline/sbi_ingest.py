#!/usr/bin/env python3
"""Owner-gated SBI PDF -> document ledger -> immutable R2 ingestion."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import re
import subprocess
import sys

if __package__:
    from .document_ledger import store_document
    from .fill_ipo import _norm
    from .company_identity import resolve_company_identity
else:
    from document_ledger import store_document
    from fill_ipo import _norm
    from company_identity import resolve_company_identity


ROOT = pathlib.Path(__file__).resolve().parents[1]
FILENAME_DATE = re.compile(r"(?<!\d)(\d{2})-(\d{2})-(\d{4})(?!\d)")


def company_from_filename(path: pathlib.Path) -> str:
    return path.stem.split("_IPO Note", 1)[0].split("_IPO NOTE", 1)[0].strip()


def document_date_from_filename(path: pathlib.Path) -> dt.date | None:
    """Return a valid filename date using the sole supported rule DD-MM-YYYY.

    Other layouts are deliberately ignored rather than guessed. Invalid calendar
    dates are also ignored and the caller uses the ingest date.
    """
    match = FILENAME_DATE.search(path.name)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def is_git_tracked(path: pathlib.Path) -> bool:
    """Identify retained sources without coupling production to a data directory."""
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", str(relative)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


def resolve_ipo(conn, *, isin: str | None, company: str | None, counter=None):
    """Use shared exact/unique-canonical company identity resolution."""
    cur = conn.cursor()
    def execute(sql, params):
        if counter is not None:
            counter.neon_reads += 1
        cur.execute(sql, params)
    result = resolve_company_identity(cur, isin=isin,
        name_norm=_norm(company) if company else None, company=company,
        execute=execute)
    cur.close()
    return result


def ingest_file(conn, path, *, source_url=None, isin=None, store=None,
                owner_approved=False, document_date=None, retain_source=None):
    path = pathlib.Path(path)
    identity = resolve_ipo(conn, isin=isin, company=company_from_filename(path))
    owner = identity.row
    if owner is None:
        return {"status": "UNRESOLVED", "path": str(path),
                "identity_resolution": identity.method,
                "ambiguous_count": identity.ambiguous_count}
    if not owner_approved:
        return {"status": "READY_FOR_INGEST", "path": str(path), "ipo_id": owner[0]}
    content = path.read_bytes()
    retained = is_git_tracked(path) if retain_source is None else retain_source
    effective_date = document_date or document_date_from_filename(path) or dt.date.today()
    saved = store_document(conn, ipo_id=owner[0], isin=owner[1], doc_type="sbi",
                           document_date=effective_date,
                           source_url=source_url, content=content, store=store,
                           temporary_path=None if retained else path)
    return {"status": "LEDGERED", "doc_id": saved.id, "object_key": saved.object_key,
            "sha256": saved.sha256, "created": saved.created, "ipo_id": owner[0],
            "document_date": effective_date.isoformat(),
            "source_retained": retained}


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
