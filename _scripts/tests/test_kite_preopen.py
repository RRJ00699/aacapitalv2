#!/usr/bin/env python3
"""Kite pre-open parser tests — offline, no Kite contact.

Context 2026-07-19: NSE endpoints are BLOCKED from the VM (Akamai rejects the
Hetzner IP in ~42ms). Kite is not blocked, and kite.quote() exposes the same
pre-open book via depth.buy/depth.sell. This is the VM-viable capture path.
"""
import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "kpc", os.path.join(HERE, "..", "kite_preopen_capture.py"))
kpc = importlib.util.module_from_spec(spec); spec.loader.exec_module(kpc)

QUOTE = {
    "last_price": 142.5,
    "buy_quantity": 981030,
    "sell_quantity": 822634,
    "volume": 385000,
    "depth": {
        "buy":  [{"price": 142.5, "quantity": 12000}, {"price": 141.0, "quantity": 5000}],
        "sell": [{"price": 144.0, "quantity": 7000},  {"price": 142.5, "quantity": 9000}],
    },
}


def test_iep_and_totals():
    r = kpc.parse_quote("ALPINE", QUOTE)
    assert r["iep"] == 142.5
    assert r["buy_qty"] == 981030 and r["sell_qty"] == 822634


def test_best_bid_is_highest_buy_level():
    r = kpc.parse_quote("ALPINE", QUOTE)
    assert r["best_bid"] == 142.5 and r["best_bid_qty"] == 12000


def test_best_ask_is_lowest_sell_level():
    r = kpc.parse_quote("ALPINE", QUOTE)
    assert r["best_ask"] == 142.5 and r["best_ask_qty"] == 9000


def test_lean_pct():
    r = kpc.parse_quote("ALPINE", QUOTE)
    assert r["lean_pct"] == 19.3


def test_hash_stable_then_changes():
    a = kpc.parse_quote("ALPINE", QUOTE)["state_hash"]
    b = kpc.parse_quote("ALPINE", QUOTE)["state_hash"]
    assert a == b
    q2 = dict(QUOTE, buy_quantity=999999)
    assert kpc.parse_quote("ALPINE", q2)["state_hash"] != a


def test_empty_depth_is_safe():
    r = kpc.parse_quote("X", {"last_price": None, "depth": {}})
    assert r["best_bid"] is None and r["best_ask"] is None and r["lean_pct"] is None


@pytest.mark.parametrize("h,m,inside", [(8,56,False),(8,57,True),(10,15,True),(10,21,False)])
def test_window_covers_1013_to_1016(h, m, inside):
    """Owner needs 10:13-10:16 specifically; window must cover it."""
    import datetime as dt
    t = dt.datetime(2026, 7, 21, h, m)
    assert kpc.in_window(t) is inside
