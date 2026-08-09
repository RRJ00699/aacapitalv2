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


def resolve_company_identity(cur, *, isin=None, name_norm=None, company=None,
                             execute=None):
    """Resolve by exact ISIN/name, then unique canonical equality; never fuzzy."""
    run = execute or cur.execute
    if isin:
        run("SELECT id,isin,name_display FROM ipo WHERE isin=%s", (isin,))
        row = cur.fetchone()
        if row:
            return IdentityResult(row, "EXACT_ISIN")
    if name_norm:
        run("SELECT id,isin,name_display FROM ipo WHERE name_norm=%s", (name_norm,))
        row = cur.fetchone()
        if row:
            return IdentityResult(row, "EXACT_NAME_NORM")
    wanted = canon(company or name_norm)
    if not wanted:
        return IdentityResult(None, "UNRESOLVED")
    run("SELECT id,isin,name_display,name_norm FROM ipo", ())
    hits = [row for row in cur.fetchall()
            if canon(row[2]) == wanted or canon(row[3]) == wanted]
    if len(hits) == 1:
        return IdentityResult(hits[0][:3], "CANONICAL_NAME")
    if len(hits) > 1:
        return IdentityResult(None, "AMBIGUOUS", len(hits))
    return IdentityResult(None, "UNRESOLVED")
