#!/usr/bin/env python3
"""
backfill_market_regimes.py — fill YEARS of NIFTY + India VIX history into market_regimes.

market_regime.py runs forward-only (one day at a time), which is why only ~26 days exist
and today's india_vix surfacing covers almost no IPOs. This backfills the gap by reusing
that engine's OWN functions (no duplicated logic) over a wide date range, in Kite-sized
chunks. GOLDEN RULE: inserts only dates that don't already exist — never overwrites the
days you already captured.

After this runs, re-run build_ipo_consolidated_v2.py and the india_vix surfacing will
cover real IPO listing dates (the VIX fix becomes meaningful), and check_data_contract.py
will show india_vix climbing.

Usage:
    setx ... (DATABASE_URL + your Kite token, same as market_regime.py needs)
    python _scripts\\backfill_market_regimes.py --from 2018-01-01            # dry-run
    python _scripts\\backfill_market_regimes.py --from 2018-01-01 --apply

Note: PCR is NOT backfillable (no historical option-chain source) — that stays a
forward-only daily capture, tracked separately in the contract.
"""
import os, sys, argparse
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # so the 'engines' package resolves when run from _scripts/

try:
    import psycopg2
    from kite_connect import get_kite          # canonical: reads token from Neon platform_config
    from engines.market_regime import (
        fetch_historical, compute_ema, classify_regime, upsert_regime,
        NIFTY_TOKEN, INDIA_VIX_TOKEN,
    )
except Exception as e:
    sys.exit(f"Import failed ({e}). Run from repo root or _scripts/ (needs kite_connect.py + engines/).")

def daterange_chunks(d0, d1, max_days=1800):
    cur = d0
    while cur <= d1:
        end = min(cur + timedelta(days=max_days), d1)
        yield cur, end
        cur = end + timedelta(days=1)

def fetch_series(kite, token, d0, d1):
    out = []
    for a, b in daterange_chunks(d0, d1):
        out += fetch_historical(kite, token, a, b)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2018-01-01")
    ap.add_argument("--to", dest="to", default=date.today().isoformat())
    ap.add_argument("--apply", action="store_true", help="write to DB (default dry-run)")
    args = ap.parse_args()
    d0 = datetime.strptime(args.frm, "%Y-%m-%d").date()
    d1 = datetime.strptime(args.to, "%Y-%m-%d").date()

    DB = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not DB:
        sys.exit("Set DATABASE_URL (or NEON_DATABASE_URL).")
    kite = get_kite()                 # token from platform_config — same source as your live pipeline
    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    print(f"Fetching NIFTY + India VIX  {d0} → {d1} (Kite, chunked)…")
    nifty = fetch_series(kite, NIFTY_TOKEN, d0, d1)
    vix   = fetch_series(kite, INDIA_VIX_TOKEN, d0, d1)
    if not nifty:
        sys.exit("No NIFTY candles returned — check Kite token / historical-data subscription.")
    # dedupe + sort by date
    nmap, vmap = {}, {}
    for c in nifty: nmap[c["date"].date()] = float(c["close"])
    for c in vix:   vmap[c["date"].date()] = float(c["close"])
    days = sorted(nmap)
    closes = [nmap[d] for d in days]
    ema = compute_ema(closes, 200)
    print(f"  NIFTY days: {len(days)} | VIX days: {len(vmap)} | range {days[0]} → {days[-1]}")

    # GOLDEN RULE: find dates already present; we will NOT touch those
    cur.execute("SELECT evaluation_date FROM market_regimes")
    existing = {r[0] for r in cur.fetchall()}
    print(f"  existing market_regimes rows: {len(existing)} (these will be left untouched)")

    to_write, skipped_existing, skipped_noema = 0, 0, 0
    plan = []
    for i, d in enumerate(days):
        if d in existing:
            skipped_existing += 1; continue
        ema200 = ema[i]
        if ema200 is None:           # first ~200 days have no EMA200 (pre-2018 warmup; no IPOs there)
            skipped_noema += 1; continue
        v = vmap.get(d)
        plan.append((d, nmap[d], ema200, v))
        to_write += 1

    print(f"\n  to insert: {to_write} new days | skip existing: {skipped_existing} | skip (no EMA200 warmup): {skipped_noema}")
    if plan[:3]:
        print("  sample:", [(str(d), f"nifty={n:,.0f}", f"vix={v}") for d, n, e, v in plan[:3]])

    if not args.apply:
        print("\ndry-run — nothing written. Re-run with --apply to backfill.")
        return

    n = 0
    for d, nclose, ema200, v in plan:
        breadth = 0.0  # historical breadth unavailable; VIX/NIFTY/EMA are what we need here
        regime = classify_regime(nclose, ema200, breadth, v)
        upsert_regime(conn, d, nclose, ema200, breadth, v, regime)  # only NEW dates reach here
        n += 1
    print(f"\n✓ backfilled {n} historical days into market_regimes (existing days untouched).")
    print("  next: python _scripts\\build_ipo_consolidated_v2.py  (india_vix now surfaces for many IPOs)")
    print("        python _scripts\\check_data_contract.py        (watch india_vix climb)")

if __name__ == "__main__":
    main()
