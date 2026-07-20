#!/usr/bin/env python3
"""Guards for the listing-day minute backfill (real executed tape).

Owner 2026-07-19: GMP and subscription are INDICATIONS and both manipulable
(grey market is unregulated; subscription can be inflated by leveraged HNI
applications that never become buyers). Kite historical_data() at minute
interval is EXECUTED trades — it cannot be talked up.

First run: 22/25 filled, 0 failures. Laser opened at 250 with 10.2M shares in
5 minutes; Aastha at 130 with 194k — two orders of magnitude apart, which is the
conviction signal the proxies only gesture at.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_scripts" / "backfill_listing_minutes.py"
pytestmark = pytest.mark.unit


def _src():
    return SCRIPT.read_text(encoding="utf-8")


def test_script_is_in_the_repo():
    """It was written and run as a loose local file — it belongs in _scripts so
    the VM and cron can use it."""
    assert SCRIPT.exists()


def test_requires_explicit_apply():
    """Never write by accident; --dry-run must be a real mode."""
    s = _src()
    assert '"--apply"' in s and '"--dry-run"' in s
    assert "pass --apply or --dry-run" in s


def test_owns_its_own_table():
    """CHANGED 2026-07-20: the tape used to ALTER columns onto ipo_consolidated,
    which build_ipo_consolidated_v2.py rebuilds every run — 456 rows were wiped
    three times in two days. It now owns ipo_listing_tape, the same pattern that
    kept ipo_bid_details intact through every rebuild."""
    s = _src()
    assert "CREATE TABLE IF NOT EXISTS ipo_listing_tape" in s
    assert "UPDATE ipo_consolidated SET" not in s, "still writing to the rebuilt table"
    for col in ("first_print_price", "vol_first_5m", "vol_first_15m",
                "vwap_first_15m", "first_trade_time"):
        assert col in s, f"{col} missing from the tape table"


def test_is_idempotent():
    """Re-running must not refetch what is already filled — the API is rate
    limited and this walks 512 IPOs."""
    assert "t.symbol IS NULL" in _src(), "reruns would refetch everything"


def test_respects_rate_limit():
    assert "time.sleep(" in _src(), "no pacing — Kite historical API will throttle"


def test_missing_symbol_is_skipped_not_fatal():
    """REITs and delisted names are not in the NSE EQ map (HEXAGON, BAGMANE,
    AMIRCHAND on the first run). They must be counted and skipped."""
    s = _src()
    assert "not in NSE instrument map" in s and "continue" in s


def test_anchors_on_first_traded_bar():
    """REGRESSION 2026-07-19: IPO listings start at 10:00 IST after the special
    pre-open, but Kite returns the day from 09:15 — bars[0:5] are EMPTY
    placeholders. The old code took bars[0], producing a phantom open price and
    vol5m=0 (IGCL, SAMBHV, KALPATARU, SCODATUBES, PROSTARM, AEGISVOPAK)."""
    s = _src()
    assert "bars.index(traded[0])" in s, "windows are not anchored on the first traded bar"
    assert "first = live[0]" in s, "first print still taken from the raw bar list"


def test_records_first_trade_time():
    """When trading actually began is itself the listing-time signal (10:00 vs
    09:15 vs later) — capture it rather than inferring it."""
    s = _src()
    assert "first_trade_time" in s, "listing-time signal not captured"


def test_no_traded_bars_is_skipped():
    assert "no traded bars" in _src()
