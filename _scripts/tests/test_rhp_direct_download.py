#!/usr/bin/env python3
"""The RHP fetcher must pull the DIRECT pdf url, not click a viewer button.

2026-07-18 -> 2026-07-20: every download failed with "no download control".
The code only clicked a Download button INSIDE the PDF.js viewer iframe; when
that button did not render, nothing was fetched. Meanwhile Xtranet, Indo-MIM,
Lohia, Caliber, Laser, Alpine, SBI Funds and Kusumgar RHPs were ALL sitting on
SEBI's page 1 the entire time — the owner proved it with a screenshot.

SEBI embeds the real file at /sebi_data/attachdocs/<month>/<id>.pdf, wrapped in
/web/?file=<url>. Verified by hand on Caliber: %PDF-1.7, 13MB.

Extracting that URL is deterministic. Clicking a viewer button is not.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_scripts" / "fetch_new_rhps.py"
pytestmark = pytest.mark.unit


def _src():
    return SCRIPT.read_text(encoding="utf-8")


def test_extracts_the_direct_attachdocs_url():
    s = _src()
    assert "sebi_data/attachdocs" in s, "does not look for SEBI's real file path"
    assert re.search(r"re\.search\(", s), "no regex extraction of the pdf url"


def test_direct_path_runs_before_the_viewer_fallback():
    """Compare CODE positions, not prose — the explanatory comment mentions the
    old error string before the new logic appears."""
    code = "\n".join(l for l in _src().split("\n") if not l.strip().startswith("#"))
    assert code.index("sebi_data/attachdocs") < code.index("expect_download"), \
        "viewer-button path still runs first — the fragile route"


def test_verifies_the_bytes_are_a_pdf():
    """A SEBI viewer wrapper saved as .pdf cost an evening (2026-07-17)."""
    assert 'b"%PDF-"' in _src(), "no magic-byte check on the downloaded file"


def test_viewer_click_survives_as_fallback():
    """Keep it: some older filings may still only expose the viewer."""
    s = _src()
    assert "FALLBACK" in s and "expect_download" in s


def test_still_rejects_short_documents():
    assert "not a full RHP" in _src(), "page-count sanity check lost"


def test_placeholder_rows_do_not_block_the_target_list():
    """REGRESSION 2026-07-20: the target query excluded any IPO with a row in
    ipo_rhp_intel — including EMPTY placeholder rows. Xtranet, Indo-MIM and
    Lohia were therefore never searched for, while the log reported
    "0 match(es), 30 still pending" across all 12 SEBI pages and their RHPs sat
    on page 1 the whole time. Only a real extraction counts as "already have it".
    """
    assert "r.full_json IS NOT NULL" in _src(), \
        "placeholder rows still count as 'already have the RHP'"
