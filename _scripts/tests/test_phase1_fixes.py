#!/usr/bin/env python3
"""Contract tests for the Phase-1 audit fixes (2026-07-20).
Offline — no Neon, no KV. Pytest-collectable, same style as test_asset_light.

Covers:
  #1 Live screen polls /api/ipo/tick-feed?live=1 (KV-only) during IST hours
  #2 Nightly pipelines pass --apply to fill_listing_open + reconcile_listing_dates
  #3 Journey route floors price_candles at ipo_intelligence.listing_date
  #4 cum-volume defaults the tick window to IST *today* (was `= NULL` -> 0 rows)
  #5 Search lands listed IPOs on the Post table's exact row (postrow anchor)
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # _scripts/
APP = os.path.join(ROOT, "..", "app")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


# ── #1 live tick overlay ────────────────────────────────────────────────────
def test_live_screen_polls_kv_tick_feed():
    page = _read(APP, "dashboard", "ipo2", "page.tsx")
    assert "tick-feed?symbol=" in page and "live=1" in page, \
        "ipo2 must poll the KV-only tick-feed fast path"
    assert "liveOverlay" in page, "overlay state missing"
    # overlay must win over the cached snapshot in the live panel
    assert re.search(r"liveOverlay\[sym\]\s*\?\?\s*ticks\[", page), \
        "KV overlay must take precedence over cached d.live ticks"
    # IST market-hours gate expressed in UTC minutes (03:30->210, 10:00->600),
    # so the check is correct from any viewer timezone (user is CST).
    assert "210" in page and "600" in page, "IST market-hours gate missing"


# ── #2 pipeline --apply ─────────────────────────────────────────────────────
def _step_args(src, script):
    """Return the arg-list strings for every step() invoking `script`."""
    return re.findall(r"\[([^\]]*%s[^\]]*)\]" % re.escape(script), src)


def test_lean_pipeline_writers_apply():
    src = _read(ROOT, "run_ipo_pipeline_lean.py")
    for script in ("fill_listing_open_from_candles.py", "reconcile_listing_dates.py"):
        calls = _step_args(src, script)
        assert calls, f"{script} step missing from lean pipeline"
        for c in calls:
            assert "--apply" in c, f"{script} runs in DRY-RUN (no --apply): {c}"


def test_full_pipeline_writers_apply():
    src = _read(ROOT, "../compatibility/scripts/run_ipo_pipeline.py")
    for script in ("fill_listing_open_from_candles.py", "reconcile_listing_dates.py"):
        calls = _step_args(src, script)
        assert calls, f"{script} step missing from full pipeline"
        for c in calls:
            assert "--apply" in c, f"{script} runs in DRY-RUN (no --apply): {c}"


# ── #3 journey listing-date floor ───────────────────────────────────────────
def test_journey_floors_candles_at_listing_date():
    # #282: journey candles now come from canonical market_candles via lib/v2/journey.ts
    # (fetchJourneyCandles), floored at ipo.listing_date. Was V1 price_candles +
    # ipo_intelligence. Same flooring contract.
    src = _read(ROOT, "..", "lib", "v2", "journey.ts")
    assert "FROM ipo" in src and "market_candles" in src, "journey must resolve listing_date from ipo"
    assert "c.d >= t.listing_date" in src, \
        "journey candles must be floored at listing_date (entry-price bug)"
    # graceful when no IPO row exists for the symbol
    assert "t.listing_date IS NULL OR" in src


# ── #4 cum-volume IST-today default ─────────────────────────────────────────
def test_cum_volume_defaults_to_ist_today():
    route = _read(APP, "api", "ipo", "cum-volume", "route.ts")
    assert "COALESCE" in route and "Asia/Kolkata" in route
    # the broken pattern: bare `= ${date ?? null}::date` with no COALESCE
    assert not re.search(r"=\s*\$\{date \?\? null\}::date\s*\n", route), \
        "date filter must not compare against bare NULL"


# ── #5 search -> post-listing exact row ─────────────────────────────────────
def test_search_lands_on_post_row():
    page = _read(APP, "dashboard", "ipo2", "page.tsx")
    assert "postrow-" in page, "post table rows need postrow-{sym} anchors"
    assert re.search(r'setView\("post"\)', page), \
        "search handler must switch to the post view for listed IPOs"
