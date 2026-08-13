import datetime as dt

from pipeline.topout_online import bearish_candle, detect_top


def bar(high, low, close, volume=10, opening=None):
    return {"ts": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
            "o": close if opening is None else opening, "h": high, "l": low,
            "c": close, "v": volume}


def test_no_signal_and_researched_lower_high_watch_are_deterministic():
    assert detect_top([])["state"] == "IDLE"
    bars = [bar(10, 8, 9), bar(9, 7, 8), bar(8, 6, 7), bar(7, 5, 6), bar(6, 4, 5)]
    result = detect_top(bars)
    assert result["state"] == "WATCH"
    assert result["watch_kind"] == "A"


def test_newest_fourth_lower_high_bar_enters_watch():
    result = detect_top([bar(high, high - 2, high - 1) for high in (10, 9, 8, 7)])
    assert result["state"] == "WATCH"


def test_sourced_bearish_candle_definitions_are_preserved():
    shooting_star = [(None, 9.0, 12.0, 8.9, 9.2, 10)]
    assert bearish_candle(shooting_star, 0)
    engulfing = [(None, 9.0, 10.2, 8.8, 10.0, 10),
                 (None, 10.1, 10.2, 8.7, 8.9, 10)]
    assert bearish_candle(engulfing, 1)


def test_tier_one_waits_for_next_bar_rejection_confirmation():
    bars = [bar(100 + i, 90, 99 + i, 10) for i in range(21)]
    bars.append(bar(130, 100, 129, 1000))
    assert detect_top(bars)["state"] != "TOP"
    bars.append(bar(128, 100, 125, 10))  # >1% rejection from the climax high
    result = detect_top(bars)
    assert result["state"] == "TOP"
    assert result["fire_path"] == "TIER1_REJECTION"


def test_production_result_contains_no_bottom_entry_or_hindsight_scoring():
    result = detect_top([bar(10 + i, 8, 9 + i / 2, 10) for i in range(25)])
    forbidden = {"b_alert", "b_px", "real_bot", "b_gap", "entry", "real_peak",
                 "gap_to_peak", "dd_avoided", "false_fire"}
    assert forbidden.isdisjoint(result)


def test_snapshot_route_and_journey_ui_keep_top_discovery_kv_only():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    builder = (root / "pipeline/build/build_snapshots.ts").read_text()
    route = (root / "app/api/ipo/journey/route.ts").read_text()
    ui = (root / "app/dashboard/journey/page.tsx").read_text()
    assert "level_observation:latestLevel" in builder
    assert "journey:isin:" in builder and "obs_type='level'" in builder
    assert "level_observation" in route
    assert "@neondatabase" not in route and "sql`" not in route
    assert "discovery-level" in ui and "evaluated_through_bar" in ui
    assert "Entry interpretation" not in ui and "Bottom interpretation" not in ui
