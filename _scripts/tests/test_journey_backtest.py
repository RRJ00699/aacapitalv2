#!/usr/bin/env python3
"""Offline tests for the Journey exit simulation — no DB, synthetic candles."""
import importlib.util, os
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "bj", os.path.join(HERE, "..", "..", "research", "backtests", "backtest_journey_exits.py")
)
bj = importlib.util.module_from_spec(spec); spec.loader.exec_module(bj)

def test_trail_exits_at_stop_not_wick():
    # peak 130, trail 12% -> stop 114.4; day3 low 110 breaches -> fill at 114.4
    c = [('d1',100,105,99,104),('d2',104,130,120,125),('d3',125,126,110,112)]
    r = bj.simulate(c, 8, 12)
    assert abs(r["LOCK8_TRAIL12"] - 0.144) < 0.001

def test_floor_not_armed_below_lock():
    # never gains +8% -> floor never arms -> holds to last close (90d proxy)
    c = [('d1',100,102,98,101),('d2',101,103,99,102),('d3',102,104,100,103)]
    r = bj.simulate(c, 8, 12)
    # no stop -> exit at day-90 proxy = last close 103 -> +3%
    assert abs(r["LOCK8_TRAIL12"] - 0.03) < 0.001

def test_naive_horizons():
    c = [(f'd{i}',100,110,95,100+i) for i in range(1,35)]  # rises 1/day
    r = bj.simulate(c, 8, 12)
    assert abs(r["NAIVE_D10"] - 0.10) < 0.001   # day-10 close = 110 -> +10%
    assert abs(r["NAIVE_D30"] - 0.30) < 0.001   # day-30 close = 130 -> +30%

def test_bad_entry_returns_none():
    assert bj.simulate([], 8, 12) is None
    assert bj.simulate([('d1',0,0,0,0)], 8, 12) is None


def test_no_same_bar_arm_and_exit():
    """REGRESSION (2026-07-18): the original sim set peak from TODAY's high then
    checked TODAY's low against it, so a day-1 spike+dip exited at exactly entry
    -> median exactly 0.0% across every parameter sweep. The stop must only use
    peaks from PRIOR bars."""
    c = [('d1', 100, 109, 95, 101), ('d2', 101, 102, 99, 100)]
    r = bj.simulate(c, 8, 12, 3)
    assert r["LOCK8_TRAIL12"] != 0.0, "same-bar arm-and-exit is back"

def test_floor_locks_documented_three_percent():
    """The rule is arm +8 / floor +3 / trail -12. A position that arms then
    collapses must exit at +3%, not breakeven."""
    c = [('d1', 100, 110, 99, 108), ('d2', 108, 109, 80, 85)]
    r = bj.simulate(c, 8, 12, 3)
    assert abs(r["LOCK8_TRAIL12"] - 0.03) < 0.001

def test_gap_down_fills_at_open_not_stop():
    """If the bar OPENS below the stop, the fill is the open (worse), not the
    stop price — no flattering the rule on gaps."""
    c = [('d1', 100, 120, 99, 118), ('d2', 90, 92, 85, 88)]
    r = bj.simulate(c, 8, 12, 3)
    assert r["LOCK8_TRAIL12"] < 0, "gap-down should fill at the (worse) open"
