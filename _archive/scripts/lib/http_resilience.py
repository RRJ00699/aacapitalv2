#!/usr/bin/env python3
"""_scripts/lib/http_resilience.py — shared scraper resilience (Phase 4).

Two primitives every auto-scraper should use:

  pick_ua()        — rotate through a small pool of current, realistic desktop
                     UAs so a blocked/fingerprinted UA doesn't kill every run.
  backoff_retry()  — exponential backoff with jitter around any fetch callable.
                     Injectable sleep/random for unit tests. Never raises out
                     of the retry loop; returns (ok, result).

Design rules (match lib/notify.py):
  * ZERO dependencies (stdlib only).
  * Pure/injectable — fully unit-testable offline.
  * A scraper that exhausts retries decides its OWN failure behavior
    (log + skip vs notify + exit); this module never calls sys.exit.
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, Optional, Tuple

# Small, current pool. Rotating a handful of real desktop UAs is enough to
# survive a single-UA block without looking like a bot farm.
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def pick_ua(rand: random.Random | None = None) -> str:
    """One UA from the pool. Pass a seeded Random for deterministic tests."""
    return (rand or random).choice(UA_POOL)


def backoff_retry(
    fn: Callable[[], Any],
    attempts: int = 4,
    base: float = 1.0,
    factor: float = 2.0,
    jitter: float = 0.3,
    is_ok: Optional[Callable[[Any], bool]] = None,
    sleep: Callable[[float], None] = time.sleep,
    rand: random.Random | None = None,
    label: str = "",
) -> Tuple[bool, Any]:
    """Run fn() up to `attempts` times with exponential backoff + jitter.

    Success = fn() didn't raise AND (is_ok is None or is_ok(result)).
    Delays: base * factor**i + U(0, jitter)  (i = 0-based failed attempt).
    Returns (True, result) on success, (False, last_result_or_exception) after
    exhausting attempts. NEVER raises.
    """
    r = rand or random
    last: Any = None
    for i in range(max(1, attempts)):
        try:
            result = fn()
            if is_ok is None or is_ok(result):
                return True, result
            last = result
        except Exception as e:  # noqa: BLE001 — resilience wrapper by design
            last = e
        if i < attempts - 1:
            try:
                sleep(base * (factor ** i) + r.uniform(0, jitter))
            except Exception:
                pass
            if label:
                print(f"  · retry {i + 2}/{attempts} {label}")
    return False, last
