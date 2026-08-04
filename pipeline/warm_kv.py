#!/usr/bin/env python3
"""Invoke the canonical TypeScript snapshot builder; no web request reads Neon."""
import argparse, os, subprocess
from config import SNAPSHOT_DEFAULT_IPOS, SNAPSHOT_DEFAULT_CONCURRENCY

def publish(limit=SNAPSHOT_DEFAULT_IPOS, concurrency=SNAPSHOT_DEFAULT_CONCURRENCY, dry_run=False):
    cmd = ["npx", "tsx", "pipeline/build/build_snapshots.ts", f"--limit={limit}", f"--concurrency={concurrency}"]
    if dry_run: cmd.append("--dry-run")
    subprocess.run(cmd, check=True, cwd=os.path.dirname(os.path.dirname(__file__)))

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=SNAPSHOT_DEFAULT_IPOS); ap.add_argument("--concurrency",type=int,default=SNAPSHOT_DEFAULT_CONCURRENCY); ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args(); publish(a.limit,a.concurrency,a.dry_run)
