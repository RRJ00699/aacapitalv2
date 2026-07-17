"""Unit tests for _scripts/compute_verdicts.py — fnum + decide().
Covers every verdict path (TRADE / WATCH / CAUTION / AVOID) plus the
historical-bug regressions: poison '--0.0000' values and the
"JUNK · 60% base" AVOID wording the dial shows.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from compute_verdicts import fnum, decide, HARD_FLAGS, SOFT_FLAGS

pytestmark = pytest.mark.unit


# ---------- fnum: scraper poison tolerance (regression) ----------

@pytest.mark.parametrize("raw,expected", [
    ("--0.0000", -0.0),      # the actual poison value that leaked upstream
    ("--12.5", -12.5),
    ("-3.2", -3.2),
    ("  7 ", 7.0),
    ("", None), ("-", None), ("--", None),
    ("n/a", None), ("NA", None), ("null", None),
    (None, None), ("garbage", None),
    (42, 42.0), (0, 0.0),
])
def test_fnum(raw, expected):
    assert fnum(raw) == expected


# ---------- decide(): base rows ----------

def _listed(**kw):
    r = {"listing_date": "2026-01-01", "is_listed": True}
    r.update(kw); return r

def test_empty_unlisted_row_is_watch():
    out = decide({})
    assert out["verdict"] == "WATCH"
    assert "not listed yet" in out["why_caution"]
    assert out["confidence"] == "low"

def test_listed_no_signal_is_caution():
    assert decide(_listed())["verdict"] == "CAUTION"


# ---------- AVOID triggers ----------

def test_avoid_band():
    out = decide(_listed(score_band="AVOID"))
    assert out["verdict"] == "AVOID"
    assert "60% base" in out["why_avoid"]   # the dial's ledger line

def test_avoid_junk_size_floor():
    out = decide(_listed(issue_size_cr=199))
    assert out["verdict"] == "AVOID" and "200cr junk floor" in out["why_avoid"]

def test_size_200_exactly_not_junk():
    assert decide(_listed(issue_size_cr=200))["verdict"] != "AVOID"

def test_avoid_euphoric_gap():
    out = decide(_listed(listing_gap_pct=71))
    assert out["verdict"] == "AVOID" and "euphoric" in out["why_avoid"]

@pytest.mark.parametrize("field,val", [
    ("rhp_verdict", "REJECT — junk"), ("rhp_verdict", "avoid"),
    ("rhp_gate", "JUNK"), ("rhp_gate", "fail"),
])
def test_avoid_rhp_rejects(field, val):
    assert decide(_listed(**{field: val}))["verdict"] == "AVOID"

@pytest.mark.parametrize("flag", HARD_FLAGS)
def test_avoid_each_hard_flag(flag):
    out = decide(_listed(**{flag: True}))
    assert out["verdict"] == "AVOID" and flag.replace("_", " ") in out["why_avoid"]

def test_hard_flag_string_true_is_ignored():
    """Pinned: only boolean True trips a flag — 'true'/'1' from a bad scrape do not."""
    assert decide(_listed(auditor_qualified="true"))["verdict"] != "AVOID"


# ---------- CAUTION triggers ----------

def test_caution_rich_vs_peers():
    out = decide(_listed(ipo_pe=40, peer_median_pe=20))  # 1.3x < 40 <= 2.5x
    assert out["verdict"] == "CAUTION" and "richer than peers" in out["why_caution"]

def test_pe_above_2_5x_peer_is_extreme_premium():
    """Flag 2 FIX (review, MR #212): PE > 2.5× peer previously escaped the
    caution window entirely — the most overvalued got no valuation caution.
    Now mirrors compute_flags.py's 2.5× "expensive" red-flag threshold."""
    out = decide(_listed(ipo_pe=60, peer_median_pe=20))   # 3.0x
    assert "extreme premium" in out["why_caution"]
    assert out["verdict"] == "CAUTION"

def test_pe_exactly_2_5x_stays_in_verify_window():
    """Boundary: 2.5x exactly is still 'verify premium', not extreme."""
    out = decide(_listed(ipo_pe=50, peer_median_pe=20))
    assert "richer than peers" in out["why_caution"]
    assert "extreme premium" not in out["why_caution"]

def test_caution_coinflip_gap():
    out = decide(_listed(listing_gap_pct=30))
    assert out["verdict"] == "CAUTION" and "coin-flip" in out["why_caution"]

def test_caution_requires_dd():
    out = decide(_listed(requires_further_dd=True))
    assert "further due diligence" in out["why_caution"]

@pytest.mark.parametrize("flag", SOFT_FLAGS)
def test_soft_flags_caution_not_avoid(flag):
    out = decide(_listed(**{flag: True}))
    assert out["verdict"] == "CAUTION" and out["why_avoid"] is None


# ---------- TRADE triggers ----------

def test_trade_strategy1_sweet_spot_bull():
    out = decide(_listed(listing_gap_pct=5, regime_bull=True))
    assert out["verdict"] == "TRADE" and "STRATEGY 1" in out["why_trade"]

def test_strategy1_needs_bull():
    assert decide(_listed(listing_gap_pct=5, regime_bull=False))["verdict"] != "TRADE"

def test_strategy1_gap_15_is_out():
    out = decide(_listed(listing_gap_pct=15, regime_bull=True))
    assert "STRATEGY 1" not in (out["why_trade"] or "")

def test_trade_strategy2_quality_bull_listed():
    out = decide(_listed(quality_promoter=True, regime_bull=True))
    assert out["verdict"] == "TRADE" and "STRATEGY 2" in out["why_trade"]

def test_strategy2_needs_listing():
    out = decide({"quality_promoter": True, "regime_bull": True})
    assert out["verdict"] == "WATCH"

def test_trade_beats_avoid_when_both_fire():
    """Pinned precedence: STRATEGY 2 can override an AVOID band."""
    out = decide(_listed(score_band="AVOID", quality_promoter=True, regime_bull=True))
    assert out["verdict"] == "TRADE"

def test_junk_blocks_strategy1_but_not_strategy2():
    """Pinned: not_junk gate applies only to STRATEGY 1."""
    out = decide(_listed(issue_size_cr=100, listing_gap_pct=5, regime_bull=True))
    assert out["verdict"] == "AVOID"          # S1 suppressed by junk
    out2 = decide(_listed(issue_size_cr=100, quality_promoter=True, regime_bull=True))
    assert out2["verdict"] == "TRADE"         # S2 fires anyway


# ---------- confidence + regime label ----------

@pytest.mark.parametrize("band,rhp,expected", [
    ("STRONG", "accept", "high"), ("AVOID", "reject", "high"),
    ("FAVORABLE", "accept", "medium"), ("STRONG", None, "medium"),
    (None, None, "low"),
])
def test_confidence_matrix(band, rhp, expected):
    r = _listed()
    if band: r["score_band"] = band
    if rhp: r["rhp_verdict"] = rhp
    assert decide(r)["confidence"] == expected

@pytest.mark.parametrize("bull,label", [(True, "bull"), (False, "bear"), (None, None)])
def test_regime_label(bull, label):
    assert decide(_listed(regime_bull=bull))["regime"] == label
