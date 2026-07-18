#!/usr/bin/env python3
"""The OPEN-NOW indicator must exist and key off the SUBSCRIPTION state.

Shipped in #192, then LOST in a later merge of IpoCard.tsx — `isOpenNow` had
zero references on main while the owner still expected the green treatment.
This is the regression class that makes fixes "come back": two workstreams edit
the same file and a merge silently resolves to the side without the change.

It is distinct from the "LIVE — trade it" chip, which keys off `onLive`
(listing-day ticks), not the subscription window.
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CARD = ROOT / "components" / "ipo" / "IpoCard.tsx"
pytestmark = pytest.mark.unit


def _src():
    return CARD.read_text(encoding="utf-8")


def test_open_now_indicator_exists():
    assert "OPEN NOW" in _src(), "OPEN-NOW indicator missing — regression of #192"


def test_open_now_keys_off_subscription_state():
    s = _src()
    assert '"OPEN"' in s, 'card no longer references state === "OPEN"'


def test_open_now_is_not_the_live_chip():
    """Guard the distinction: onLive is listing-day ticks, not the open window."""
    s = _src()
    assert "LIVE — trade it" in s, "LIVE chip missing"
    assert "OPEN NOW" in s, "OPEN-NOW must exist independently of the LIVE chip"
