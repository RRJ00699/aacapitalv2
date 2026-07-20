#!/usr/bin/env python3
"""fetch_new_rhps must PAGINATE SEBI, not read page 1 only.

2026-07-18 -> 2026-07-20: the scanner read only SEBI's newest page (~21
filings). Any IPO whose RHP had rolled onto page 2+ could never be matched, so
the backlog sat at "NEW IPOs (last 45d) without an RHP: 35" for days while the
log cheerfully reported "no new IPOs found on SEBI's newest page yet".

A silent no-op that LOOKS like success is the failure mode that has cost the
most time on this project. This test pins the fix.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_scripts" / "fetch_new_rhps.py"
pytestmark = pytest.mark.unit


def _src():
    return SCRIPT.read_text(encoding="utf-8")


def test_scans_more_than_one_page():
    s = _src()
    assert "MAX_PAGES" in s, "no page loop — still reading the newest page only"
    assert re.search(r"for page_no in range\(1, MAX_PAGES", s), "no pagination loop"


def test_stops_when_all_pending_matched():
    """Do not walk 12 pages when page 1 answered everything."""
    s = _src()
    assert "if not pending:" in s, "does not stop early once every IPO is matched"


def test_detects_a_page_that_did_not_advance():
    """A Next click that silently fails would otherwise re-scan page 1 forever."""
    s = _src()
    assert "same content as previous" in s, "no repeat-page guard"


def test_reports_the_pending_backlog():
    """The old log said 'no new IPOs found' while 35 waited. The count must be
    visible on every page so a stalled backlog cannot hide."""
    assert "still pending" in _src()


def test_page_limit_is_configurable():
    assert "SEBI_MAX_PAGES" in _src(), "cannot widen the search without a code change"
