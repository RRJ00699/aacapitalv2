#!/usr/bin/env python3
"""One bounded run of NSE lifecycle work, planned independently per IPO."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

from document_ledger import store_document
from lifecycle import IPOWindow, plan_run
from nse_fetch import apply_to_db, fetch_one, parse_issue_info, prime

DIAGNOSTIC_LOOKBACK_DAYS = 30


def _find_anchor_url(value):
    """Find NSE's anchor-allocation PDF without depending on JSON nesting."""
    if isinstance(value, dict):
        for key, child in value.items():
            if "anchor" in str(key).lower() and isinstance(child, str) and ".pdf" in child.lower():
                return child
        for child in value.values():
            found = _find_anchor_url(child)
            if found: return found
    elif isinstance(value, list):
        for child in value:
            found = _find_anchor_url(child)
            if found: return found
    elif isinstance(value, str) and "anchor" in value.lower() and ".pdf" in value.lower():
        return value
    return None


def _targets(conn, today, limit):
    cur = conn.cursor()
    cur.execute("""SELECT i.id, i.symbol, i.name_display, ii.open_date, ii.close_date,
                          i.listing_date,
                          (ii.band_lo IS NOT NULL AND ii.band_hi IS NOT NULL
                           AND ii.lot_size IS NOT NULL) AS issue_complete,
                          EXISTS (SELECT 1 FROM documents d
                                   WHERE d.ipo_id=i.id AND d.doc_type='anchor') AS anchor_banked,
                          EXISTS (SELECT 1 FROM subscription_snapshots s
                                   WHERE s.ipo_id=i.id AND s.is_final) AS final_subscription_banked
                     FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id
                    WHERE COALESCE(i.is_mainboard,TRUE)=TRUE
                      AND (i.listing_date BETWEEN %s - 1 AND %s
                           OR ii.open_date <= %s + 1 AND COALESCE(ii.close_date,%s) >= %s - 1)
                    ORDER BY COALESCE(i.listing_date,ii.open_date),i.id LIMIT %s""",
                (today, today, today, today, today, limit))
    return [IPOWindow(*row) for row in cur.fetchall()]


def _diagnostic_candidates(conn, today):
    """Read-only superset used to explain both inclusion and exclusion.

    Status catches upcoming rows whose lifecycle dates have not reached ``ipo_issue``;
    the date lookback catches recent historical rows that can enter the live SQL's
    one-day listing buffer.  This query never supplies work to ``run``.
    """
    cur = conn.cursor()
    cur.execute("""SELECT i.id, i.symbol, i.name_display, ii.open_date, ii.close_date,
                          i.listing_date,
                          (ii.band_lo IS NOT NULL AND ii.band_hi IS NOT NULL
                           AND ii.lot_size IS NOT NULL) AS issue_complete,
                          EXISTS (SELECT 1 FROM documents d
                                   WHERE d.ipo_id=i.id AND d.doc_type='anchor') AS anchor_banked,
                          EXISTS (SELECT 1 FROM subscription_snapshots s
                                   WHERE s.ipo_id=i.id AND s.is_final) AS final_subscription_banked
                     FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id
                    WHERE COALESCE(i.is_mainboard,TRUE)=TRUE
                      AND (UPPER(COALESCE(i.status,'')) IN ('UPCOMING','OPEN')
                           OR i.listing_date >= %s - %s
                           OR ii.open_date >= %s - %s
                           OR ii.close_date >= %s - %s)
                    ORDER BY COALESCE(ii.open_date,i.listing_date) DESC NULLS LAST,i.id""",
                (today, DIAGNOSTIC_LOOKBACK_DAYS, today, DIAGNOSTIC_LOOKBACK_DAYS,
                 today, DIAGNOSTIC_LOOKBACK_DAYS))
    return [IPOWindow(*row) for row in cur.fetchall()]


def _inside_target_window(ipo, today):
    listing_match = (ipo.listing_date is not None
                     and today - dt.timedelta(days=1) <= ipo.listing_date <= today)
    issue_match = (ipo.open_date is not None
                   and ipo.open_date <= today + dt.timedelta(days=1)
                   and (ipo.close_date or today) >= today - dt.timedelta(days=1))
    return listing_match or issue_match


def _exclusion_reasons(ipo, today, actions):
    reasons = []
    inside = _inside_target_window(ipo, today)
    if not inside: reasons.append("outside_window")
    if not ipo.symbol: reasons.append("missing_symbol")
    if not any((ipo.open_date, ipo.close_date, ipo.listing_date)):
        reasons.append("missing_dates")
    elif (ipo.open_date is None) != (ipo.close_date is None):
        reasons.append("incomplete_issue_dates")
    if ipo.listing_date == today - dt.timedelta(days=1) and not actions:
        reasons.append("historical_listing_buffer")
    if (inside and not actions and ipo.issue_complete and ipo.anchor_banked
            and ipo.final_subscription_banked):
        reasons.append("already_complete")
    return reasons


def build_diagnostics(candidates, today):
    """Return stable JSON diagnostics without network, writes, or R2 access."""
    counts = {key: 0 for key in ("eligible_candidates", "missing_symbol", "missing_dates",
        "already_complete", "outside_window", "planned_issue",
        "planned_subscription_forward", "planned_subscription_final", "planned_anchor",
        "planned_preopen")}
    rows = []
    action_counts = {"nse_issue_metadata": "planned_issue",
                     "subscription_forward": "planned_subscription_forward",
                     "subscription_final": "planned_subscription_final",
                     "anchor_discovery": "planned_anchor",
                     "preopen_capture": "planned_preopen"}
    for plan in plan_run(candidates, today):
        ipo = plan.ipo
        inside = _inside_target_window(ipo, today)
        actions = list(plan.actions) if inside else []
        reasons = _exclusion_reasons(ipo, today, actions)
        counts["eligible_candidates"] += int(inside)
        counts["missing_symbol"] += int(not ipo.symbol)
        counts["missing_dates"] += int(not any((ipo.open_date, ipo.close_date, ipo.listing_date)))
        counts["outside_window"] += int(not inside)
        counts["already_complete"] += int("already_complete" in reasons)
        for action in actions: counts[action_counts[action]] += 1
        rows.append({"ipo_id": ipo.ipo_id, "name": ipo.name, "symbol": ipo.symbol,
            "open_date": ipo.open_date, "close_date": ipo.close_date,
            "listing_date": ipo.listing_date, "issue_complete": ipo.issue_complete,
            "anchor_banked": ipo.anchor_banked,
            "final_subscription_banked": ipo.final_subscription_banked,
            "planned_actions": actions,
            "exclusion_reason": reasons or None})
    return {"aggregate_counts": counts, "candidates": rows}


def _absolute_url(url):
    if url.startswith("//"): return "https:" + url
    if url.startswith("/"): return "https://www.nseindia.com" + url
    return url


def run(conn, session, plans, *, write, db_target_queries=1):
    metrics = {"nse_calls": 0, "db_target_queries": db_target_queries,
               "db_write_operations": 0,
               "r2_puts": 0, "preopen_runs": 0, "ipos": []}
    preopen = False
    for plan in plans:
        item = {"ipo_id": plan.ipo.ipo_id, "symbol": plan.ipo.symbol,
                "actions": list(plan.actions), "results": []}
        payload = None
        nse_actions = set(plan.actions) & {"nse_issue_metadata", "subscription_forward",
                                           "subscription_final", "anchor_discovery"}
        try:
            if nse_actions:
                payload = fetch_one(session, plan.ipo.symbol.upper())
                metrics["nse_calls"] += 1
            if write and ({"nse_issue_metadata", "subscription_forward", "subscription_final"} & nse_actions):
                rep = apply_to_db(conn, plan.ipo.ipo_id, payload,
                                  subscription_final="subscription_final" in plan.actions,
                                  apply_issue="nse_issue_metadata" in plan.actions,
                                  apply_subscription=bool({"subscription_forward", "subscription_final"}
                                                          & set(plan.actions)))
                metrics["db_write_operations"] += int(bool(rep["issue_fields"])) + int(rep["subs_action"].startswith("inserted"))
                item["results"].append(rep["subs_action"])
            if "anchor_discovery" in plan.actions:
                url = _find_anchor_url(payload)
                if url:
                    item["results"].append("anchor_url_found")
                    if write:
                        response = session.get(_absolute_url(url), timeout=20)
                        if response.status_code != 200: raise RuntimeError(f"anchor PDF HTTP {response.status_code}")
                        issue, extras, _ = parse_issue_info(payload)
                        stored = store_document(conn, ipo_id=plan.ipo.ipo_id,
                            isin=extras.get("isin"), doc_type="anchor",
                            document_date=plan.ipo.open_date or dt.date.today(),
                            source_url=_absolute_url(url), content=response.content)
                        metrics["r2_puts"] += int(stored.created)
                        metrics["db_write_operations"] += 1
                        item["results"].append("anchor_ledger_verified")
                else: item["results"].append("anchor_not_available")
            preopen = preopen or "preopen_capture" in plan.actions
        except Exception as exc:
            conn.rollback()
            item["results"].append(f"failed:{type(exc).__name__}:{str(exc)[:100]}")
        metrics["ipos"].append(item)
        if nse_actions: time.sleep(2.5)
    if preopen and write:
        capture_script = os.path.join(os.path.dirname(__file__), "capture_preopen.py")
        proc = subprocess.run([sys.executable, capture_script], capture_output=True,
                              text=True, timeout=600)
        metrics["preopen_runs"] = 1
        metrics["preopen_status"] = proc.returncode
    return metrics


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--today", type=dt.date.fromisoformat)
    args = ap.parse_args()
    if not (args.write or args.dry_run): raise SystemExit("choose --write or --dry-run")
    import psycopg2
    from curl_cffi import requests as cffi
    today = args.today or dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    targets = _targets(conn, today, args.limit)
    if args.dry_run:
        print(json.dumps({"lifecycle_diagnostics": build_diagnostics(
            _diagnostic_candidates(conn, today), today)}, default=str, indent=2, sort_keys=True))
    plans = plan_run(targets, today)
    metrics = run(conn, prime(cffi), plans, write=args.write,
                  db_target_queries=2 if args.dry_run else 1)
    conn.close(); print(json.dumps(metrics, default=str, indent=2, sort_keys=True))
    failed = any(any(str(result).startswith("failed:") for result in ipo["results"])
                 for ipo in metrics["ipos"])
    if failed or metrics.get("preopen_status", 0) != 0:
        raise SystemExit(1)


if __name__ == "__main__": main()
