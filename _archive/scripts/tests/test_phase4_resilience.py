#!/usr/bin/env python3
"""Tests for Phase-4 scraper resilience (2026-07-20).
Offline — backoff_retry / pick_ua are executed FOR REAL with injected
sleep/random; scraper integrations are file-contract checked.

Covers:
  A. lib/http_resilience.backoff_retry: exponential delays, jitter bounds,
     success short-circuit, is_ok gating, never raises, (ok, result) shape
  B. pick_ua: rotates within the pool, deterministic under a seeded Random
  C. scrape_chittorgarh: UA rotation, backoff around the page read, and the
     zero-total tripwire (notify + exit 1)
  D. scrape_investorgain_gmp: 4 exponential attempts, unreachable alert, and
     the parse-zero markup tripwire with the off-season (header-only) guard
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # _scripts/
sys.path.insert(0, ROOT)

from lib.http_resilience import UA_POOL, backoff_retry, pick_ua  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


# ── A. backoff_retry (real execution) ───────────────────────────────────────
def test_backoff_delays_are_exponential_with_jitter():
    delays, calls = [], {"n": 0}
    def failing():
        calls["n"] += 1
        raise RuntimeError("boom")
    ok, last = backoff_retry(failing, attempts=4, base=1.0, factor=2.0, jitter=0.3,
                             sleep=delays.append, rand=random.Random(7))
    assert ok is False and isinstance(last, RuntimeError)
    assert calls["n"] == 4, "must attempt exactly `attempts` times"
    assert len(delays) == 3, "no sleep after the final attempt"
    for i, d in enumerate(delays):
        lo, hi = 1.0 * 2 ** i, 1.0 * 2 ** i + 0.3
        assert lo <= d <= hi, f"delay {i} = {d}, expected [{lo}, {hi}]"


def test_backoff_success_short_circuits():
    delays, calls = [], {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return {"rows": [1, 2]}
    ok, result = backoff_retry(flaky, attempts=5, sleep=delays.append,
                               rand=random.Random(1))
    assert ok is True and result == {"rows": [1, 2]}
    assert calls["n"] == 3 and len(delays) == 2, "must stop at first success"


def test_backoff_is_ok_gating():
    # HTTP 200 with an empty body is still a failure when is_ok says so
    ok, result = backoff_retry(lambda: [], attempts=3, is_ok=lambda r: bool(r),
                               sleep=lambda s: None, rand=random.Random(2))
    assert ok is False and result == []


def test_backoff_never_raises_on_exceptions():
    ok, last = backoff_retry(lambda: (_ for _ in ()).throw(ValueError("odd")),
                             attempts=2, sleep=lambda s: None)
    assert ok is False and isinstance(last, ValueError)
    # deliberately NOT swallowed: BaseException (KeyboardInterrupt/SystemExit)
    # must propagate so Ctrl-C and clean exits still work on the VM
    import pytest as _pytest
    with _pytest.raises(KeyboardInterrupt):
        backoff_retry(lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
                      attempts=2, sleep=lambda s: None)


# ── B. pick_ua ──────────────────────────────────────────────────────────────
def test_pick_ua_pool():
    assert len(UA_POOL) >= 4 and len(set(UA_POOL)) == len(UA_POOL)
    r = random.Random(42)
    picks = {pick_ua(r) for _ in range(50)}
    assert picks.issubset(set(UA_POOL)) and len(picks) > 1, "must actually rotate"
    assert pick_ua(random.Random(9)) == pick_ua(random.Random(9)), "seeded = deterministic"


# ── C. chittorgarh integration ──────────────────────────────────────────────
def test_chittorgarh_resilience_wiring():
    src = _read("scrape_chittorgarh.py")
    assert "from lib.http_resilience import" in src
    assert "pick_ua" in src, "UA rotation missing"
    assert "_backoff_retry(_once" in src, "page read must go through backoff"
    assert "attempts=4" in src
    # zero-total tripwire: alert + non-zero exit (fires the pipeline sink)
    assert "ZERO rows scraped" in src and "sys.exit(1)" in src
    assert "from lib.notify import notify" in src


# ── D. investorgain integration ─────────────────────────────────────────────
def test_investorgain_backoff_and_tripwires():
    src = _read("scrape_investorgain_gmp.py")
    assert "range(4)" in src, "must make 4 attempts"
    assert "2 ** attempt" in src, "backoff must be exponential"
    assert "GMP scrape unreachable" in src, "unreachable alert missing"
    assert "GMP parser matched 0 rows" in src, "markup tripwire missing"
    assert "len(rows) > 3 and not out" in src, \
        "off-season guard: header-only tables must not false-alert"
