#!/usr/bin/env python3
"""Publish route snapshots and record the outcome for the workflow run artifact."""
import json
import subprocess
import sys
import time
from pathlib import Path

started = time.time()
record = {"step": "snapshot build/publication", "status": "running", "started_at_epoch": started}
ledger = Path("snapshot_publication_ledger.json")
try:
    subprocess.run([sys.executable, "warm_kv.py"], check=True)
    record.update({"status": "ok"})
except subprocess.CalledProcessError as exc:
    record.update({"status": "failed", "returncode": exc.returncode})
    raise
finally:
    record["duration_seconds"] = round(time.time() - started, 3)
    ledger.write_text(json.dumps(record, indent=2) + "\n")
