#!/usr/bin/env python3
"""Publish route snapshots, record the outcome, and alert on failure."""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

FAILED_STEP = "snapshot build/publication"
LEDGER = Path("snapshot_publication_ledger.json")

def write_ledger(record):
    LEDGER.write_text(json.dumps(record, indent=2) + "\n")

def send_failure_alert(record):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("ntfy snapshot failure alert skipped: NTFY_TOPIC unset")
        return
    branch = os.environ.get("GITHUB_REF_NAME") or os.environ.get("GITHUB_REF", "unknown")
    sha = os.environ.get("GITHUB_SHA", "unknown")
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    timestamp = record["finished_at"]
    body = (
        f"AA Capital snapshot publication failed\n"
        f"workflow_run_id={run_id}\n"
        f"failed_step={FAILED_STEP}\n"
        f"timestamp={timestamp}\n"
        f"branch={branch}\n"
        f"commit_sha={sha}\n"
        f"last-known-good KV remains active"
    )
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode()[:900],
        headers={"Title": "AA Capital snapshot publication failed", "Priority": "high"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
        print("ntfy snapshot failure alert sent")
    except Exception as exc:
        print(f"ntfy snapshot failure alert failed: {type(exc).__name__}: {str(exc)[:120]}")

started = time.time()
record = {
    "step": FAILED_STEP,
    "status": "running",
    "started_at": dt.datetime.now(dt.UTC).isoformat(),
    "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
    "branch": os.environ.get("GITHUB_REF_NAME") or os.environ.get("GITHUB_REF"),
    "commit_sha": os.environ.get("GITHUB_SHA"),
    "last_known_good_kv_remains_active": True,
}
write_ledger(record)
try:
    subprocess.run([sys.executable, "warm_kv.py"], check=True)
    record.update({"status": "ok"})
except subprocess.CalledProcessError as exc:
    record.update({"status": "failed", "returncode": exc.returncode})
    raise
finally:
    record["finished_at"] = dt.datetime.now(dt.UTC).isoformat()
    record["duration_seconds"] = round(time.time() - started, 3)
    write_ledger(record)
    if record["status"] == "failed":
        send_failure_alert(record)
