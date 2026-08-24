#!/usr/bin/env python3
"""Official NSE discovery + issue/subscription lane for the D1 write plane.

Identity remains ISIN -> exact name_norm.  Symbol is routing metadata only.  The parser is
reused from nse_fetch.py; only persistence changes from Postgres to the authenticated D1
Worker.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
from collections import defaultdict

from curl_cffi import requests as cffi

from d1_ingest import D1IngestClient, fingerprint
from fill_ipo import _norm
from nse_fetch import fetch_discovery, fetch_one, parse_bid_details, parse_issue_info, prime


def _date(value):
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.date().isoformat() if isinstance(value, dt.datetime) else value.isoformat()
    return str(value)[:10]


def _status(row: dict) -> str:
    today = dt.date.today()
    listing = dt.date.fromisoformat(_date(row.get("listing_date"))) if row.get("listing_date") else None
    open_d = dt.date.fromisoformat(_date(row.get("open_date"))) if row.get("open_date") else None
    close_d = dt.date.fromisoformat(_date(row.get("close_date"))) if row.get("close_date") else None
    if listing and listing <= today:
        return "LISTED"
    if open_d and close_d:
        if open_d <= today <= close_d:
            return "OPEN"
        if today > close_d:
            return "CLOSED"
        return "UPCOMING"
    return "ANNOUNCED"


def _issue_fields(issue: dict, extras: dict) -> dict:
    out = {
        "open_date": _date(issue.get("open_date")), "close_date": _date(issue.get("close_date")),
        "listing_date": _date(extras.get("listing_date")),
        "band_lo_rs": issue.get("band_lo"), "band_hi_rs": issue.get("band_hi"),
        "face_value_rs": issue.get("face_value"), "lot_size_shares": issue.get("lot_size"),
        "issue_size_cr": issue.get("issue_size_cr"), "fresh_cr": issue.get("fresh_cr"),
        "ofs_cr": issue.get("ofs_cr"), "registrar_name": issue.get("registrar"),
    }
    if extras.get("brlm_names"):
        names = [x.strip() for x in re.split(r",|\s+and\s+", str(extras["brlm_names"]), flags=re.I) if x.strip()]
        out["brlm_json"] = names
    return {k: v for k, v in out.items() if v is not None}


def _subscription_ops(ipo_id: int, subs: dict, *, captured_at: str, final: bool):
    # An all-zero table means NSE has not reported demand yet. Never store it as zero demand.
    meaningful = any((subs.get(k) or 0) > 0 for k in
                     ("qib_x", "nii_x", "bnii_x", "snii_x", "retail_x", "total_x", "mf_shares_bid"))
    if not meaningful:
        return []
    ops = []
    for source_key, category in (
        ("qib_x", "QIB"), ("nii_x", "NII"), ("bnii_x", "BNII"),
        ("snii_x", "SNII"), ("retail_x", "RETAIL"), ("total_x", "TOTAL"),
    ):
        if subs.get(source_key) is None:
            continue
        fp = fingerprint("nse-sub", ipo_id, captured_at, category, subs[source_key], final)
        ops.append({"op": "subscription_insert", "ipo_id": ipo_id, "captured_at": captured_at,
                    "category": category, "subscription_x": subs[source_key], "is_final": final,
                    "observation_fingerprint": fp})
    if subs.get("mf_shares_bid") is not None:
        fp = fingerprint("nse-sub", ipo_id, captured_at, "MF", subs["mf_shares_bid"], final)
        ops.append({"op": "subscription_insert", "ipo_id": ipo_id, "captured_at": captured_at,
                    "category": "MF", "shares_bid": int(subs["mf_shares_bid"]), "is_final": final,
                    "observation_fingerprint": fp})
    return ops


def run(*, limit: int = 20, apply: bool = False, client: D1IngestClient | None = None):
    client = client or D1IngestClient.from_env()
    s = prime(cffi)
    discovered, calls, errors = fetch_discovery(s)
    discovered = discovered[:limit]
    report = {"discovery_http_calls": calls, "discovery_errors": errors,
              "discovered": len(discovered), "spine_created": 0, "detail_fetched": 0,
              "issue_upserts": 0, "subscription_rows": 0, "failures": []}

    targets = []
    for row in discovered:
        name_norm = _norm(row["name"])
        op = {"op": "spine_upsert", "isin": row.get("isin"), "name": row["name"],
              "name_norm": name_norm, "nse_symbol": row.get("symbol"), "security_kind": "EQUITY",
              "status": _status(row), "discovered_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            if apply:
                result = client.op(op)
                ipo_id = int(result["ipo_id"])
                report["spine_created"] += int(bool(result.get("created")))
                issue = {k: v for k, v in {
                    "open_date": _date(row.get("open_date")), "close_date": _date(row.get("close_date")),
                    "listing_date": _date(row.get("listing_date")), "band_lo_rs": row.get("band_lo"),
                    "band_hi_rs": row.get("band_hi"), "lot_size_shares": row.get("lot_size"),
                    "issue_size_cr": row.get("issue_size_cr")}.items() if v is not None}
                if issue:
                    client.op({"op": "issue_upsert", "ipo_id": ipo_id, "fields": issue,
                               "source_name": "nse-discovery", "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            else:
                existing = client.resolve_identity(isin=row.get("isin"), name_norm=name_norm)
                ipo_id = int(existing["id"]) if existing else 0
            if ipo_id and row.get("symbol"):
                targets.append((ipo_id, row))
        except Exception as exc:
            report["failures"].append({"name": row.get("name"), "stage": "discovery", "error": f"{type(exc).__name__}:{exc}"})

    # Also include D1's current active spine so a temporary NSE discovery omission cannot
    # starve details/subscription refresh for an already-known issue.
    seen = {ipo_id for ipo_id, _ in targets}
    for row in client.active_ipos(limit=limit, lookback_days=100):
        if int(row["id"]) not in seen and row.get("nse_symbol"):
            targets.append((int(row["id"]), {
                "name": row["name"], "symbol": row["nse_symbol"], "isin": row.get("isin"),
                "open_date": row.get("open_date"), "close_date": row.get("close_date"),
                "listing_date": row.get("listing_date"),
            }))
            seen.add(int(row["id"]))
        if len(targets) >= limit:
            break

    for ipo_id, row in targets:
        try:
            payload = fetch_one(s, str(row["symbol"]).upper())
            report["detail_fetched"] += 1
            issue, extras, notes = parse_issue_info(payload)
            fields = _issue_fields(issue, extras)
            if apply and fields:
                client.op({"op": "issue_upsert", "ipo_id": ipo_id, "fields": fields,
                           "source_name": "nse", "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
                report["issue_upserts"] += 1
            if apply and extras.get("industry"):
                client.op({"op": "company_profile_upsert", "ipo_id": ipo_id, "industry": extras["industry"]})
            if apply and extras.get("isin"):
                # Resolve through the same exact name_norm; this only fills a NULL ISIN.
                client.op({"op": "spine_upsert", "isin": extras["isin"], "name": row["name"],
                           "name_norm": _norm(row["name"]), "nse_symbol": row.get("symbol"),
                           "status": _status({**row, "listing_date": extras.get("listing_date") or row.get("listing_date")}),
                           "security_kind": "EQUITY"})
            subs = parse_bid_details(payload)
            close_d = issue.get("close_date") or row.get("close_date")
            if isinstance(close_d, str):
                try: close_d = dt.date.fromisoformat(close_d[:10])
                except ValueError: close_d = None
            final = bool(close_d and close_d <= dt.date.today())
            captured = dt.datetime.now(dt.timezone.utc).isoformat()
            subops = _subscription_ops(ipo_id, subs, captured_at=captured, final=final)
            if apply and subops:
                client.batch(subops)
                report["subscription_rows"] += len(subops)
            if notes:
                report.setdefault("notes", []).append({"ipo_id": ipo_id, "notes": notes})
        except Exception as exc:
            report["failures"].append({"ipo_id": ipo_id, "stage": "detail", "error": f"{type(exc).__name__}:{exc}"})
        time.sleep(2.5)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    rep = run(limit=max(1, min(args.limit, 100)), apply=args.apply)
    print("D1_NSE_SUMMARY=" + json.dumps(rep, sort_keys=True, default=str))
    return 1 if rep["discovery_errors"] or rep["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
