#!/usr/bin/env python3
"""Bounded, official-only NSE ISIN/listing-date refresh for canonical IPO rows."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os

EQUITY_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SOURCE = "nse_equity_master"


def select_isin_candidates(conn, today, limit):
    cur = conn.cursor()
    cur.execute("""SELECT id,name_display,symbol,isin,listing_date
        FROM ipo WHERE isin IS NULL AND symbol IS NOT NULL AND listing_date IS NOT NULL
        AND listing_date <= %s ORDER BY listing_date,id LIMIT %s""",
        (today + dt.timedelta(days=1), limit))
    return cur.fetchall()


def select_listing_date_candidates(conn, limit):
    cur = conn.cursor()
    cur.execute("""SELECT id,name_display,symbol,isin,listing_date
        FROM ipo WHERE listing_date IS NULL AND symbol IS NOT NULL AND status='announced'
        ORDER BY created_at,id LIMIT %s""", (limit,))
    return cur.fetchall()


def parse_equity_master(content):
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    normalized = {h.strip().upper(): h for h in headers}
    aliases = {
        "symbol": ("SYMBOL",),
        "name": ("NAME OF COMPANY", "COMPANY NAME"),
        "isin": ("ISIN NUMBER", "ISIN"),
        "listing_date": ("DATE OF LISTING", "LISTING DATE"),
    }
    keys = {kind: next((normalized[a] for a in names if a in normalized), None)
            for kind, names in aliases.items()}
    if not keys["symbol"] or not keys["name"]:
        raise ValueError(f"unsupported EQUITY_L headers: {headers}")
    rows = {}
    for row in reader:
        symbol = (row.get(keys["symbol"]) or "").strip().upper()
        if not symbol:
            continue
        date_value = (row.get(keys["listing_date"]) or "").strip() if keys["listing_date"] else ""
        listing_date = None
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                listing_date = dt.datetime.strptime(date_value, fmt).date(); break
            except ValueError:
                pass
        rows[symbol] = {"symbol": symbol, "name": (row.get(keys["name"]) or "").strip(),
                        "isin": (row.get(keys["isin"]) or "").strip().upper() if keys["isin"] else None,
                        "listing_date": listing_date}
    return headers, rows


def quote_record(payload, requested_symbol):
    meta = (payload or {}).get("meta") or {}
    info = (payload or {}).get("info") or {}
    symbol = str(meta.get("symbol") or info.get("symbol") or "").strip().upper()
    if symbol != requested_symbol.upper():
        return None
    name = info.get("companyName") or meta.get("companyName")
    date_value = meta.get("listingDate")
    try: listing_date = dt.date.fromisoformat(str(date_value)[:10]) if date_value else None
    except ValueError: listing_date = None
    return {"symbol": symbol, "name": name, "isin": meta.get("isin"),
            "listing_date": listing_date}


def _name_matches(canonical_name, official_name):
    from fill_ipo import _norm
    return bool(official_name) and _norm(canonical_name) == _norm(official_name)


def _fill_empty(conn, ipo_id, field, value, *, write):
    if value is None or not write:
        return False
    from fill_v2 import log_source_fact
    cur = conn.cursor()
    cur.execute(f"UPDATE ipo SET {field}=COALESCE({field}, %s) WHERE id=%s AND {field} IS NULL",
                (value, ipo_id))
    changed = cur.rowcount == 1
    if changed:
        log_source_fact(conn, ipo_id, field, value, SOURCE)
    return changed


def refresh(conn, session, *, limit=10, quote_limit=10, write=False, today=None):
    today = today or dt.datetime.now(IST).date()
    isin_rows = select_isin_candidates(conn, today, limit)
    remaining = max(0, limit - len(isin_rows))
    listing_rows = select_listing_date_candidates(conn, remaining)
    selected = isin_rows + listing_rows
    response = session.get(EQUITY_MASTER_URL, timeout=20)
    response.raise_for_status()
    headers, master = parse_equity_master(response.content)
    report, quote_calls, updates = [], 0, 0
    for ipo_id, name, symbol, old_isin, old_date in selected:
        requested = symbol.strip().upper()
        official = master.get(requested)
        source = "csv"
        if official is None and quote_calls < quote_limit:
            quote_calls += 1
            quote = session.get(QUOTE_URL.format(symbol=requested), timeout=15)
            if quote.status_code == 200:
                official = quote_record(quote.json(), requested)
            source = "quote"
        if not official:
            report.append({"ipo_id": ipo_id, "symbol": requested, "outcome": "not_found", "source": source})
            continue
        if not _name_matches(name, official.get("name")):
            report.append({"ipo_id": ipo_id, "symbol": requested, "outcome": "name_mismatch", "source": source})
            continue
        changed = []
        prospective = []
        if old_isin is None and official.get("isin"):
            prospective.append("isin")
            if _fill_empty(conn, ipo_id, "isin", official["isin"], write=write): changed.append("isin")
        if old_date is None and official.get("listing_date"):
            prospective.append("listing_date")
            if _fill_empty(conn, ipo_id, "listing_date", official["listing_date"], write=write): changed.append("listing_date")
        updates += len(changed)
        report.append({"ipo_id": ipo_id, "symbol": requested,
                       "outcome": "updated" if changed else ("would_update" if prospective and not write else "no_value"),
                       "source": source, "fields": changed if write else prospective})
    if write: conn.commit()
    return {"headers": headers, "selected": len(selected), "quote_calls": quote_calls,
            "updates": updates, "rows": report}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=10); ap.add_argument("--quote-limit", type=int, default=10)
    args = ap.parse_args(argv)
    if not (args.write ^ args.dry_run): raise SystemExit("choose exactly one of --write or --dry-run")
    if args.limit < 0 or args.quote_limit < 0: raise SystemExit("limits must be non-negative")
    print("OPERATIONS_BUDGET " + json.dumps({"max_session_prime_calls": 2, "max_csv_calls": 1,
          "max_quote_calls": args.quote_limit, "max_selected_rows": args.limit,
          "max_updates": args.limit * 2}, sort_keys=True))
    import psycopg2
    from curl_cffi import requests
    from nse_fetch import prime
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        result = refresh(conn, prime(requests), limit=args.limit,
                         quote_limit=args.quote_limit, write=args.write)
        print(json.dumps(result, default=str, indent=2, sort_keys=True))
    finally: conn.close()
    return result


if __name__ == "__main__": main()
