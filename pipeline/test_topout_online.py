import datetime as dt

from pipeline.topout_online import detect_level


def bar(high, low, close, volume=10):
    return {"ts": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), "o": close,
            "h": high, "l": low, "c": close, "v": volume}


def test_no_signal_and_watch_states_are_deterministic():
    assert detect_level([])["state"] == "no_signal"
    assert detect_level([bar(10, 8, 9), bar(9, 7, 8), bar(8, 6, 7)])["state"] == "watch_top"
    assert detect_level([bar(8, 6, 7), bar(9, 7, 8), bar(10, 8, 9)])["state"] == "watch_bottom"


def test_top_uses_only_current_and_prior_bars():
    bars = [bar(10 + i / 10, 8, 9, 10) for i in range(9)]
    bars.append(bar(15, 8, 14, 100))
    result = detect_level(bars)
    assert result["state"] == "top" and result["signal"] == "exit"
    assert detect_level(bars)["trigger_evidence"] == result["trigger_evidence"]


def test_bottom_signal_and_invalidation_to_no_signal():
    bars = [bar(12, 10 - i / 10, 11, 10) for i in range(9)]
    bars.append(bar(12, 5, 6, 100))
    assert detect_level(bars)["signal"] == "entry"
    bars.append(bar(13, 4, 4.01, 10))
    assert detect_level(bars)["signal"] is None
