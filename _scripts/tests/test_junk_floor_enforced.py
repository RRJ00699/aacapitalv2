#!/usr/bin/env python3
"""The Rs.200cr junk floor must EXCLUDE, not merely label.

docs/specifications/IPO_BUSINESS_REQUIREMENTS.md §2 (owner-locked): issue size < Rs.200cr is
"RULED OUT — below this floor, don't touch". Until 2026-07-18 the engine only
appended an avoid-reason (compute_verdicts.py:61) and the IPO still rendered
beside real candidates — the opposite of "filter junk, focus on good companies".

The route now splits the payload: `cards` (investable) and `filtered` (junk,
each carrying `filtered_reason`). Nothing is hidden or lost; it is enforced.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
# PR #282 moved the command-feed logic into lib/v2/ipo-command.ts (enrichCards splits
# investable/filtered; buildCommand assembles the payload). Contract unchanged.
ROUTE = ROOT / "lib" / "v2" / "ipo-command.ts"
pytestmark = pytest.mark.unit


def _src():
    return ROUTE.read_text(encoding="utf-8")


def test_junk_floor_constant_is_200():
    m = re.search(r"const\s+JUNK_FLOOR_CR\s*=\s*(\d+)", _src())
    assert m, "JUNK_FLOOR_CR missing — the floor is not enforced in the route"
    assert int(m.group(1)) == 200, f"floor is {m.group(1)}cr, spec says 200cr"


def test_payload_splits_cards_and_filtered():
    """REGRESSION: pre-2026-07-18 the payload was `cards: enrichedCards` with no
    split, so a Rs.126cr IPO rendered as a normal candidate."""
    s = _src()
    assert "cards: investable" in s, "cards must serve the investable list only"
    assert "filtered," in s and "filtered_count" in s, "filtered list not exposed"


def test_filtered_entries_carry_a_reason():
    assert "filtered_reason" in _src(), "junk must state WHY it was ruled out"


def test_split_uses_size_not_verdict():
    """The floor is a hard size rule — it must not depend on the verdict engine
    having run (a null verdict must still be filtered)."""
    s = _src()
    block = s[s.index("const investable"): s.index("const withResearch")]
    assert "issue_size_cr" in block, "split must key off issue size"
    assert "sz > 0 && sz < JUNK_FLOOR_CR" in block, \
        "must filter only real sub-floor sizes (0/unknown stays investable)"


def test_verdict_engine_still_records_the_reason():
    """compute_verdicts keeps its avoid-reason — the split is enforcement, the
    reason is still needed for the card's why-not list."""
    cv = (ROOT / "_scripts" / "compute_verdicts.py").read_text(encoding="utf-8")
    assert "junk floor" in cv, "verdict engine lost the junk-floor reason"
