#!/usr/bin/env python3
"""Bounded incremental 15-minute supply using the canonical Kite helper/writer."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time

import psycopg2

from kite_fetch import fetch_candles_15m, get_kite

TRANSIENT_MARKERS = ("timeout", "timed out", "429", "too many requests", "500", "502", "503", "504")


def is_transient(exc: Exception) -> bool:
    return any(marker in f"{type(exc).__name__}: {exc}".lower() for marker in TRANSIENT_MARKERS)


def select_targets(conn, limit: int):
    """Canonical mainboard/size scope, bounded by IST calendar dates."""
    cur = conn.cursor()
    cur.execute("""SELECT i.id,i.isin,i.symbol,i.name_display,i.listing_date,i.kite_token
      FROM ipo i
      WHERE i.is_mainboard=TRUE AND i.listing_date BETWEEN
        ((now() AT TIME ZONE 'Asia/Kolkata')::date - 100)
        AND (now() AT TIME ZONE 'Asia/Kolkata')::date
      AND i.kite_token IS NOT NULL AND NULLIF(trim(i.symbol),'') IS NOT NULL
      AND COALESCE((SELECT ii.issue_size_cr FROM ipo_issue ii WHERE ii.ipo_id=i.id LIMIT 1),999999)>=150
      ORDER BY i.listing_date DESC,i.id LIMIT %s""", (limit,))
    return cur.fetchall()


def insert_bars(conn, ipo_id: int, bars: list[dict]) -> int:
    """Use the established (ipo_id,ts) identity; duplicates are intentionally no-ops."""
    cur = conn.cursor()
    inserted = 0
    for bar in bars:
        cur.execute("""INSERT INTO market_candles_15m(ipo_id,ts,o,h,l,c,v)
          VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (ipo_id,ts) DO NOTHING""",
                    (ipo_id, bar["ts"], bar.get("o"), bar.get("h"), bar.get("l"),
                     bar.get("c"), bar.get("v")))
        inserted += cur.rowcount
    conn.commit()
    return inserted


def run(conn, *, limit: int, dry_run: bool, throttle_seconds: float = 0.34, sleep=time.sleep):
    targets = select_targets(conn, limit)
    summary = {"selected": len(targets), "attempted": 0, "bars_received": 0,
               "bars_inserted": 0, "duplicates": 0, "no_data": 0,
               "transient_failed": 0, "ipos": []}
    if dry_run:
        summary["ipos"] = [{"ipo_id": row[0], "name": row[3], "status": "dry"} for row in targets]
        return summary
    kite = get_kite()
    cur = conn.cursor()
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    for ipo_id, _isin, _symbol, name, listing_date, token in targets:
        summary["attempted"] += 1
        cur.execute("SELECT max(ts) FROM market_candles_15m WHERE ipo_id=%s", (ipo_id,))
        latest = (cur.fetchone() or [None])[0]
        start = latest + dt.timedelta(microseconds=1) if latest else listing_date
        item = {"ipo_id": ipo_id, "name": name, "from": str(start)}
        try:
            for attempt in range(2):
                try:
                    bars = fetch_candles_15m(kite, token, start, today)
                    break
                except Exception as exc:
                    if not is_transient(exc) or attempt:
                        raise
                    sleep(0.5)
            received = len(bars)
            inserted = insert_bars(conn, ipo_id, bars) if bars else 0
            summary["bars_received"] += received
            summary["bars_inserted"] += inserted
            summary["duplicates"] += received - inserted
            if not bars:
                summary["no_data"] += 1
            item.update(status="ok" if bars else "no_data", received=received, inserted=inserted)
        except Exception as exc:
            conn.rollback()
            if not is_transient(exc):
                raise
            summary["transient_failed"] += 1
            item.update(status="transient_failed", error=type(exc).__name__)
        summary["ipos"].append(item)
        sleep(throttle_seconds)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if not (args.dry_run or args.write):
        parser.error("choose --dry-run or --write")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        result = run(conn, limit=max(1, args.limit), dry_run=args.dry_run)
    finally:
        conn.close()
    print("FIFTEEN_MIN_CANDLES=" + json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
