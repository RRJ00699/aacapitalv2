#!/usr/bin/env python3
"""The House Stack must stay wired across all three screens.

MEASURED 2026-07-19 (n=55, D30 from the listing open):
    30+ anchors AND >=Rs.200cr AND OFS<30%
      -> 72.7% win, +17.2% median, 23.6% chance of a -20% drawdown
    baseline: 62.2% win, +12.7% median, 32.4% drawdown risk

It out-performed EVERY candidate signal tested that day — RHP governance flags,
executed early volume (first-15m turnover), retail price-bid ratio, and mutual
fund share of QIB. Layering MF>10% on top made it WORSE at D1/D2/D3/D5 and D30
(-7.4 win% at D1), so the stack ships alone.

This is the regression class that keeps biting: a fix lands, a later merge of the
same file silently drops it, and nobody notices because no test guards it.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
# PR #282 moved the route logic into tested lib/v2 helpers; the House Stack lives in
# lib/v2/ipo-command.ts (enrichCards) and lib/v2/live-preopen.ts (scoreStatic). The
# contract is unchanged — re-pointed to where the code now is (behaviour is unit-tested
# in lib/v2/*.test.ts).
CMD_ROUTE = ROOT / "lib" / "v2" / "ipo-command.ts"
CARD = ROOT / "components" / "ipo" / "IpoCard.tsx"
LIVE = ROOT / "lib" / "v2" / "live-preopen.ts"
pytestmark = pytest.mark.unit


def test_command_route_computes_all_three_conditions():
    s = CMD_ROUTE.read_text(encoding="utf-8")
    assert "stackAnchors" in s and "anc >= 30" in s, "30-anchor leg missing"
    assert "stackFloor" in s and "size >= 200" in s, "Rs.200cr floor leg missing"
    assert "stackFresh" in s and "ofsPct < 30" in s, "OFS<30% leg missing"
    assert "houseStack" in s, "the three legs are not combined"


def test_command_route_exposes_it_to_the_ui():
    s = CMD_ROUTE.read_text(encoding="utf-8")
    for f in ("house_stack:", "house_stack_parts", "house_stack_stat"):
        assert f in s, f"{f} not in the payload — the UI cannot render it"


def test_card_shows_the_chip():
    s = CARD.read_text(encoding="utf-8")
    assert "HOUSE STACK" in s, "no chip on the Command card"
    assert "c.house_stack === true" in s, "chip not gated on the computed flag"


def test_journey_explains_the_hold():
    """Journey is where the stack matters most: it is the evidence for sitting
    through a dip (23.6% drawdown risk vs 32.4%)."""
    s = CARD.read_text(encoding="utf-8")
    assert "drawdown risk 23.6%" in s, "Journey does not cite the drawdown edge"


def test_why_buy_list_includes_it():
    s = CARD.read_text(encoding="utf-8")
    assert "HOUSE STACK: 30+ anchors" in s, "not in the why-to-buy reasons"


def test_live_engine_has_it_as_a_static_rule():
    """All three inputs are known before the open, so it must resolve with the
    static set at 09:30 — not wait for live ticks."""
    s = LIVE.read_text(encoding="utf-8")
    assert "The House Stack" in s, "House Stack missing from the live rules"
    assert "anchors >= 30" in s and "size >= 200" in s and "ofs < 30" in s, \
        "live rule does not check all three legs"


def test_stack_thresholds_are_not_drifted():
    """Guard the exact numbers the backtest measured. Changing a threshold
    invalidates the 72.7% claim printed next to it."""
    s = CMD_ROUTE.read_text(encoding="utf-8")
    assert "anc >= 30" in s and "size >= 200" in s and "ofsPct < 30" in s
    assert "72.7%" in s, "the measured win-rate is no longer cited with the rule"
