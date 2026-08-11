#!/usr/bin/env python3
"""Publish route snapshots, record the outcome, and alert on failure."""
import datetime as dt
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

FAILED_STEP = "snapshot build/publication"
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "snapshot_publication_ledger.json"
ROOT = HERE.parent


def write_ledger(record):
    LEDGER.write_text(json.dumps(record, indent=2) + "\n")


def github_warning(message: str):
    print(f"::warning::{message}")


def send_failure_alert(record):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        record["alert_status"] = "NOT_CONFIGURED"
        msg = "ntfy snapshot failure alert skipped: NTFY_TOPIC unset"
        print(msg)
        github_warning("NTFY_TOPIC is not configured; snapshot publication failure alert was not sent")
        return
    record["alert_status"] = "ATTEMPTED"
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
        record["alert_status"] = "SENT"
        print("ntfy snapshot failure alert sent")
    except Exception as exc:
        record["alert_status"] = "FAILED"
        record["alert_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        print(f"ntfy snapshot failure alert failed: {record['alert_error']}")


def missing_required_config():
    missing = []
    for name in ("SNAPSHOT_PUBLISH_URL", "SNAPSHOT_PUBLISH_KEY"):
        if not os.environ.get(name, "").strip():
            missing.append(name)
    return missing


def main(argv=()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        # Consumer-proof path without a ledger write or publication.  warm_kv passes
        # this through to the canonical builder, which validates selectors/config.
        return subprocess.run(
            [sys.executable, str(HERE / "warm_kv.py"), "--dry-run"],
            cwd=ROOT,
        ).returncode
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
        missing = missing_required_config()
        if missing:
            raise RuntimeError("missing required snapshot publication configuration: " + ", ".join(missing))
        completed = subprocess.run([sys.executable, str(HERE / "warm_kv.py")], check=True, cwd=ROOT,
                                   text=True, capture_output=True)
        if completed.stdout: print(completed.stdout, end="")
        if completed.stderr: print(completed.stderr, end="", file=sys.stderr)
        record.update({"status": "ok", "alert_status": "NOT_REQUIRED"})
        return 0
    except subprocess.CalledProcessError as exc:
        if exc.stdout: print(exc.stdout, end="")
        if exc.stderr: print(exc.stderr, end="", file=sys.stderr)
        record.update({"status": "failed", "returncode": exc.returncode, "error": f"snapshot builder exited {exc.returncode}"})
        for line in reversed((exc.stderr or "").splitlines() + (exc.stdout or "").splitlines()):
            try:
                diagnostic = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            if diagnostic.get("stage") == "details-publication":
                record["details_batch"] = diagnostic.get("details_batch")
                record["failing_isins"] = diagnostic.get("failing_isins")
                break
        return exc.returncode or 1
    except Exception as exc:
        record.update({"status": "failed", "returncode": 1, "error": str(exc)})
        return 1
    finally:
        record["finished_at"] = dt.datetime.now(dt.UTC).isoformat()
        record["duration_seconds"] = round(time.time() - started, 3)
        if record["status"] == "failed":
            send_failure_alert(record)
        write_ledger(record)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
