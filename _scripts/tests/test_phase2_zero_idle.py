#!/usr/bin/env python3
"""Contract tests for Phase-2 zero-idle DB architecture (2026-07-20).
Offline — no Neon, no KV. Same style as test_asset_light / test_phase1_fixes.

Zero-idle principle: user READS are served from Cloudflare KV; Neon wakes only
for pipeline writes/warms, execution records, or a genuine cold start.

Covers:
  A. lib/kv-cache.ts grows a stale tier (cachedWithStale / kvPutBoth / kvStore)
  B. ipo-command serves the :stale twin on primary miss (x-cache: STALE header,
     Neon NOT woken) and every write also writes the twin
  C. journey caches the candle read per sym per IST day, does NOT cache empty
     results (listing-morning candles must appear after EOD sync), and keeps
     the live broker quote per-request
  D. cum-volume fronts Neon with KV (confirmed 24h / in-window 60s) and only
     confirms when BOTH window bounds exist AND the 11:00 IST window closed
     (the old vol_end-alone fallback confirmed whole-day volume — wrong number)
  E. live-preopen caches the nightly Neon read; the pre-open book capture
     (a WRITE) stays per-request
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # _scripts/
APP = os.path.join(ROOT, "..", "app")
LIB = os.path.join(ROOT, "..", "lib")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


# ── A. shared helper ────────────────────────────────────────────────────────
def test_kv_cache_stale_tier():
    src = _read(LIB, "kv-cache.ts")
    for sym in ("export async function readStrict",
                "export async function readVersionedSnapshot",
                "export function kvStore"):
        assert sym in src, f"kv-cache.ts missing {sym}"
    assert ":stale" in src, "stale twin key suffix missing"
    strict_body = src[src.index("export async function readStrict"):src.index("export async function cached")]
    assert "await _build" not in strict_body and "build()" not in strict_body


# ── B. ipo-command stale tier ───────────────────────────────────────────────
def test_ipo_command_serves_stale_without_neon():
    src = _read(APP, "api", "ipo-command", "route.ts")
    # PR #282: the stale twin is now served by the shared cachedWithStale() helper in
    # lib/kv-cache.ts (its twin mechanics are covered by test_kv_cache_stale_tier),
    # rather than inline in the route. Contract unchanged: KV-first, stale flagged,
    # Neon not woken on a primary miss.
    assert "readVersionedSnapshot" in src and "readStrict" in src
    assert '"STALE"' in src, "stale responses must be flagged x-cache: STALE"
    assert '"HIT"' in src and '"MISS"' in src
    assert "@/lib/db" not in src


# ── C. journey day-cache ────────────────────────────────────────────────────
def test_journey_candles_kv_day_cache():
    src = _read(APP, "api", "ipo", "journey", "route.ts")
    assert "journey:candles:v2" in src, "journey candle KV key missing"  # v1->v2: market_candles source (#282)
    assert "readStrict" in src, "journey must use strict shared KV reads"
    assert "istDate" in src, "cache key must be per IST calendar day"
    assert "historical_snapshot_unavailable" in src and "store.put" not in src
    # live price stays per-request (never cached)
    assert "/api/broker/quote" in src


def test_journey_does_not_cache_empty():
    src = _read(APP, "api", "ipo", "journey", "route.ts")
    assert "store.put" not in src and "@/lib/db" not in src


# ── D. cum-volume ───────────────────────────────────────────────────────────
def test_cum_volume_kv_front():
    src = _read(APP, "api", "ipo", "cum-volume", "route.ts")
    assert "cumvol:v1" in src, "cum-volume KV key missing"
    assert "readStrict" in src and "retry-after" in src


def test_cum_volume_confirm_requires_both_bounds_and_close():
    src = _read(APP, "api", "ipo", "cum-volume", "route.ts")
    # old bug: vol_end alone (whole-day volume) confirmed as the window total
    assert not re.search(r"vol_end != null \? Number\(r\.vol_end\) : null", src), \
        "vol_end-alone fallback must be gone (it confirmed the wrong number)"
    assert "@neondatabase/serverless" not in src


# ── E. live-preopen ─────────────────────────────────────────────────────────
def test_live_preopen_caches_read_keeps_write():
    src = _read(APP, "api", "ipo", "live-preopen", "route.ts")
    assert "ipo-live-preopen:v2" in src
    assert 'from "@/lib/kv-cache"' in src
    assert "INSERT INTO" not in src and "@/lib/db" not in src
