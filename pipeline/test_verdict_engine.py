"""DB-free unit tests pinning the V2 verdict taxonomy (plan C6, C5).

These exercise the pure `decide()` extracted from `compute_decision`, so no database is
required. They pin the owner's rules: missing-financials -> WATCH (never JUNK), the
structural JUNK line, append-only decisions, and the engine_version bump.
"""
import inspect
import re

import verdict_engine as ve


def _decide(**overrides):
    base = dict(score=None, band=None, missing=[], red_count=0, junk_sigs=[],
                measured=False, has_row=True, mf=None, size=None, good_set="strong")
    base.update(overrides)
    return ve.decide(**base)


def test_missing_financials_is_watch_never_junk():
    # No valuation / missing financial inputs, no structural junk signal -> WATCH.
    for missing in (["no_valuation"], ["pe_no_financials", "pb_no_financials"], ["no_valuation", "ronw_missing"]):
        d = _decide(missing=missing, band=None, has_row=True, junk_sigs=[], mf=None, size=200)
        assert d["verdict"] == "WATCH", (missing, d)
        assert any("missing_inputs" in r for r in d["reasons"])


def test_missing_financials_cannot_reach_good():
    # Even with a STRONG band and a clean measured RHP, a missing input blocks GOOD -> WATCH.
    d = _decide(missing=["pe_no_financials"], band="STRONG", measured=True, red_count=0, size=500)
    assert d["verdict"] == "WATCH"


def test_structural_junk_line_is_unchanged():
    # The only JUNK triggers remain the owner's structural line.
    assert _decide(mf=0, size=500)["verdict"] == "JUNK"                       # mf_shares_bid == 0
    assert _decide(size=120)["verdict"] == "JUNK"                             # issue_size < 150cr
    assert _decide(junk_sigs=["going_concern"], size=500)["verdict"] == "JUNK"  # severe RHP signal
    # A benign red-flag signal is NOT junk -> WATCH.
    assert _decide(junk_sigs=["auditor_qualified"], size=500)["verdict"] == "WATCH"


def test_good_still_reachable_with_complete_clean_strong():
    d = _decide(missing=[], band="STRONG", measured=True, red_count=0, has_row=True, size=500)
    assert d["verdict"] == "GOOD"


def test_severe_junk_wins_even_with_missing_financials():
    # A genuine SEVERE signal still classifies JUNK; that is a structural signal, not the
    # "missing financials" condition, which alone is never JUNK.
    d = _decide(missing=["no_valuation"], junk_sigs=["fraud"], size=500)
    assert d["verdict"] == "JUNK"


def test_engine_version_bumped():
    assert ve.ENGINE_VERSION == "v2-verdict-3"


def test_decisions_are_append_only():
    # write_decision must be a plain INSERT — no UPDATE/UPSERT/ON CONFLICT — so history is
    # append-only and readers take DISTINCT ON (ipo_id) ... ORDER BY decided_at DESC.
    src = inspect.getsource(ve.write_decision)
    assert re.search(r"INSERT\s+INTO\s+decisions", src, re.I)
    assert "ENGINE_VERSION" in src
    assert not re.search(r"UPDATE\s+decisions", src, re.I)
    assert "ON CONFLICT" not in src.upper()


def test_compute_decision_delegates_to_pure_decide():
    # compute_decision reads facts then calls decide(); the pure function is the taxonomy.
    src = inspect.getsource(ve.compute_decision)
    assert "decide(" in src
