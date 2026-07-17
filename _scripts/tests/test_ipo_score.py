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

def test_mid_gap_plus2():
    s, why, _ = score_row({"gap_bucket": "mid"})   # case-insensitive
    assert s == 2 and "MID gap +2" in why

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
    """Mega, MID-gap, peer-cheap, low-PE row → +2+2+1 = 5 → STRONG."""
    r = {"gap_bucket": "MID", "issue_size_cr": 3000,
         "ipo_pe": 10, "peer_median_pe": 25, "anchor_count": 40}
    s, why, pending = score_row(r)
    assert s == 5 and band_of(s) == "STRONG" and pending == []
