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
import urllib.parse
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


def structured_objects(output):
    """Decode JSON objects embedded in a child's otherwise human-readable output.

    Scans for objects wherever they appear rather than requiring one per line. The
    line-based twin this replaces demanded that the publication record be ALONE on its
    line and called .get() on whatever json.loads returned, so a shared line — a cmd.exe
    banner, an npm notice, or a bare scalar — turned a SUCCESSFUL publication into "the
    publication response omitted canonical ipo-command:v6", and a non-dict turned it into
    an AttributeError. Same discipline as cron.structured_objects, which the orchestrator
    already uses to read this very process's output; the two are pinned to agree by
    pipeline/test_snapshot_publication.py.
    """
    decoder = json.JSONDecoder()
    objects = []
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            objects.append(value)
    return objects


def publication_versions(output):
    published = {}
    for value in structured_objects(output or ""):
        if value.get("stage") == "publication":
            published.update(value.get("published") or {})
    return published


def prove_active_consumer(output, versions=None):
    versions = publication_versions(output) if versions is None else versions
    expected = versions.get("ipo-command:v6")
    if not expected:
        raise RuntimeError("publication response omitted canonical ipo-command:v6 version")
    origin = os.environ["SNAPSHOT_PUBLISH_URL"]
    parsed = urllib.parse.urlsplit(origin)
    endpoint = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/api/ipo-command", "", ""))
    response = urllib.request.urlopen(endpoint, timeout=30)
    active = response.headers.get("x-snapshot-version")
    rollback = response.headers.get("x-snapshot-rollback")
    if active != expected or rollback:
        raise RuntimeError("active snapshot pointer did not resolve to the published Command version")
    proof = {"snapshots_published": len(versions), "active_version": active,
             "consumer_source": "active", "canonical_snapshot": "ipo-command:v6"}
    print(json.dumps({"SNAPSHOT_CONSUMER_PROOF": proof}, sort_keys=True))
    return proof


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
        "phase": "config",
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
        record["phase"] = "builder"
        # errors="replace" and an explicit codec: the builder's stream is mixed on
        # Windows (Node speaks UTF-8, the cmd.exe launcher speaks the console code page),
        # and a step that has already published 16 keys must never be failed by a byte it
        # could not decode. cron.run() decodes THIS process the same way.
        completed = subprocess.run([sys.executable, str(HERE / "warm_kv.py")], check=True, cwd=ROOT,
                                   capture_output=True, encoding="utf-8", errors="replace")
        if completed.stdout: print(completed.stdout, end="")
        if completed.stderr: print(completed.stderr, end="", file=sys.stderr)
        # Publication is done at this point; everything below only PROVES it. Record what
        # actually went live before running the proof, so the ledger describes reality
        # even when the proof itself fails.
        record["phase"] = "publication-proof"
        published = publication_versions(completed.stdout or "")
        record["published_snapshots"] = len(published)
        record["last_known_good_kv_remains_active"] = not published
        proof = prove_active_consumer(completed.stdout or "", published)
        record.update({"status": "ok", "alert_status": "NOT_REQUIRED", "consumer_proof": proof})
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
