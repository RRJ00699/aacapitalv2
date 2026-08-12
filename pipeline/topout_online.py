#!/usr/bin/env python3
"""DISCOVERY-only online level detector and canonical observation writer.

The pure detector consumes bars only through the evaluated bar. A later bar is never
used to revise an earlier decision. Production orchestration reads stored 15m bars;
it performs no broker calls and refuses writes unless the live schema permits `level`.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics

import psycopg2

DETECTOR_VERSION = "discovery-level-v1"


def detect_level(bars: list[dict], *, volume_window: int = 8, climax: float = 2.5) -> dict:
    if not bars:
        return {"state": "no_signal", "signal": None, "trigger_evidence": {}}
    highs = [float(b["h"]) for b in bars]
    lows = [float(b["l"]) for b in bars]
    closes = [float(b["c"]) for b in bars]
    volumes = [float(b.get("v") or 0) for b in bars]
    state, signal, evidence = "no_signal", None, {}
    if len(bars) >= 3 and highs[-1] < highs[-2] < highs[-3]:
        state, evidence = "watch_top", {"lower_highs": 2}
    elif len(bars) >= 3 and lows[-1] > lows[-2] > lows[-3]:
        state, evidence = "watch_bottom", {"higher_lows": 2}
    if len(bars) > volume_window:
        avg = statistics.mean(volumes[-volume_window-1:-1]) or 1
        ratio = volumes[-1] / avg
        if ratio >= climax and lows[-1] < min(lows[:-1]) and closes[-1] > lows[-1] * 1.01:
            state, signal, evidence = "bottom", "entry", {"volume_ratio": round(ratio, 3), "bounce_pct": round((closes[-1]-lows[-1])*100/lows[-1], 3)}
        elif ratio >= climax and highs[-1] > max(highs[:-1]) and closes[-1] < highs[-1] * .99:
            state, signal, evidence = "top", "exit", {"volume_ratio": round(ratio, 3), "rejection_pct": round((highs[-1]-closes[-1])*100/highs[-1], 3)}
    return {"state": state, "signal": signal, "trigger_evidence": evidence}


def level_is_permitted(conn) -> bool:
    cur = conn.cursor()
    cur.execute("""SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c
      JOIN pg_class t ON t.oid=c.conrelid WHERE t.relname='listing_observations' AND c.contype='c'""")
    definitions = " ".join(str(row[0]) for row in cur.fetchall()).lower()
    return not definitions or "obs_type" not in definitions or "level" in definitions


def run(conn, *, limit: int, dry_run: bool):
    cur = conn.cursor()
    cur.execute("""SELECT i.id,i.name_display FROM ipo i WHERE EXISTS
      (SELECT 1 FROM market_candles_15m c WHERE c.ipo_id=i.id)
      ORDER BY i.listing_date DESC NULLS LAST LIMIT %s""", (limit,))
    targets = cur.fetchall()
    if not dry_run and not level_is_permitted(conn):
        raise RuntimeError("owner: listing_observations schema does not permit obs_type='level'")
    states = []
    for ipo_id, name in targets:
        cur.execute("SELECT ts,o,h,l,c,v FROM market_candles_15m WHERE ipo_id=%s ORDER BY ts", (ipo_id,))
        rows = cur.fetchall()
        bars = [dict(zip(("ts","o","h","l","c","v"), row)) for row in rows]
        result = detect_level(bars)
        evaluated = bars[-1]["ts"]
        payload = {"detector_version": DETECTOR_VERSION, "evaluated_through_bar": evaluated.isoformat(),
                   "label": "DISCOVERY", **result}
        inserted = 0
        if not dry_run:
            cur.execute("""INSERT INTO listing_observations(ipo_id,observed_at,obs_type,payload)
              VALUES(%s,%s,'level',%s::jsonb) ON CONFLICT (ipo_id,obs_type,observed_at) DO NOTHING""",
                        (ipo_id, evaluated, json.dumps(payload)))
            inserted = cur.rowcount
        states.append({"ipo_id": ipo_id, "name": name, "inserted": inserted, **payload})
    if not dry_run:
        conn.commit()
    return {"selected": len(targets), "states": states, "label": "DISCOVERY"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if not (args.dry_run or args.write): parser.error("choose --dry-run or --write")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try: result = run(conn, limit=max(1,args.limit), dry_run=args.dry_run)
    finally: conn.close()
    print("TOP_BOTTOM_DETECTOR=" + json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__": main()
