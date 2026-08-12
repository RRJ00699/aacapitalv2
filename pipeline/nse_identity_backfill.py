#!/usr/bin/env python3
"""Bounded, official-only NSE ISIN/listing-date refresh for canonical IPO rows."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re

EQUITY_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SOURCE = "nse_equity_master"
ISIN_PATTERN = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")


class SourceUnavailable(RuntimeError):
    """The upstream NSE primary source (EQUITY_L.csv) answered with a non-200 status.

    For a bounded nightly backfill this is an EXPECTED, RECOVERABLE condition
    (throttling, maintenance windows, or runner-IP policy), not a code fault: nothing
    was filled and nothing was corrupted. It is raised as a distinct type so the entry
    point can treat it as a clean no-op (exit 0 with a visible marker) while genuine
    faults - DB errors, malformed data, unexpected exceptions - still surface as a
    non-zero exit. See main().
    """


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
    isin = str(meta.get("isin") or "").strip().upper() or None
    return {"symbol": symbol, "name": name, "isin": isin,
            "listing_date": listing_date}


def _name_matches(canonical_name, official_name):
    from company_identity import canon
    return bool(official_name) and canon(canonical_name) == canon(official_name)


def _fill_empty(conn, ipo_id, field, value, *, write):
    assert field in {"isin", "listing_date"}
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
    # Reserve capacity for both cohorts so persistent identity misses cannot starve
    # announced rows awaiting their first listing date.
    isin_quota = (limit + 1) // 2 if limit > 1 else limit
    listing_quota = limit - isin_quota
    isin_rows = select_isin_candidates(conn, today, isin_quota)
    listing_rows = select_listing_date_candidates(conn, listing_quota)
    selected = isin_rows + listing_rows
    response = session.get(EQUITY_MASTER_URL, timeout=20)
    status = getattr(response, "status_code", 200)
    if status != 200:
        # A non-200 from the primary ISIN source is a bounded, recoverable no-op, not a
        # failure: surface it as SourceUnavailable so main() can exit 0 cleanly.
        raise SourceUnavailable(f"EQUITY_L.csv returned HTTP {status}")
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
        official_isin = str(official.get("isin") or "").strip().upper() or None
        if official_isin and not ISIN_PATTERN.fullmatch(official_isin):
            report.append({"ipo_id": ipo_id, "symbol": requested,
                           "outcome": "invalid_isin", "source": source,
                           "isin": official_isin})
            continue
        if old_isin is None and official_isin:
            cur = conn.cursor()
            cur.execute("SELECT id FROM ipo WHERE isin=%s LIMIT 1", (official_isin,))
            owner = cur.fetchone()
            if owner and owner[0] != ipo_id:
                report.append({"ipo_id": ipo_id, "candidate_ipo_id": ipo_id,
                               "owner_ipo_id": owner[0], "symbol": requested,
                               "outcome": "isin_owner_conflict", "source": source})
                continue
        changed = []
        prospective = []
        if old_isin is None and official_isin:
            prospective.append("isin")
            if _fill_empty(conn, ipo_id, "isin", official_isin, write=write): changed.append("isin")
        if old_date is None and official.get("listing_date"):
            prospective.append("listing_date")
            if _fill_empty(conn, ipo_id, "listing_date", official["listing_date"], write=write): changed.append("listing_date")
        updates += len(changed)
        report.append({"ipo_id": ipo_id, "symbol": requested,
                       "outcome": "updated" if changed else ("would_update" if prospective and not write else "no_value"),
                       "source": source, "fields": changed if write else prospective})
    if write: conn.commit()
    return {"headers": headers, "selected": len(selected),
            "selected_by_need": {"isin": len(isin_rows), "listing_date": len(listing_rows)},
            "selector_quotas": {"isin": isin_quota, "listing_date": listing_quota},
            "quote_calls": quote_calls,
            "updates": updates, "rows": report}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=10); ap.add_argument("--quote-limit", type=int, default=10)
    args = ap.parse_args(argv)
    if not (args.write ^ args.dry_run): raise SystemExit("choose exactly one of --write or --dry-run")
    if args.limit < 0 or args.quote_limit < 0: raise SystemExit("limits must be non-negative")
    isin_quota = (args.limit + 1) // 2 if args.limit > 1 else args.limit
    print("OPERATIONS_BUDGET " + json.dumps({"max_session_prime_calls": 2, "max_csv_calls": 1,
          "max_quote_calls": args.quote_limit, "max_selected_rows": args.limit,
          "max_isin_candidates": isin_quota,
          "max_listing_date_candidates": args.limit - isin_quota,
          "max_updates": args.limit * 2}, sort_keys=True))
    import psycopg2
    from curl_cffi import requests
    from nse_fetch import prime
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        result = refresh(conn, prime(requests), limit=args.limit,
                         quote_limit=args.quote_limit, write=args.write)
    except SourceUnavailable as exc:
        # CLEAN NO-OP -> EXIT 0. The primary source was unavailable this run; nothing was
        # filled and nothing was corrupted. Emit a visible marker in the normal result
        # shape (so the orchestrator's counts parser still reads selected/updates) and
        # return so the process exits 0. A genuine fault (DB, parse, or any other
        # unexpected exception) is deliberately NOT caught here and still exits non-zero.
        result = {"headers": [], "selected": 0,
                  "selected_by_need": {"isin": 0, "listing_date": 0},
                  "selector_quotas": {"isin": 0, "listing_date": 0},
                  "quote_calls": 0, "updates": 0, "rows": [],
                  "skipped": "source_unavailable", "detail": str(exc)}
    finally:
        conn.close()
    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    return result


if __name__ == "__main__": main()
