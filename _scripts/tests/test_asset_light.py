#!/usr/bin/env python3
"""Tests for asset-light Step 3 (ticker KV path) + command staleness filter.
Offline — no Neon, no KV, no NSE. Pytest-collectable."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "..", "app")


def _checks():
    r = {}
    ticker = open(os.path.join(ROOT, "ipo", "kite_ticker_ipo.py")).read()
    r["ticker _kv_put_live"] = "_kv_put_live" in ticker
    r["ticker live:tick key"] = "live:tick:" in ticker
    r["ticker 60s neon flush"] = "NEON_FLUSH_S = 60" in ticker
    r["ticker last_kv+last_db"] = "last_kv" in ticker and "last_db" in ticker
    r["ticker admin key auth"] = "ADMIN_JOB_KEY" in ticker and "X-AAC-Key" in ticker
    r["ticker kv before neon"] = ticker.index("last_kv") < ticker.index("NEON_FLUSH_S")

    # #282: the command WHERE moved into lib/v2/ipo-command.ts (fetchCards), on canonical
    # columns (i.listing_date / iss.close_date / iss.open_date). Same 30-day window.
    route = open(os.path.join(ROOT, "..", "lib", "v2", "ipo-command.ts")).read()
    r["cmd leak removed"] = "listing_date IS NULL AND" not in route
    r["cmd window filter"] = "AT TIME ZONE 'Asia/Kolkata')::date - 30" in route
    r["cmd 30day lockin"] = "::date - 30" in route
    r["cmd keeps listing cond"] = "i.listing_date >=" in route
    r["cmd keeps close cond"] = "iss.close_date >=" in route
    r["cmd keeps open cond"] = "iss.open_date" in route

    tf = open(os.path.join(APP, "api", "ipo", "tick-feed", "route.ts")).read()
    r["tick-feed kv read"] = "live:tick:" in tf
    r["tick-feed live=1 path"] = 'searchParams.get("live")' in tf
    r["tick-feed no DB fallback"] = "historical_snapshot_unavailable" in tf and "@/lib/db" not in tf

    kp = open(os.path.join(APP, "api", "admin", "kv-put", "route.ts")).read()
    r["kv-put admin key"] = "ADMIN_JOB_KEY" in kp
    r["kv-put 401"] = "401" in kp
    return r


def test_asset_light_all():
    r = _checks()
    failed = [k for k, v in r.items() if not v]
    assert not failed, f"failed: {failed}"


if __name__ == "__main__":
    r = _checks()
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'} — {k}")
    n = sum(r.values())
    print(f"\n{n}/{len(r)} PASS")
    raise SystemExit(0 if n == len(r) else 1)
