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
import hashlib

if __package__:
    from .document_ledger import store_document
    from .fill_ipo import _norm
    from .company_identity import load_company_identity_set, resolve_company_identity
    from .sbi_identity_config import reviewed_decision
else:
    from document_ledger import store_document
    from fill_ipo import _norm
    from company_identity import load_company_identity_set, resolve_company_identity
    from sbi_identity_config import reviewed_decision


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


def resolve_ipo(conn, *, isin: str | None, company: str | None, counter=None,
                identity_rows=None):
    """Use shared exact/unique-canonical company identity resolution."""
    cur = conn.cursor()
    def execute(sql, params):
        if counter is not None:
            counter.neon_reads += 1
        cur.execute(sql, params)
    result = resolve_company_identity(cur, isin=isin,
        name_norm=_norm(company) if company else None, company=company,
        execute=execute, identity_rows=identity_rows)
    cur.close()
    return result


def approved_override_owner(conn, entry, *, identity_rows=None):
    """Accept an override only when its ID and ISIN identify the same spine row."""
    ipo_id, isin = entry["ipo_id"], entry["isin"]
    if identity_rows is not None:
        matches = [row for row in identity_rows if row[0] == ipo_id and row[1] == isin]
        return matches[0][:3] if len(matches) == 1 else None
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id,isin,name_display FROM ipo WHERE id=%s AND isin=%s",
            (ipo_id, isin),
        )
        rows = cur.fetchall()
        return rows[0] if len(rows) == 1 else None
    finally:
        close = getattr(cur, "close", None)
        if close:
            close()


def ingest_file(conn, path, *, source_url=None, isin=None, store=None,
                owner_approved=False, document_date=None, retain_source=None,
                identity_rows=None):
    path = pathlib.Path(path)
    content = path.read_bytes()
    local_sha256 = hashlib.sha256(content).hexdigest()
    decision = reviewed_decision(local_sha256, path.name)
    if decision and decision.kind == "exclusion":
        return {"status": "SKIPPED_REVIEWED_EXCLUSION", "path": str(path),
                "local_sha256": local_sha256,
                "classification": decision.entry["classification"]}
    if decision and decision.kind == "unapproved_override":
        return {"status": "UNRESOLVED", "path": str(path),
                "local_sha256": local_sha256,
                "identity_resolution": "UNAPPROVED_SHA_OVERRIDE", "ambiguous_count": 0}
    if decision and decision.kind == "override":
        owner = approved_override_owner(conn, decision.entry, identity_rows=identity_rows)
        if owner is None:
            return {"status": "INVALID_REVIEWED_OVERRIDE", "path": str(path),
                    "local_sha256": local_sha256,
                    "identity_resolution": "OVERRIDE_ID_ISIN_MISMATCH"}
        identity_method = "OWNER_APPROVED_SHA_OVERRIDE"
    else:
        identity = resolve_ipo(conn, isin=isin, company=company_from_filename(path),
                               identity_rows=identity_rows)
        owner = identity.row
        identity_method = identity.method
    if owner is None:
        return {"status": "UNRESOLVED", "path": str(path),
                "local_sha256": local_sha256, "identity_resolution": identity_method,
                "ambiguous_count": identity.ambiguous_count}
    if not owner_approved:
        return {"status": "READY_FOR_INGEST", "path": str(path), "ipo_id": owner[0]}
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
        cur = conn.cursor()
        identity_rows = load_company_identity_set(cur)
        cur.close()
        for name in a.paths:
            try:
                print(ingest_file(conn, name, owner_approved=a.owner_approved,
                                  identity_rows=identity_rows))
            except Exception as exc:
                failed += 1
                print({"status": "FAILED", "path": name, "error": str(exc)}, file=sys.stderr)
    finally:
        conn.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
