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


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def parse_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    return list(dict.fromkeys(int(part) for part in value.split(",") if part.strip()))


def select_targets(conn, limit: int, ids: list[int] | None = None):
    """Select exact IDs or the progress-safe canonical 100-day mainboard cohort."""
    cur = conn.cursor()
    id_clause = "AND i.id = ANY(%s)" if ids is not None else ""
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    eligibility = f"""AND {CANONICAL_UNIVERSE_SQL}
        AND i.listing_date BETWEEN
        ((now() AT TIME ZONE 'Asia/Kolkata')::date - 100)
        AND (now() AT TIME ZONE 'Asia/Kolkata')::date AND i.kite_token IS NOT NULL"""
    limit_clause = "" if ids is not None else "LIMIT %s"
    params = ([ids] if ids is not None else [limit])
    cur.execute(f"""SELECT i.id,i.isin,i.symbol,i.name_display,i.listing_date,i.kite_token,
                            i.is_mainboard, i.status
      FROM ipo i
      LEFT JOIN (SELECT ipo_id,max(ts) AS latest FROM market_candles_15m GROUP BY ipo_id) c
        ON c.ipo_id=i.id
      WHERE TRUE {eligibility}
      {id_clause}
      ORDER BY c.latest ASC NULLS FIRST,i.id {limit_clause}""", params)
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


def run(conn, *, limit: int, dry_run: bool, ids: list[int] | None = None,
        throttle_seconds: float = 0.34, sleep=time.sleep):
    targets = select_targets(conn, limit, ids)
    requested = len(ids) if ids is not None else len(targets)
    summary = {"requested": requested, "selected": len(targets), "eligible": 0,
               "attempted": 0, "bars_received": 0,
               "bars_inserted": 0, "duplicates": 0, "no_data": 0,
               "transient_failed": 0, "exclusions": {}, "ipos": []}
    by_id = {row[0]: row for row in targets}
    for missing_id in (value for value in (ids or []) if value not in by_id):
        summary["exclusions"]["not_found"] = summary["exclusions"].get("not_found", 0) + 1
        summary["ipos"].append({"ipo_id": missing_id, "status": "not_found"})
    today = dt.datetime.now(IST).date()
    eligible = []
    from nse_fetch import canonical_spine_eligible
    for row in targets:
        ipo_id, _isin, _symbol, name, listing_date, token, is_mainboard, status = row
        reason = ("out_of_universe" if not canonical_spine_eligible(is_mainboard, status) else
                  "missing_listing_date" if listing_date is None else
                  "outside_window" if not (today - dt.timedelta(days=100) <= listing_date <= today) else
                  "missing_token" if token is None else None)
        # A stored token is sufficient: blank symbols must not suppress an explicit ID.
        if reason:
            summary["exclusions"][reason] = summary["exclusions"].get(reason, 0) + 1
            summary["ipos"].append({"ipo_id": ipo_id, "name": name, "status": reason})
        else:
            eligible.append(row)
    targets = eligible
    summary["eligible"] = len(targets)
    terminal = len(summary["ipos"]) + len(targets)
    if ids is not None and terminal != requested:
        raise AssertionError(f"explicit ID accounting mismatch: requested={requested} outcomes={terminal}")
    if dry_run:
        summary["ipos"].extend({"ipo_id": row[0], "name": row[3], "status": "eligible"} for row in targets)
        return summary
    if not targets:
        return summary
    kite = get_kite()
    cur = conn.cursor()
    end = dt.datetime.now(IST)
    for ipo_id, _isin, _symbol, name, listing_date, token, _mainboard, _status in targets:
        summary["attempted"] += 1
        cur.execute("SELECT max(ts) FROM market_candles_15m WHERE ipo_id=%s", (ipo_id,))
        latest = (cur.fetchone() or [None])[0]
        # Kite bars are aligned to 15-minute boundaries. Keep both paginator bounds
        # timezone-aware and resume at the next possible identity, never +1 microsecond.
        start = (latest.astimezone(IST) + dt.timedelta(minutes=15)) if latest else dt.datetime.combine(listing_date, dt.time.min, IST)
        item = {"ipo_id": ipo_id, "name": name, "from": str(start)}
        try:
            for attempt in range(2):
                try:
                    bars = fetch_candles_15m(kite, token, start, end)
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
    parser.add_argument("--ids", help="exact comma-separated IPO IDs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if not (args.dry_run or args.write):
        parser.error("choose --dry-run or --write")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        result = run(conn, limit=max(1, args.limit), dry_run=args.dry_run,
                     ids=parse_ids(args.ids))
    finally:
        conn.close()
    print("FIFTEEN_MIN_CANDLES=" + json.dumps(result, default=str, sort_keys=True))
    if result["eligible"] and result["transient_failed"] == result["eligible"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
