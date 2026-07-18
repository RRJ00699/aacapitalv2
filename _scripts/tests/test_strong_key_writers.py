#!/usr/bin/env python3
"""Write paths must resolve their target row by STRONG KEY, not fuzzy containment.

SCHEMA.md RULE 2 / owner rule: ISIN or exact normalized name, never fuzzy.

2026-07-18: `enrich_ipo_chittorgarh.py` resolved its UPDATE target with
`WHERE company_name ILIKE '%<company>%'`. It guarded on "exactly one hit", but a
single hit can be the WRONG row (e.g. "%Laser%" matching a different Laser
entity) — and it then UPDATEs it. Canon-equality is now tried first; containment
survives only as a logged last-resort fallback.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

WRITER = ROOT / "_scripts" / "ipo" / "enrich_ipo_chittorgarh.py"


def _src():
    return WRITER.read_text(encoding="utf-8")


def test_canon_match_is_attempted_first():
    s = _src()
    assert "regexp_replace(lower(" in s, "no canon normalisation in the writer"
    code = "\n".join(l for l in s.split("\n") if not l.strip().startswith("#"))
    assert code.index("regexp_replace(lower(") < code.index("ILIKE"), \
        "fuzzy ILIKE runs before canon — strong key must win"


def test_fuzzy_is_only_a_fallback():
    """The ILIKE query must be inside the `if not hits:` fallback branch."""
    s = _src()
    seg = s[s.index("match_mode = \"canon\""): s.index("if len(hits) != 1")]
    assert "if not hits:" in seg and "ILIKE" in seg, \
        "ILIKE is not gated behind an empty canon result"


def test_ambiguous_match_still_skips_the_write():
    assert re.search(r"if len\(hits\) != 1:[\s\S]{0,120}return", _src()), \
        "a non-unique match must never proceed to UPDATE"


def test_fuzzy_fallback_is_logged():
    """If we ever fall back to containment, it must be visible in the log —
    silent fuzzy matching is how wrong rows get written."""
    assert "matched" in _src() and "containment" in _src(), \
        "fuzzy fallback is not logged"


def test_update_targets_id_not_name():
    assert re.search(r"UPDATE ipo_intelligence SET \{sets\} WHERE id = %s", _src()), \
        "UPDATE must target the resolved primary key, never a name predicate"
