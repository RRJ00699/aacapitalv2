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
import time

from curl_cffi import requests as cffi_requests

EQUITY_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SOURCE = "nse_equity_master"
ISIN_PATTERN = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")
DB_CONNECT_TIMEOUT = 25
DB_STATEMENT_TIMEOUT_MS = 30_000
DB_LOCK_TIMEOUT_MS = 5_000


class DeadlineExceeded(RuntimeError):
    pass


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
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    cur = conn.cursor()
    cur.execute("""SELECT id,name_display,symbol,isin,listing_date
        FROM ipo i WHERE isin IS NULL AND symbol IS NOT NULL AND listing_date IS NOT NULL
        AND """ + CANONICAL_UNIVERSE_SQL + """
        AND (upper(COALESCE(i.status,'')) IN ('ANNOUNCED','UPCOMING','OPEN','CLOSED')
          OR (upper(COALESCE(i.status,''))='LISTED'
            AND i.listing_date BETWEEN %s AND %s))
        ORDER BY listing_date NULLS FIRST,id LIMIT %s""",
        (today - dt.timedelta(days=100), today + dt.timedelta(days=1), limit))
    return cur.fetchall()


def select_listing_date_candidates(conn, limit):
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    cur = conn.cursor()
    cur.execute("""SELECT id,name_display,symbol,isin,listing_date
        FROM ipo i WHERE listing_date IS NULL AND symbol IS NOT NULL AND """ + CANONICAL_UNIVERSE_SQL + """
        AND upper(COALESCE(i.status,'')) IN ('ANNOUNCED','UPCOMING','OPEN','CLOSED')
        ORDER BY created_at,id LIMIT %s""", (limit,))
    return cur.fetchall()


def count_legacy_unresolved(conn, today):
    """Count permanent historical misses excluded from the bounded active retry lane."""
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    cur = conn.cursor()
    cur.execute("""SELECT count(*) FROM ipo i WHERE i.symbol IS NOT NULL
      AND (i.isin IS NULL OR i.listing_date IS NULL)
      AND NOT (""" + CANONICAL_UNIVERSE_SQL + """ AND (
        (i.isin IS NULL AND (upper(COALESCE(i.status,'')) IN ('ANNOUNCED','UPCOMING','OPEN','CLOSED')
          OR (upper(COALESCE(i.status,''))='LISTED' AND i.listing_date BETWEEN %s AND %s)))
        OR (i.listing_date IS NULL AND upper(COALESCE(i.status,''))
          IN ('ANNOUNCED','UPCOMING','OPEN','CLOSED'))))""",
        (today - dt.timedelta(days=100), today + dt.timedelta(days=1)))
    return int((cur.fetchone() or [0])[0])


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
    try:
        cur.execute(f"UPDATE ipo SET {field}=COALESCE({field}, %s) WHERE id=%s AND {field} IS NULL",
                    (value, ipo_id))
        changed = cur.rowcount == 1
        if changed:
            log_source_fact(conn, ipo_id, field, value, SOURCE, commit=False)
    except Exception:
        conn.rollback()
        raise
    return changed


def refresh(conn, session, *, limit=10, quote_limit=10, write=False, today=None,
            deadline=None, clock=time.monotonic, timings=None):
    timings = timings if timings is not None else []
    started_run = clock()

    def remaining_timeout(configured):
        if deadline is None:
            return configured
        remaining = deadline - clock()
        if remaining <= 0:
            raise DeadlineExceeded("runtime deadline exhausted")
        return min(configured, remaining)

    def timed_db(operation, fn, *, symbol=None, timeout_ms=DB_STATEMENT_TIMEOUT_MS):
        started = clock(); outcome = "found"
        try:
            if deadline is not None:
                timeout_ms = max(1, int(remaining_timeout(DB_STATEMENT_TIMEOUT_MS / 1000) * 1000))
                timeout_cur = conn.cursor()
                timeout_cur.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
                timeout_cur.execute("SET LOCAL lock_timeout = %s", (min(DB_LOCK_TIMEOUT_MS, timeout_ms),))
            else:
                remaining_timeout(0.001)
            return fn()
        except DeadlineExceeded:
            outcome = "not_attempted_deadline"; raise
        except Exception:
            outcome = "error"; raise
        finally:
            item = {"operation": operation, "elapsed_ms": round((clock()-started)*1000, 3),
                    "timeout_ms": timeout_ms, "outcome": outcome}
            if symbol is not None: item["symbol"] = symbol
            timings.append(item)

    today = today or dt.datetime.now(IST).date()
    # Reserve capacity for both cohorts so persistent identity misses cannot starve
    # announced rows awaiting their first listing date.
    isin_quota = (limit + 1) // 2 if limit > 1 else limit
    listing_quota = limit - isin_quota
    isin_rows = timed_db("selector_isin", lambda: select_isin_candidates(conn, today, isin_quota))
    listing_rows = timed_db("selector_listing_date", lambda: select_listing_date_candidates(conn, listing_quota))
    selected = isin_rows + listing_rows
    legacy_unresolved = timed_db("legacy_unresolved_count", lambda: count_legacy_unresolved(conn, today))

    def unavailable(reason, outcome):
        exc = SourceUnavailable(reason)
        exc.result = {"status": "skipped", "reason": "source_unavailable", "headers": [],
                      "selected": len(selected),
                      "selected_by_need": {"isin": len(isin_rows), "listing_date": len(listing_rows)},
                      "selector_quotas": {"isin": isin_quota, "listing_date": listing_quota},
                      "quote_calls": 0, "updates": 0,
                      "legacy_unresolved_not_retried": legacy_unresolved,
                      "rows": [{"ipo_id": row[0], "symbol": row[2].strip().upper(),
                                "outcome": outcome, "source_outcome": outcome,
                                "source": "csv", "elapsed_ms": 0.0} for row in selected],
                      "timings": timings}
        return exc

    csv_started = clock(); csv_timeout = None; csv_outcome = "found"
    try:
        csv_timeout = remaining_timeout(20)
        response = session.get(EQUITY_MASTER_URL, timeout=csv_timeout)
    except DeadlineExceeded:
        csv_outcome = "not_attempted_deadline"
        raise unavailable("equity_master deadline exhausted", csv_outcome)
    except (cffi_requests.RequestsError, TimeoutError, ConnectionError):
        csv_outcome = "source_unavailable"
        raise unavailable("equity_master request unavailable", csv_outcome)
    finally:
        timings.append({"operation": "equity_master_csv", "elapsed_ms": round((clock()-csv_started)*1000, 3),
                        "timeout_ms": round(csv_timeout*1000, 3) if csv_timeout else 0,
                        "outcome": csv_outcome})
    status = getattr(response, "status_code", 200)
    if status != 200:
        timings[-1]["outcome"] = "source_unavailable"
        timings[-1]["http_status"] = status
        # A non-200 from the primary ISIN source is a bounded, recoverable no-op, not a
        # failure: surface it as SourceUnavailable so main() can exit 0 cleanly.
        raise unavailable(f"EQUITY_L.csv returned HTTP {status}", "source_unavailable")
    headers, master = parse_equity_master(response.content)
    report, quote_calls, updates = [], 0, 0
    for ipo_id, name, symbol, old_isin, old_date in selected:
        row_started = clock()
        requested = symbol.strip().upper()
        official = master.get(requested)
        source = "csv"
        source_outcome = "found" if official is not None else None
        if official is None and quote_calls >= quote_limit:
            source_outcome = "not_attempted_quote_quota"
        elif official is None:
            try:
                quote_timeout = remaining_timeout(15)
            except DeadlineExceeded:
                source_outcome = "not_attempted_deadline"
            else:
                quote_calls += 1; source = "quote"; quote_started = clock()
                quote_outcome = "found"; status = None
                try:
                    quote = session.get(QUOTE_URL.format(symbol=requested), timeout=quote_timeout)
                except (cffi_requests.RequestsError, TimeoutError, ConnectionError):
                    quote_outcome = source_outcome = "source_unavailable"
                else:
                    status = getattr(quote, "status_code", 200)
                    if status == 429 or status >= 500:
                        quote_outcome = source_outcome = "source_unavailable"
                    elif status != 200:
                        quote_outcome = source_outcome = "invalid_response"
                    else:
                        try:
                            payload = quote.json()
                        except ValueError:
                            quote_outcome = source_outcome = "invalid_response"
                        else:
                            if not isinstance(payload, dict):
                                quote_outcome = source_outcome = "invalid_response"
                            else:
                                meta, info = payload.get("meta") or {}, payload.get("info") or {}
                                if not isinstance(meta, dict) or not isinstance(info, dict):
                                    quote_outcome = source_outcome = "invalid_response"
                                else:
                                    returned = str(meta.get("symbol") or info.get("symbol") or "").strip().upper()
                                    if returned and returned != requested:
                                        quote_outcome = source_outcome = "exact_symbol_mismatch"
                                    else:
                                        official = quote_record(payload, requested)
                                        if official is None:
                                            quote_outcome = source_outcome = "invalid_response"
                                        else: source_outcome = "found"
                item = {"operation": "quote", "symbol": requested,
                        "elapsed_ms": round((clock()-quote_started)*1000, 3),
                        "timeout_ms": round(quote_timeout*1000, 3), "outcome": quote_outcome}
                if status is not None: item["http_status"] = status
                timings.append(item)
        if not official:
            report.append({"ipo_id": ipo_id, "symbol": requested, "outcome": source_outcome,
                           "source_outcome": source_outcome, "source": source,
                           "elapsed_ms": round((clock()-row_started)*1000, 3)})
            continue
        if not _name_matches(name, official.get("name")):
            report.append({"ipo_id": ipo_id, "symbol": requested, "outcome": "name_mismatch",
                           "source_outcome": "found", "source": source,
                           "elapsed_ms": round((clock()-row_started)*1000, 3)})
            continue
        official_isin = str(official.get("isin") or "").strip().upper() or None
        if official_isin and not ISIN_PATTERN.fullmatch(official_isin):
            report.append({"ipo_id": ipo_id, "symbol": requested,
                           "outcome": "invalid_isin", "source": source,
                           "source_outcome": "found", "isin": official_isin,
                           "elapsed_ms": round((clock()-row_started)*1000, 3)})
            continue
        if old_isin is None and official_isin:
            def find_owner():
                cur = conn.cursor(); cur.execute("SELECT id FROM ipo WHERE isin=%s LIMIT 1", (official_isin,))
                return cur.fetchone()
            owner = timed_db("isin_owner_check", find_owner, symbol=requested)
            if owner and owner[0] != ipo_id:
                report.append({"ipo_id": ipo_id, "candidate_ipo_id": ipo_id,
                               "owner_ipo_id": owner[0], "symbol": requested,
                               "outcome": "isin_owner_conflict", "source_outcome": "found",
                               "source": source, "elapsed_ms": round((clock()-row_started)*1000, 3)})
                continue
        changed = []
        prospective = []
        if old_isin is None and official_isin:
            prospective.append("isin")
            if timed_db("update_source_fact", lambda: _fill_empty(conn, ipo_id, "isin", official_isin, write=write),
                        symbol=requested): changed.append("isin")
        if old_date is None and official.get("listing_date"):
            prospective.append("listing_date")
            if timed_db("update_source_fact", lambda: _fill_empty(conn, ipo_id, "listing_date", official["listing_date"], write=write),
                        symbol=requested): changed.append("listing_date")
        updates += len(changed)
        report.append({"ipo_id": ipo_id, "symbol": requested,
                       "outcome": "updated" if changed else ("would_update" if prospective and not write else "no_value"),
                       "source_outcome": "found", "source": source, "fields": changed if write else prospective,
                       "elapsed_ms": round((clock()-row_started)*1000, 3)})
    if write and updates:
        try: timed_db("final_commit", conn.commit)
        except Exception:
            try: conn.rollback()
            finally: raise RuntimeError("final_commit_failed") from None
    return {"headers": headers, "selected": len(selected),
            "selected_by_need": {"isin": len(isin_rows), "listing_date": len(listing_rows)},
            "selector_quotas": {"isin": isin_quota, "listing_date": listing_quota},
            "quote_calls": quote_calls,
            "legacy_unresolved_not_retried": legacy_unresolved,
            "updates": updates, "rows": report, "timings": timings,
            "elapsed_ms": round((clock()-started_run)*1000, 3)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=10); ap.add_argument("--quote-limit", type=int, default=10)
    ap.add_argument("--max-runtime-seconds", type=float, default=240)
    args = ap.parse_args(argv)
    if not (args.write ^ args.dry_run): raise SystemExit("choose exactly one of --write or --dry-run")
    if args.limit < 0 or args.quote_limit < 0 or args.max_runtime_seconds < 1: raise SystemExit("runtime must be at least one second; row limits must be non-negative")
    isin_quota = (args.limit + 1) // 2 if args.limit > 1 else args.limit
    print("OPERATIONS_BUDGET " + json.dumps({"max_session_prime_calls": 2, "max_csv_calls": 1,
          "max_quote_calls": args.quote_limit, "max_selected_rows": args.limit,
          "max_isin_candidates": isin_quota,
          "max_listing_date_candidates": args.limit - isin_quota,
          "max_updates": args.limit * 2, "max_runtime_seconds": args.max_runtime_seconds}, sort_keys=True))
    import psycopg2
    from curl_cffi import requests
    from nse_fetch import prime
    timings = []; clock = time.monotonic; deadline = clock() + args.max_runtime_seconds
    connect_started = clock(); connect_timeout = max(1, min(DB_CONNECT_TIMEOUT, int(args.max_runtime_seconds)))
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=connect_timeout,
                                keepalives=1, keepalives_idle=30,
                                keepalives_interval=10, keepalives_count=3,
                                options=(f"-c statement_timeout={min(DB_STATEMENT_TIMEOUT_MS, int(args.max_runtime_seconds*1000))} "
                                         f"-c lock_timeout={min(DB_LOCK_TIMEOUT_MS, int(args.max_runtime_seconds*1000))}"))
    except Exception:
        timings.append({"operation": "db_connect", "elapsed_ms": round((clock()-connect_started)*1000, 3),
                        "timeout_ms": connect_timeout*1000, "outcome": "error"})
        print(json.dumps({"status": "failed", "reason": "db_connect_failed", "timings": timings}, sort_keys=True))
        raise RuntimeError("db_connect_failed") from None
    timings.append({"operation": "db_connect", "elapsed_ms": round((clock()-connect_started)*1000, 3),
                    "timeout_ms": connect_timeout*1000, "outcome": "found"})
    failure = None
    try:
        remaining_ms = max(1, min(DB_STATEMENT_TIMEOUT_MS, int((deadline-clock())*1000)))
        config_started = clock(); cur = conn.cursor()
        cur.execute("SET statement_timeout = %s", (remaining_ms,))
        cur.execute("SET lock_timeout = %s", (min(DB_LOCK_TIMEOUT_MS, remaining_ms),))
        timings.append({"operation": "db_session_config", "elapsed_ms": round((clock()-config_started)*1000, 3),
                        "timeout_ms": remaining_ms, "outcome": "found"})
        def timeout_for(configured):
            remaining = deadline-clock()
            if remaining <= 0: raise DeadlineExceeded("runtime deadline exhausted")
            return min(configured, remaining)
        def prime_timing(operation, started, timeout, outcome):
            timings.append({"operation": operation, "elapsed_ms": round((clock()-started)*1000, 3),
                            "timeout_ms": round(timeout*1000, 3), "outcome": outcome})
        try:
            session = prime(requests, timeout_for=timeout_for, record_timing=prime_timing)
        except DeadlineExceeded:
            raise SourceUnavailable("nse_prime deadline exhausted") from None
        except (requests.RequestsError, TimeoutError, ConnectionError):
            raise SourceUnavailable("nse_prime transport unavailable") from None
        result = refresh(conn, session, limit=args.limit, quote_limit=args.quote_limit,
                         write=args.write, deadline=deadline, clock=clock, timings=timings)
    except SourceUnavailable as exc:
        # CLEAN NO-OP -> EXIT 0. The primary source was unavailable this run; nothing was
        # filled and nothing was corrupted. Emit a visible marker in the normal result
        # shape (so the orchestrator's counts parser still reads selected/updates) and
        # return so the process exits 0. A genuine fault (DB, parse, or any other
        # unexpected exception) is deliberately NOT caught here and still exits non-zero.
        conn.rollback()
        result = getattr(exc, "result", {"status": "skipped", "reason": "source_unavailable",
                         "timings": timings})
        result["evidence"] = {"source": "NSE", "detail": str(exc)}
    except Exception as exc:
        conn.rollback()
        reason = "final_commit_failed" if str(exc) == "final_commit_failed" else "backfill_failed"
        result = {"status": "failed", "reason": reason, "timings": timings}
        failure = RuntimeError(reason)
    finally:
        conn.close()
    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    if failure is not None:
        raise failure from None
    return result


if __name__ == "__main__": main()
