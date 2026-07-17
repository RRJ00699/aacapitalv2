"""Unit tests for _scripts/compute_flags.py — scan().
Every red-flag and green-check branch, boundary values, truthiness semantics,
and a cross-module consistency test locking the 2.5x 'expensive' threshold to
the verdict engine's 'extreme premium' caution (Flag 2 fix, MR #212).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from compute_flags import scan, fnum as flags_fnum
from compute_verdicts import decide

pytestmark = pytest.mark.unit


def test_empty_row_no_flags():
    red, green = scan({})
    assert red == [] and green == []


# ---------- governance red flags ----------

@pytest.mark.parametrize("field,label", [
    ("auditor_qualified", "auditor qualified opinion"),
    ("sebi_action", "SEBI action on record"),
    ("criminal_litigation", "criminal litigation"),
    ("promoter_pledge_flag", "promoter shares pledged"),
    ("related_party_concern", "related-party concern"),
    ("customer_concentration_high", "customer concentration high"),
    ("contingent_liabilities_material", "material contingent liabilities"),
])
def test_each_governance_red_flag(field, label):
    red, _ = scan({field: True})
    assert red == [label]

def test_governance_flags_are_truthy_not_boolean_gated():
    """Pinned: unlike decide()'s `is True` gate, scan() fires on ANY truthy —
    a string 'true' from a bad scrape WOULD flag here. Divergence documented."""
    red, _ = scan({"sebi_action": "true"})
    assert "SEBI action on record" in red

@pytest.mark.parametrize("val", ["", "clean", None])
def test_numbers_integrity_clean_values_pass(val):
    red, _ = scan({"numbers_integrity_flag": val})
    assert red == []

def test_numbers_integrity_concern_flags():
    red, _ = scan({"numbers_integrity_flag": "restated"})
    assert "numbers-integrity concern" in red


# ---------- quantitative red flags (boundaries) ----------

@pytest.mark.parametrize("row,expect_in_red", [
    ({"issue_size_cr": 199.99}, "junk floor"),
    ({"ofs_pct": 60.01}, "OFS-heavy"),
    ({"ipo_pe": 51, "peer_median_pe": 20}, "expensive"),   # >2.5x
    ({"debt_equity": 2.01}, "high leverage"),
])
def test_quant_red_flags_fire(row, expect_in_red):
    red, _ = scan(row)
    assert any(expect_in_red in f for f in red)

@pytest.mark.parametrize("row", [
    {"issue_size_cr": 200},                      # boundary: 200 exactly is NOT junk
    {"ofs_pct": 60},                             # 60 exactly is NOT OFS-heavy
    {"ipo_pe": 50, "peer_median_pe": 20},        # 2.5x exactly is NOT expensive
    {"debt_equity": 2},                          # 2.0 exactly is NOT high leverage
    {"ipo_pe": 51, "peer_median_pe": 0},         # zero peer PE: no div, no flag
])
def test_quant_red_flag_boundaries_do_not_fire(row):
    red, _ = scan(row)
    assert red == []


# ---------- green checks (boundaries) ----------

@pytest.mark.parametrize("row,expect_in_green", [
    ({"issue_size_cr": 2000}, "mega issue"),
    ({"ofs_pct": 29.99}, "fresh-issue heavy"),
    ({"final_qib": 10}, "strong QIB"),
    ({"ipo_pe": 17.9, "peer_median_pe": 20}, "cheaper than peers"),  # <0.9x
    ({"debt_equity": 0.3}, "low debt"),
])
def test_green_checks_fire(row, expect_in_green):
    _, green = scan(row)
    assert any(expect_in_green in g for g in green)

@pytest.mark.parametrize("row", [
    {"issue_size_cr": 1999.99}, {"ofs_pct": 30}, {"final_qib": 9.99},
    {"ipo_pe": 18, "peer_median_pe": 20},        # 0.9x exactly not cheap
    {"debt_equity": 0.31},
])
def test_green_check_boundaries_do_not_fire(row):
    _, green = scan(row)
    assert green == []

def test_rhp_clean_green_requires_no_reds():
    _, green = scan({"rhp_verdict": "accept"})
    assert "RHP forensic clean" in green
    red, green2 = scan({"rhp_verdict": "accept", "sebi_action": True})
    assert "RHP forensic clean" not in green2

def test_size_dead_zone_neither_flag():
    red, green = scan({"issue_size_cr": 1000})   # 200–1999: neither junk nor mega
    assert red == [] and green == []


# ---------- cross-module consistency (Flag 2 fix lock) ----------

def test_expensive_threshold_agrees_with_verdict_extreme_premium():
    """LOCK: the 2.5x boundary must mean the same thing in both modules.
    Above it: flags say 'expensive' AND the verdict cautions 'extreme premium'.
    At/below it: neither fires. If either module's threshold drifts, this fails."""
    above = {"ipo_pe": 60, "peer_median_pe": 20,
             "listing_date": "2026-01-01", "is_listed": True}
    red, _ = scan(above)
    v = decide(above)
    assert any("expensive" in f for f in red)
    assert "extreme premium" in v["why_caution"]

    at = {"ipo_pe": 50, "peer_median_pe": 20,
          "listing_date": "2026-01-01", "is_listed": True}
    red_at, _ = scan(at)
    v_at = decide(at)
    assert red_at == []
    assert "extreme premium" not in (v_at["why_caution"] or "")


# ---------- fnum divergence ----------

def test_flags_fnum_stricter_than_verdicts_fnum():
    """Pinned divergence: flags' fnum does NOT strip '--' poison — '--0.5'
    reads as None here but -0.5 in compute_verdicts. Documented, not fixed."""
    assert flags_fnum("--0.5") is None
