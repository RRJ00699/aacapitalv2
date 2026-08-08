"""Guard: dead pipeline steps stay removed.

Phase D archived two steps whose outputs no route or compute reads:
  - close_in_range.py  — CIR is REJECTED as pure leakage (IPO_BUSINESS_REQUIREMENTS §5)
  - match_anchor_deals.py — writes to institutional_large_deals, a table that does
    not exist; silent no-op

This test FAILS on the pre-Phase-D code (both are invoked in the pipeline) and
passes after. Re-adding either dead step to a pipeline file fails CI. Comments are
stripped before matching, so the "removed …" breadcrumbs don't trip it.

NOT removed and asserted still-present: fetch_delivery_bhavcopy.py — despite the
handover calling delivery "dead", app/api/post-listing/route.ts:85 reads
delivery_percentage FROM delivery_data (live screen, PostListingDashboard.tsx:56).
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

PIPELINES = ["_scripts/run_ipo_pipeline_lean.py", "compatibility/scripts/run_ipo_pipeline.py"]
DEAD_SCRIPTS = ["close_in_range.py", "match_anchor_deals.py"]
KEPT_SCRIPT = "fetch_delivery_bhavcopy.py"   # delivery feeds the post-listing route


def _code_only(path):
    """Return the file's source with the comment portion of each line removed."""
    out = []
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


def test_dead_steps_not_invoked_in_pipelines():
    offenders = []
    for p in PIPELINES:
        code = _code_only(p)
        for s in DEAD_SCRIPTS:
            if s in code:
                offenders.append(f"{p} still invokes {s}")
    assert not offenders, (
        "Dead pipeline steps re-introduced (CIR leakage / non-existent "
        "institutional_large_deals):\n  " + "\n  ".join(offenders))


def test_dead_step_scripts_are_archived_not_deleted():
    for s in DEAD_SCRIPTS:
        assert not (ROOT / "_scripts" / s).exists(), f"{s} should have moved to _archive/"
        assert (ROOT / "_archive" / "_scripts" / s).exists(), f"{s} missing from _archive/"


def test_delivery_step_is_kept():
    """Regression guard: delivery is NOT dead — a live route reads delivery_data."""
    lean = _code_only("_scripts/run_ipo_pipeline_lean.py")
    assert KEPT_SCRIPT in lean, "delivery step was removed, but post-listing route reads delivery_data"
