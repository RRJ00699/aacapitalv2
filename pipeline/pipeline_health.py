#!/usr/bin/env python3
"""Build and publish the zero-wake pipeline-health:v1 snapshot."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request

import psycopg2

SNAPSHOT_NAME = "pipeline-health:v1"
EXPECTED_LEAN_STEPS = (
    "schema sync (single owner of DDL)", "write-constraint guard (A)",
    "lineage registry (P2)", "NSE discovery (new IPOs)",
    "IPOMatrix enrich (new IPOs)", "IPOMatrix refresh (upcoming drip-feed)",
    "EPS backfill (caution-marked)", "refresh GMP", "delivery pct (NSE bhavcopy)",
    "market regime + VIX (today)", "candles: in-window daily sync",
    "listing-day fields (kite)", "derive listing_open",
    "street news discovery (free RSS)", "d10 outcome precompute",
    "reconcile listing dates", "master computables backfill",
    "peer PE from SBI notes (fill-empty)", "peer PE (fetch, fair-value input)",
    "sync issue_details -> intelligence (isin)", "compute red-flag scanner",
    "sync trade journal (kite orders)", "compute journal outcomes",
    "backup critical tables", "purge post-lock candles", "health-check (gate)",
    "value-sanity report", "date sanity gate (D)", "freshness monitor (P2)",
    "smoke probe (live API)",
)
WEEKLY_STEPS = {"purge post-lock candles"}
SECRET_NAMES = ("DATABASE_URL", "NEON_DATABASE_URL", "SNAPSHOT_PUBLISH_KEY",
                "ANTHROPIC_API_KEY", "KITE_API_KEY", "KITE_API_SECRET")


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def redact(value, environ=None):
    text = str(value or "")
    environ = os.environ if environ is None else environ
    for name in SECRET_NAMES:
        secret = environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(postgres(?:ql)?://)[^\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)\b(token|password|secret|authorization|cookie)\s*[:=]\s*\S+",
                  r"\1=[REDACTED]", text)
    return text


def _status(ok, error):
    message = str(error or "").strip().lower()
    if not ok:
        return "failed"
    if message.startswith("skipped"):
        return "skipped"
    if message.startswith("dry"):
        return "dry"
    if message.startswith("partial") or "retry_required" in message:
        return "partial"
    return "ok"


def build_payload(step_rows, failure_rows, *, environ=None):
    """Convert the latest persisted lean run to the contracted, secret-safe shape."""
    steps = []
    for step, ok, error, ran_at in step_rows:
        safe_error = redact(error, environ)[:1000] or None
        steps.append({"step": str(step), "status": _status(ok, error),
                      "ran_at": _iso(ran_at), "duration_ms": 0,
                      "config_required": bool(safe_error and safe_error.lower().startswith("owner: configure")),
                      "error": safe_error})
    failures = []
    for step, tail, failed_at in failure_rows:
        bounded = "\n".join(redact(tail, environ).splitlines()[-12:])
        failures.append({"step": str(step), "stderr_tail": bounded[:6000],
                         "failed_at": _iso(failed_at)})
    last_run_at = max((row["ran_at"] for row in steps if row["ran_at"]), default=None)
    final_step = EXPECTED_LEAN_STEPS[-1].lower()
    run_complete = any(row["step"].strip().lower() == final_step for row in steps)
    return {"run_complete": run_complete, "last_run_at": last_run_at,
            "steps": steps,
            "expected": [{"step": step, "weekly": step in WEEKLY_STEPS}
                         for step in EXPECTED_LEAN_STEPS],
            "failures": failures}


def read_health(conn):
    cur = conn.cursor()
    cur.execute("""SELECT step,ok,error,ran_at FROM pipeline_steps
      WHERE run_date=(SELECT max(run_date) FROM pipeline_steps) ORDER BY id""")
    steps = cur.fetchall()
    cur.execute("""SELECT step,stderr_tail,failed_at FROM pipeline_failures
      WHERE failed_at::date=(SELECT max(run_date) FROM pipeline_steps)
      ORDER BY failed_at,id""")
    return steps, cur.fetchall()


def publication_endpoint(origin):
    parsed = urllib.parse.urlsplit(origin.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("snapshot publication URL is invalid")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/api/admin/snapshots", "", ""))


def publish(payload, *, environ=None, urlopen=urllib.request.urlopen):
    environ = os.environ if environ is None else environ
    origin = environ.get("SNAPSHOT_PUBLISH_URL", "").strip()
    key = environ.get("SNAPSHOT_PUBLISH_KEY", "").strip()
    if not origin or not key:
        return {"step": "pipeline health publication", "status": "skipped",
                "reason": "owner: configure snapshot publication"}
    request = urllib.request.Request(
        publication_endpoint(origin),
        data=json.dumps({"snapshots": [{"name": SNAPSHOT_NAME, "payload": payload}]}).encode(),
        headers={"content-type": "application/json", "x-aac-key": key}, method="POST")
    try:
        response = json.loads(urlopen(request, timeout=30).read())
    except Exception:
        return {"step": "pipeline health publication", "status": "failed",
                "reason": "pipeline health publication failed"}
    version = (response.get("published") or {}).get(SNAPSHOT_NAME)
    if not version:
        return {"step": "pipeline health publication", "status": "failed",
                "reason": "pipeline health active pointer was not confirmed"}
    return {"step": "pipeline health publication", "status": "ok",
            "version": str(version)}


def main():
    if not os.environ.get("SNAPSHOT_PUBLISH_URL") or not os.environ.get("SNAPSHOT_PUBLISH_KEY"):
        print(json.dumps({"step": "pipeline health publication", "status": "skipped",
                          "reason": "owner: configure snapshot publication"}, sort_keys=True))
        return 0
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=25,
                            keepalives=1, keepalives_idle=30,
                            keepalives_interval=10, keepalives_count=3)
    try:
        steps, failures = read_health(conn)
        result = publish(build_payload(steps, failures))
    finally:
        conn.close()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"ok", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
