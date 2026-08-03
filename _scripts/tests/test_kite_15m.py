#!/usr/bin/env python3
"""market_candles_15m — paginated 15-minute fetch + idempotent upsert.

The pagination is EXECUTED offline against a fake historical_data (no Kite); the
DDL + upsert (PK ipo_id,ts) is exercised on embedded postgres via the pg_uri
fixture. Guards the 200-day/request cap and the re-run-safe backfill."""
import datetime as dt
import importlib.util
import math
import os
import sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
# pipeline modules import each other by bare name (e.g. fill_v2 -> fill_ipo), so the
# pipeline dir must be importable for those transitive imports to resolve.
sys.path.insert(0, os.path.join(HERE, "..", "..", "pipeline"))
def _load(name, rel):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, "..", "..", "pipeline", rel))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
kf = _load("kite_fetch", "kite_fetch.py")


class FakeKite:
    """Records each historical_data window; returns one bar per DAY in the window,
    so bar totals prove coverage is contiguous with no gaps or overlaps."""
    def __init__(self): self.calls = []
    def historical_data(self, token, from_date, to_date, interval):
        self.calls.append((from_date, to_date, interval))
        bars, d = [], from_date
        while d <= to_date:
            bars.append({"date": dt.datetime(d.year, d.month, d.day, 9, 15),
                         "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100})
            d += dt.timedelta(days=1)
        return bars


def test_15minute_interval_and_single_window():
    """A short (<200d) span — the 07-30 priority case — is ONE 15minute request."""
    k = FakeKite()
    start, end = dt.date(2026, 7, 30), dt.date(2026, 8, 3)      # 5 days
    bars = kf.fetch_candles_15m(k, 195661057, start, end)
    assert len(k.calls) == 1
    assert k.calls[0][2] == "15minute"
    assert k.calls[0][0] == start and k.calls[0][1] == end
    assert len(bars) == 5
    assert bars[0]["ts"] == dt.datetime(2026, 7, 30, 9, 15)
    assert set(bars[0]) == {"ts", "o", "h", "l", "c", "v"}


def test_pagination_splits_at_200_days():
    k = FakeKite()
    start, end = dt.date(2025, 1, 1), dt.date(2025, 12, 31)      # 365 days -> 2 windows
    bars = kf.fetch_candles_15m(k, 1, start, end)
    assert len(k.calls) == 2
    (f0, t0, _), (f1, t1, _) = k.calls
    assert f0 == start and (t0 - f0).days == 199                 # first window: 200 days inclusive
    assert f1 == t0 + dt.timedelta(days=1) and t1 == end         # contiguous, no overlap
    assert (t1 - f1).days < 200
    assert len(bars) == 365                                      # every day covered exactly once


def test_backfill_2016_window_count():
    k = FakeKite()
    start, end = dt.date(2016, 2, 8), dt.date(2026, 8, 3)        # ~10.5y backfill
    bars = kf.fetch_candles_15m(k, 1, start, end)
    span = (end - start).days + 1
    assert len(k.calls) == math.ceil(span / 200)
    assert k.calls[0][0] == start and k.calls[-1][1] == end      # full coverage, ends exactly on `end`
    assert len(bars) == span


def test_daily_candles_paginate_at_2000_days():
    """A pre-2020 listing->today range exceeds Kite's 2000-day day-interval cap, so the
    DAILY fetch must paginate too — an unpaginated call errored and (via the old
    early-return) skipped the 15-min fetch for exactly the old IPOs that need it."""
    k = FakeKite()
    start, end = dt.date(2016, 2, 8), dt.date(2026, 8, 3)         # ~3,830 days -> 2 windows
    bars = kf.fetch_candles(k, 1, start, end)
    span = (end - start).days + 1
    assert len(k.calls) == math.ceil(span / 2000)
    assert all(call[2] == "day" for call in k.calls)             # day interval, paginated
    assert k.calls[0][0] == start and k.calls[-1][1] == end
    assert len(bars) == span
    assert set(bars[0]) == {"d", "o", "h", "l", "c", "v"}


@pytest.mark.integration
def test_upsert_15m_idempotent(pg_uri):
    import psycopg2
    fv = _load("fill_v2", "fill_v2.py")
    conn = psycopg2.connect(pg_uri)
    fv.ensure_15m_table(conn)
    bars = [{"ts": dt.datetime(2026, 7, 30, 9, 15), "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100},
            {"ts": dt.datetime(2026, 7, 30, 9, 30), "o": 1.5, "h": 2.5, "l": 1, "c": 2, "v": 200}]
    assert fv.upsert_candles_15m(conn, 5, bars) == 2
    fv.upsert_candles_15m(conn, 5, bars)                          # re-run: PK (ipo_id,ts) -> no dupes
    cur = conn.cursor(); cur.execute("SELECT count(*) FROM market_candles_15m WHERE ipo_id=5")
    assert cur.fetchone()[0] == 2
    conn.close()
