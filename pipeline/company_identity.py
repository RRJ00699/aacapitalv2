"""Shared deterministic company identity for document pipelines."""
import re
from dataclasses import dataclass

CORP_SUFFIXES = (
    "privatelimited", "pvtlimited", "corporation", "incorporated",
    "enterprises", "industries", "company", "limited", "private", "public",
    "corp", "pvt", "ltd", "inc", "co",
)


def canon(name):
    """Apply the established RHP corporate-name canonicalization semantics."""
    value = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    changed = True
    while changed and len(value) > 3:
        changed = False
        for suffix in CORP_SUFFIXES:
            if value.endswith(suffix) and len(value) - len(suffix) >= 3:
                value = value[:-len(suffix)]
                changed = True
                break
    return value


@dataclass(frozen=True)
class IdentityResult:
    row: tuple | None
    method: str
    ambiguous_count: int = 0


IDENTITY_SET_SQL = "SELECT id,isin,name_display,name_norm FROM ipo"


def load_company_identity_set(cur, execute=None):
    """Load the IPO identity spine once for deterministic batch resolution."""
    run = execute or cur.execute
    run(IDENTITY_SET_SQL, ())
    return tuple(cur.fetchall())


def resolve_company_identity(cur, *, isin=None, name_norm=None, company=None,
                             execute=None, identity_rows=None):
    """Resolve by exact ISIN/name, then unique canonical equality; never fuzzy."""
    run = execute or cur.execute
    if identity_rows is not None:
        rows = identity_rows
        if isin:
            hits = [row for row in rows if row[1] == isin]
            if len(hits) == 1:
                return IdentityResult(hits[0][:3], "EXACT_ISIN")
        if name_norm:
            hits = [row for row in rows if row[3] == name_norm]
            if len(hits) == 1:
                return IdentityResult(hits[0][:3], "EXACT_NAME_NORM")
    else:
        rows = None
    if isin:
        if rows is None:
            run("SELECT id,isin,name_display FROM ipo WHERE isin=%s", (isin,))
            row = cur.fetchone()
            if row:
                return IdentityResult(row, "EXACT_ISIN")
    if name_norm:
        if rows is None:
            run("SELECT id,isin,name_display FROM ipo WHERE name_norm=%s", (name_norm,))
            row = cur.fetchone()
            if row:
                return IdentityResult(row, "EXACT_NAME_NORM")
    wanted = canon(company or name_norm)
    if not wanted:
        return IdentityResult(None, "UNRESOLVED")
    if rows is None:
        rows = load_company_identity_set(cur, execute=run)
    hits = [row for row in rows
            if canon(row[2]) == wanted or canon(row[3]) == wanted]
    if len(hits) == 1:
        return IdentityResult(hits[0][:3], "CANONICAL_NAME")
    if len(hits) > 1:
        return IdentityResult(None, "AMBIGUOUS", len(hits))
    return IdentityResult(None, "UNRESOLVED")
