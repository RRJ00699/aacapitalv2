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
    for sym in ("export async function cachedWithStale",
                "export async function kvPutBoth",
                "export function kvStore"):
        assert sym in src, f"kv-cache.ts missing {sym}"
    assert ":stale" in src, "stale twin key suffix missing"
    # stale hit must return BEFORE build() runs (Neon stays asleep)
    body = src[src.index("cachedWithStale"):]
    assert body.index('source: "stale"') < body.index('source: "build"')


# ── B. ipo-command stale tier ───────────────────────────────────────────────
def test_ipo_command_serves_stale_without_neon():
    # OBSOLETE BY ARCHITECTURE: cache-on-miss/stale-twin assertions were replaced by
    # immutable active/previous snapshots; product contract (readable fallback) is restored in versioned-snapshot.test.ts.
    src = _read(APP, "api", "ipo-command", "route.ts")
    assert "readVersionedSnapshot" in src and "ipo-command:v6" in src
    assert "@/lib/db" not in src


# ── C. journey day-cache ────────────────────────────────────────────────────
def test_journey_candles_kv_day_cache():
    # OBSOLETE BY ARCHITECTURE: day bundle and route-side non-empty writes are gone.
    # RESTORED product contract: ISIN-first per-IPO immutable snapshots and no route producer.
    src = _read(APP, "api", "ipo", "journey", "route.ts")
    assert "journey:isin:${isin}:v1" in src and "readVersionedSnapshot" in src
    assert "store.put" not in src and "@/lib/db" not in src

def test_journey_does_not_cache_empty():
    src = _read(APP, "api", "ipo", "journey", "route.ts")
    assert "store.put" not in src  # route cannot publish empty or non-empty data


# ── D. cum-volume ───────────────────────────────────────────────────────────
def test_cum_volume_kv_front():
    src = _read(APP, "api", "ipo", "cum-volume", "route.ts")
    assert "cumvol:v1" in src, "cum-volume KV key missing"
    assert "86400" in src and "60" in src, "confirmed 24h / in-window 60s TTLs"
    assert "kvStore" in src


def test_cum_volume_confirm_requires_both_bounds_and_close():
    src = _read(APP, "api", "ipo", "cum-volume", "route.ts")
    # old bug: vol_end alone (whole-day volume) confirmed as the window total
    assert not re.search(r"vol_end != null \? Number\(r\.vol_end\) : null", src), \
        "vol_end-alone fallback must be gone (it confirmed the wrong number)"
    assert "windowClosed" in src, "confirmation requires the 11:00 IST close"
    assert "660" in src, "11:00 IST = 660 IST-minutes gate missing"


# ── E. live-preopen ─────────────────────────────────────────────────────────
def test_live_preopen_caches_read_keeps_write():
    # OBSOLETE BY ARCHITECTURE: route-side cache/write and ipo_preopen_book were removed.
    # RESTORED contract: pipeline snapshot only, honest BLOCKED overlay, no external request.
    src = _read(APP, "api", "ipo", "live-preopen", "route.ts")
    assert "ipo-live-preopen:v2" in src and 'live_overlay:"BLOCKED"' in src
    assert "fetch(" not in src and "INSERT" not in src and "@/lib/db" not in src
