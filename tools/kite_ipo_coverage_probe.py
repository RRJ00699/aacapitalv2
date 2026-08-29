from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv('.env.local')
load_dotenv('.env')

SAMPLE_YEARS = (2016, 2018, 2020, 2023, 2026)
INTERVALS = ('day', '15minute', '5minute')
RATE_SLEEP = 0.4


def as_date(v):
    if v is None:
        return None
    if hasattr(v, 'date') and not isinstance(v, date):
        return v.date()
    return v


def load_sample_and_token(conn):
    cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
    row = cur.fetchone()
    if not row or not row[0]:
        raise SystemExit('No kite_access_token in Neon. Run _scripts/refresh_kite_token.py first.')
    token = row[0]

    cur.execute("""
        WITH ranked AS (
          SELECT EXTRACT(YEAR FROM listing_date)::int AS yr,
                 id, name_display, symbol, isin, listing_date, lock30, kite_token,
                 ROW_NUMBER() OVER (
                   PARTITION BY EXTRACT(YEAR FROM listing_date)::int
                   ORDER BY listing_date, id
                 ) AS rn
          FROM ipo
          WHERE listing_date IS NOT NULL
            AND symbol IS NOT NULL
            AND is_mainboard IS TRUE
            AND EXTRACT(YEAR FROM listing_date)::int = ANY(%s)
        )
        SELECT yr,id,name_display,symbol,isin,listing_date,lock30,kite_token
        FROM ranked
        WHERE rn <= 2
        ORDER BY yr, listing_date
    """, (list(SAMPLE_YEARS),))
    rows = cur.fetchall()
    cur.close()
    return token, rows


def summarize_bars(bars):
    if not bars:
        return {'rows': 0, 'first': None, 'last': None, 'traded_rows': 0}
    traded = sum(1 for b in bars if (b.get('volume') or 0) > 0)
    first = bars[0].get('date')
    last = bars[-1].get('date')
    return {
        'rows': len(bars),
        'first': first.isoformat() if hasattr(first, 'isoformat') else str(first),
        'last': last.isoformat() if hasattr(last, 'isoformat') else str(last),
        'traded_rows': traded,
    }


def main():
    ap = argparse.ArgumentParser(description='Read-only Kite historical coverage probe for IPO listing-to-lock30 windows')
    ap.add_argument('--output', type=Path, default=Path('artifacts/kite-ipo-coverage-probe.json'))
    args = ap.parse_args()

    db = os.environ.get('DATABASE_URL') or os.environ.get('NEON_DATABASE_URL') or os.environ.get('NEON_READONLY_DATABASE_URL')
    api_key = os.environ.get('KITE_API_KEY', '')
    if not db:
        raise SystemExit('DATABASE_URL / NEON_DATABASE_URL / NEON_READONLY_DATABASE_URL missing')
    if not api_key:
        raise SystemExit('KITE_API_KEY missing')

    conn = psycopg2.connect(db, connect_timeout=20)
    try:
        access_token, sample = load_sample_and_token(conn)
    finally:
        conn.close()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()
    print(f"Kite token valid for user_id={profile.get('user_id')}")

    results = []
    per_interval_rows = defaultdict(list)
    for yr, ipo_id, name, symbol, isin, listing_date, lock30, kite_token in sample:
        start = as_date(listing_date)
        end = as_date(lock30)
        if not end:
            end = date.fromordinal(start.toordinal() + 30)
        token = int(kite_token) if kite_token else None
        item = {
            'year': int(yr), 'ipo_id': int(ipo_id), 'name': name, 'symbol': symbol,
            'isin': isin, 'listing_date': start.isoformat(), 'lock30': end.isoformat(),
            'kite_token': token, 'intervals': {}
        }
        print(f"\n{yr} {symbol:<14} {start} -> {end} token={token}")
        if token is None:
            item['error'] = 'NO_STORED_KITE_TOKEN'
            results.append(item)
            print('  no stored Kite instrument token; skipped')
            continue

        for interval in INTERVALS:
            try:
                bars = kite.historical_data(token, start, end, interval)
                summary = summarize_bars(bars)
                summary['status'] = 'OK' if bars else 'EMPTY'
                item['intervals'][interval] = summary
                per_interval_rows[interval].append(summary['rows'])
                print(f"  {interval:<8} rows={summary['rows']:<5} traded={summary['traded_rows']:<5} first={summary['first']} last={summary['last']}")
            except Exception as exc:
                item['intervals'][interval] = {'status': 'ERROR', 'error': str(exc)[:300], 'rows': 0}
                print(f"  {interval:<8} ERROR {str(exc)[:180]}")
            time.sleep(RATE_SLEEP)
        results.append(item)

    # Storage projection uses sample average rows per IPO over the exact listing->lock30 window.
    projections = {}
    for interval in INTERVALS:
        vals = [x for x in per_interval_rows.get(interval, []) if x >= 0]
        if vals:
            projections[interval] = {
                'sample_ipos': len(vals),
                'avg_rows_per_ipo': round(statistics.mean(vals), 1),
                'median_rows_per_ipo': round(statistics.median(vals), 1),
                'projected_rows_500_ipos': int(round(statistics.mean(vals) * 500)),
                'projected_rows_1000_ipos': int(round(statistics.mean(vals) * 1000)),
            }

    payload = {
        'read_only': True,
        'sample_years': list(SAMPLE_YEARS),
        'sample_count': len(results),
        'intervals': list(INTERVALS),
        'results': results,
        'projections': projections,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')

    status_counts = defaultdict(int)
    for r in results:
        for interval in INTERVALS:
            status_counts[f"{interval}:{r.get('intervals',{}).get(interval,{}).get('status','SKIP')}"] += 1
    print('\n' + json.dumps({
        'sample_count': len(results),
        'status_counts': dict(sorted(status_counts.items())),
        'projections': projections,
        'output': str(args.output),
    }, sort_keys=True))


if __name__ == '__main__':
    main()
