#!/usr/bin/env python3
"""OPEN-NOW indicator must exist and key off the SUBSCRIPTION state.

Shipped in #192, LOST in a later merge of IpoCard.tsx, restored 2026-07-18.
This is the regression class that makes fixes "come back": two workstreams edit
the same file and a merge resolves to the side without the change. No test
guarded it, so nothing noticed.

Distinct from the "LIVE - trade it" chip, which keys off `onLive` (listing-day
ticks), not the subscription window.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CARD = ROOT / "components" / "ipo" / "IpoCard.tsx"
pytestmark = pytest.mark.unit


def _src():
    return CARD.read_text(encoding="utf-8")


def test_open_now_indicator_exists():
    assert "OPEN NOW" in _src(), "OPEN-NOW indicator missing - regression of #192"


def test_open_now_keys_off_subscription_state():
    assert '"OPEN"' in _src(), 'card no longer references state === "OPEN"'


def test_open_now_is_distinct_from_live_chip():
    s = _src()
    assert "LIVE" in s and "OPEN NOW" in s, \
        "OPEN-NOW must exist independently of the LIVE chip"
