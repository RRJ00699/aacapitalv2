"""Unit tests for _scripts/ipo_score.py — score_row + band_of.
The backtested numbers are the oracle: these tests PIN current behavior
(roadmap Phase 2). If a locked number changes intentionally, update here
with the backtest that justified it.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from ipo_score import band_of, score_row, BANDS

pytestmark = pytest.mark.unit


# ---------- band_of ----------

@pytest.mark.parametrize("score,expected", [
    (-99, "AVOID"), (-3, "AVOID"), (-2, "AVOID"),
    (-1, "NEUTRAL"), (0, "NEUTRAL"),
    (1, "FAVORABLE"), (2, "FAVORABLE"),
    (3, "STRONG"), (99, "STRONG"),
])
def test_band_boundaries(score, expected):
    assert band_of(score) == expected

def test_band_out_of_range_defaults_neutral():
    assert band_of(-100) == "NEUTRAL"
    assert band_of(100) == "NEUTRAL"

def test_bands_cover_all_integer_scores_contiguously():
    """Regression guard: no integer score may fall in a gap between bands."""
    for s in range(-10, 11):
        assert any(lo <= s <= hi for lo, hi, _ in BANDS), f"score {s} unbanded"


# ---------- score_row: each branch in isolation ----------

def test_empty_row_scores_zero_with_pending():
    s, why, pending = score_row({})
    assert s == 0 and why == []
    assert set(pending) == {"anchors", "peerPE"}

def test_mid_gap_scores_zero_dead_factor():
    """MID gap is DEAD (IPO_BUSINESS_REQUIREMENTS.md §5): the original +2 was
    measured on polluted data and collapsed to a coin-flip on clean data.
    Scoring it inflated the band on every MID-gap IPO.

    REGRESSION: this test FAILS on the pre-2026-07-18 code (which returned 2).
    If it ever returns to +2, a dead factor is back in the score."""
    s, why, _ = score_row({"gap_bucket": "mid"})   # case-insensitive
    assert s == 0, f"MID gap must contribute nothing, got {s}"
    assert not any("MID" in w for w in why), f"dead MID factor cited in why: {why}"


def test_high_gap_still_scored():
    """HIGH gap -1 is decayed but NOT dead — it must survive the MID removal."""
    s, why, _ = score_row({"gap_bucket": "HIGH"})
    assert s == -1 and "HIGH gap -1" in why

def test_high_gap_minus1():
    s, why, _ = score_row({"gap_bucket": "HIGH"})
    assert s == -1 and "HIGH gap -1" in why

@pytest.mark.parametrize("size,delta,tag", [
    (2000, 2, ">2000cr +2"),      # boundary: >= 2000
    (5000, 2, ">2000cr +2"),
    (150, -2, "150-500cr -2"),    # boundary: >= 150
    (499.99, -2, "150-500cr -2"), # boundary: < 500
])
def test_issue_size_branches(size, delta, tag):
    s, why, _ = score_row({"issue_size_cr": size})
    assert s == delta and tag in why

@pytest.mark.parametrize("size", [149.99, 500, 1999.99])
def test_issue_size_dead_zones_score_zero(size):
    """149.99 and the 500–1999 band contribute nothing — pinned."""
    s, why, _ = score_row({"issue_size_cr": size})
    assert s == 0 and why == []

def test_peer_cheap_plus1():
    s, why, _ = score_row({"ipo_pe": 10, "peer_median_pe": 20})  # 0.5 < 0.6
    assert s == 1 and "peer-cheap +1" in why

def test_peer_ratio_at_0_6_not_cheap():
    s, why, _ = score_row({"ipo_pe": 12, "peer_median_pe": 20})  # exactly 0.6
    assert "peer-cheap +1" not in why

def test_peer_pe_zero_no_division_error():
    s, why, _ = score_row({"ipo_pe": 10, "peer_median_pe": 0})
    assert "peer-cheap +1" not in why

@pytest.mark.parametrize("pe,delta,tag", [
    (60.01, 1, "PE>60 +1"),
    (30, -1, "PE30-60 -1"),
    (60, -1, "PE30-60 -1"),   # boundary: 60 is in the minus band
])
def test_pe_branches(pe, delta, tag):
    s, why, _ = score_row({"ipo_pe": pe})
    assert s == delta and tag in why

def test_pe_below_30_neutral():
    s, why, _ = score_row({"ipo_pe": 29.99})
    assert s == 0

def test_pending_cleared_when_present():
    _, _, pending = score_row({"anchor_count": 5, "peer_median_pe": 22})
    assert pending == []

def test_anchor_count_zero_still_pending():
    """Pinned: falsy anchor_count (0) reads as missing."""
    _, _, pending = score_row({"anchor_count": 0, "peer_median_pe": 22})
    assert "anchors" in pending


# ---------- regression fixture: known composite ----------

def test_composite_known_good():
    """Mega + peer-cheap = +2+1 = 3 → STRONG (band floor is 3).

    CHANGED 2026-07-18: previously 5, because MID gap added +2. MID gap is DEAD
    (§5). This row stays STRONG only because it sits on the band floor — a row
    that scored exactly 3 WITH the MID weight now scores 1 and drops from STRONG
    to FAVORABLE. That band shift is the inflation being removed."""
    r = {"gap_bucket": "MID", "issue_size_cr": 3000,
         "ipo_pe": 10, "peer_median_pe": 25, "anchor_count": 40}
    s, why, pending = score_row(r)
    assert s == 3 and band_of(s) == "STRONG" and pending == []


def test_mid_removal_can_shift_band_down():
    """The real user impact: a row that only reached STRONG because of MID gap
    now lands in FAVORABLE. Mega(+2) + MID(+2 dead) was 4=STRONG; now 2."""
    r = {"gap_bucket": "MID", "issue_size_cr": 3000}
    s, _, _ = score_row(r)
    assert s == 2 and band_of(s) == "FAVORABLE", f"got {s}/{band_of(s)}"


def test_mid_removal_costs_exactly_two_points():
    """Guard the size of the change: a MID row and a LOW row must now score
    identically — the gap bucket contributes nothing unless it is HIGH."""
    base = {"issue_size_cr": 3000, "ipo_pe": 10, "peer_median_pe": 25, "anchor_count": 40}
    mid, _, _ = score_row({**base, "gap_bucket": "MID"})
    low, _, _ = score_row({**base, "gap_bucket": "LOW"})
    high, _, _ = score_row({**base, "gap_bucket": "HIGH"})
    assert mid == low, "MID must no longer differ from LOW"
    assert high == mid - 1, "HIGH gap -1 must still apply"
