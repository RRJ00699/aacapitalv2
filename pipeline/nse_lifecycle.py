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
from nse_fetch import (DISCOVERY_APIS, apply_to_db, fetch_discovery, fetch_one,
                       parse_issue_info, prime)

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
                           OR ii.open_date <= %s + %s AND ii.close_date >= %s - 1)
                    ORDER BY COALESCE(i.listing_date,ii.open_date),i.id LIMIT %s""",
                (today, today, today, DIAGNOSTIC_LOOKBACK_DAYS, today, limit))
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
    issue_match = (ipo.open_date is not None and ipo.close_date is not None
                   and ipo.open_date <= today + dt.timedelta(days=DIAGNOSTIC_LOOKBACK_DAYS)
                   and ipo.close_date >= today - dt.timedelta(days=1))
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


def validate_diagnostic_superset(targets, diagnostics):
    target_ids = {ipo.ipo_id for ipo in targets}
    diagnostic_ids = {ipo.ipo_id for ipo in diagnostics}
    missing = sorted(target_ids - diagnostic_ids)
    if missing:
        raise RuntimeError(f"diagnostic contract violated; target ids missing: {missing}")


def _reconcile_discovery_batch(conn, discovered, *, write):
    """Resolve official identities and optionally fill canonical missing fields."""
    from fill_ipo import _norm, upsert_ipo
    from fill_v2 import upsert_ipo_issue
    report, overlays, writes, reads = [], [], 0, 0
    for row in discovered:
        cur = conn.cursor()
        hit = None
        if row.get("isin"):
            cur.execute("""SELECT id,name_display,name_norm,symbol,listing_date,isin
                             FROM ipo WHERE isin=%s LIMIT 1""", (row["isin"],))
            hit = cur.fetchone()
            reads += 1
        if not hit and row.get("symbol"):
            cur.execute("""SELECT id,name_display,name_norm,symbol,listing_date,isin
                             FROM ipo WHERE UPPER(symbol)=%s LIMIT 1""", (row["symbol"],))
            hit = cur.fetchone()
            reads += 1
        action = "matched_existing" if hit else "unresolved"
        ipo_id = hit[0] if hit else None
        sufficient_new = bool(row.get("isin"))
        if not hit and sufficient_new: action = "bootstrap_required"
        if hit and row.get("isin") and hit[5] and row["isin"] != hit[5]:
            raise ValueError("official ISIN conflicts with symbol-owned canonical IPO")
        if not hit and sufficient_new:
            cur.execute("SELECT id FROM ipo WHERE name_norm=%s LIMIT 1", (_norm(row["name"]),))
            reads += 1
            if cur.fetchone():
                raise ValueError("official ISIN has unresolved canonical name ownership")
        available_issue = {key: row.get(key) for key in
            ("open_date", "close_date", "band_lo", "band_hi", "lot_size", "issue_size_cr")
            if row.get(key) is not None}
        state = None
        if ipo_id:
            cur.execute("""SELECT ii.open_date,ii.close_date,ii.band_lo,ii.band_hi,
                    ii.lot_size,ii.issue_size_cr,
                    EXISTS(SELECT 1 FROM documents d WHERE d.ipo_id=%s AND d.doc_type='anchor'),
                    EXISTS(SELECT 1 FROM subscription_snapshots s WHERE s.ipo_id=%s AND s.is_final)
                FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id WHERE i.id=%s""",
                (ipo_id, ipo_id, ipo_id))
            state = cur.fetchone(); reads += 1
        issue_keys = ("open_date", "close_date", "band_lo", "band_hi", "lot_size", "issue_size_cr")
        issue_fields = {key: value for key, value in available_issue.items()
                        if state is None or state[issue_keys.index(key)] is None}
        spine_refresh = (not hit or (row.get("symbol") and not hit[3])
                         or (row.get("listing_date") and not hit[4])
                         or (row.get("isin") and not hit[5]))
        refresh = bool(issue_fields or spine_refresh)
        if write and (hit or sufficient_new):
            record = {"isin": row.get("isin"), "symbol": row.get("symbol"),
                      "name_display": hit[1] if hit else row["name"],
                      "name_norm": hit[2] if hit else _norm(row["name"]),
                      "listing_date": row.get("listing_date"), "is_mainboard": True,
                      "status": "announced"}
            spine_action = "unchanged"
            if spine_refresh:
                ipo_id, spine_action = upsert_ipo(conn, record, source="nse-discovery")
                writes += 1
            if issue_fields: upsert_ipo_issue(conn, ipo_id, issue_fields, source="nse-discovery")
            writes += int(bool(issue_fields)); action = spine_action
        if ipo_id:
            effective_complete = all(row.get(key) is not None or (state and state[idx] is not None)
                                     for key, idx in (("band_lo", 2), ("band_hi", 3),
                                                      ("lot_size", 4)))
            overlays.append(IPOWindow(ipo_id, row.get("symbol") or (hit[3] if hit else None),
                hit[1] if hit else row["name"],
                row.get("open_date") or (state[0] if state else None),
                row.get("close_date") or (state[1] if state else None),
                row.get("listing_date") or (hit[4] if hit else None), effective_complete,
                state[6] if state else False, state[7] if state else False))
        report.append({"name": row["name"], "isin": row.get("isin"),
            "symbol": row.get("symbol"), "resolution": action,
            "ipo_id": ipo_id, "metadata_refresh_required": refresh})
    return report, overlays, reads, writes


def reconcile_discovery(conn, discovered, *, write):
    """Isolate canonical resolution/refresh failures to one discovered IPO."""
    report, overlays, reads, writes = [], [], 0, 0
    for row in discovered:
        try:
            item_report, item_overlays, item_reads, item_writes = (
                _reconcile_discovery_batch(conn, [row], write=write))
            report.extend(item_report); overlays.extend(item_overlays)
            reads += item_reads; writes += item_writes
        except Exception as exc:
            conn.rollback()
            report.append({"name": row.get("name"), "isin": row.get("isin"),
                "symbol": row.get("symbol"), "resolution": "failed",
                "ipo_id": None, "metadata_refresh_required": False,
                "error": f"{type(exc).__name__}:{str(exc)[:100]}"})
    return report, overlays, reads, writes


def _absolute_url(url):
    if url.startswith("//"): return "https:" + url
    if url.startswith("/"): return "https://www.nseindia.com" + url
    return url


def run(conn, session, plans, *, write, db_target_queries=1):
    metrics = {"detail_http_calls": 0, "anchor_http_calls": 0,
               "db_target_queries": db_target_queries,
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
                metrics["detail_http_calls"] += 1
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
                        metrics["anchor_http_calls"] += 1
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


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--discovery-only", action="store_true",
                    help="refresh only the official canonical IPO universe")
    ap.add_argument("--today", type=dt.date.fromisoformat)
    args = ap.parse_args(argv)
    if not (args.write or args.dry_run): raise SystemExit("choose --write or --dry-run")
    import psycopg2
    from curl_cffi import requests as cffi
    today = args.today or dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    session = prime(cffi)
    discovered, discovery_calls, discovery_errors = fetch_discovery(session)
    discovery_total = len(discovered)
    discovered = discovered[:args.limit]
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    discovery_rows, overlays, discovery_reads, discovery_writes = ([], [], 0, 0)
    if not discovery_errors:
        discovery_rows, overlays, discovery_reads, discovery_writes = reconcile_discovery(
            conn, discovered, write=args.write)
    else:
        discovery_rows = [{"name": row["name"], "isin": row.get("isin"),
            "symbol": row.get("symbol"), "resolution": "not_reconciled_discovery_failure",
            "ipo_id": None, "metadata_refresh_required": False} for row in discovered]
    if args.discovery_only:
        output = {"DISCOVERY": {"official_source": [url for _, url in DISCOVERY_APIS],
            "feed_http_calls": discovery_calls, "returned_count": discovery_total,
            "processed_limit": args.limit, "errors": discovery_errors,
            "discovered_ipos": discovery_rows, "db_reads": discovery_reads,
            "db_writes": discovery_writes}}
        conn.close()
        print(json.dumps(output, default=str, indent=2, sort_keys=True))
        if discovery_errors or any(row["resolution"] == "failed" for row in discovery_rows):
            raise SystemExit(1)
        return output
    targets = _targets(conn, today, args.limit)
    diagnostic_candidates = _diagnostic_candidates(conn, today)
    validate_diagnostic_superset(targets, diagnostic_candidates)
    if args.dry_run:
        by_id = {ipo.ipo_id: ipo for ipo in diagnostic_candidates}
        by_id.update({ipo.ipo_id: ipo for ipo in overlays})
        diagnostic_candidates = list(by_id.values())
        targets = [ipo for ipo in diagnostic_candidates if _inside_target_window(ipo, today)][:args.limit]
    lifecycle_diagnostics = build_diagnostics(diagnostic_candidates, today)
    plans = plan_run(targets, today)
    metrics = run(conn, session, plans, write=args.write,
                  db_target_queries=2)
    output = {"DISCOVERY": {"official_source": [url for _, url in DISCOVERY_APIS],
              "session_prime_http_calls": 2, "feed_http_calls": discovery_calls,
              "returned_count": discovery_total, "processed_limit": args.limit,
              "errors": discovery_errors,
              "discovered_ipos": discovery_rows,
              "matched_existing": sum(r["resolution"] == "matched_existing" for r in discovery_rows),
              "new_or_unresolved": sum(r["resolution"] in ("bootstrap_required", "unresolved") for r in discovery_rows),
              "metadata_refresh_required": sum(r["metadata_refresh_required"] for r in discovery_rows)},
              "LIFECYCLE": lifecycle_diagnostics,
              "OPERATIONS": {**metrics, "discovery_db_reads": discovery_reads,
                             "discovery_db_writes": discovery_writes,
                             "r2_writes": metrics["r2_puts"]}}
    conn.close(); print(json.dumps(output, default=str, indent=2, sort_keys=True))
    failed = any(any(str(result).startswith("failed:") for result in ipo["results"])
                 for ipo in metrics["ipos"])
    if discovery_errors or failed or metrics.get("preopen_status", 0) != 0:
        raise SystemExit(1)


if __name__ == "__main__": main()
