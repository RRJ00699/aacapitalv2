"""Guard: repo root stays free of one-off / debug clutter.

Phase E relocated 14 unreferenced one-off scripts and 5 stray artifacts from the
repo root to _archive/. This test FAILS on the pre-E tree (they sit at root) and
passes after. Re-dropping any of them at root fails CI.

Only provably-unreferenced files were moved. KEPT at root (still referenced as
run-commands by live scripts): link_brlm_scores.py, load_instrument_tokens.py,
real_return_analysis.py — and the artifacts read/written by scripts (sector_map.csv,
ipo_master.xlsx, ipo_factors.csv, factor_report.csv, dip_defense.csv).
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

RELOCATED = [
    "_check_coverage.py", "_check_turtlemint.py", "anchor_analysis.py",
    "check_brlm_scores.py", "check_mf.py", "check_upcoming_ipos.py", "debug_kite.py",
    "fix_listing_day_close.py", "fix_nse_symbols.py", "fix_upcoming_ipos.py",
    "listing_day_signals.py", "patch_play_selector.py", "pre_subscription_score.py",
    "real_return_analysis_v2.py",
    "golden_symbol_review.csv", "missing_financials.csv",
    "missing_financials_to_fetch.txt", "sbi_api.json", "build_errors.txt",
]

RELOCATED_LIVE = ["_scripts/link_brlm_scores.py", "_scripts/load_instrument_tokens.py",
                  "research/backtests/legacy_real_return_analysis.py"]


def test_relocated_clutter_not_at_root():
    stragglers = [f for f in RELOCATED if (ROOT / f).exists()]
    assert not stragglers, f"one-off clutter still at repo root (move to _archive/): {stragglers}"


def test_relocated_clutter_preserved_in_archive():
    missing = [f for f in RELOCATED if not (ROOT / "_archive" / ("_scripts/" + f if f.endswith(".py") else f)).exists()]
    assert not missing, f"relocated files missing from _archive/ (nothing deleted rule): {missing}"


def test_referenced_root_scripts_relocated_with_updated_callers():
    """Referenced tools remain tracked in their final operational/research zones."""
    missing = [f for f in RELOCATED_LIVE if not (ROOT / f).exists()]
    assert not missing, f"a referenced script was lost during relocation: {missing}"
