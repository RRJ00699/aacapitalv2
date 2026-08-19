#!/usr/bin/env python3
"""Invoke the canonical TypeScript snapshot builder; no web request reads Neon."""
import argparse
import os
import shutil
import subprocess
import sys
from config import SNAPSHOT_DEFAULT_IPOS, SNAPSHOT_DEFAULT_CONCURRENCY

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_npx() -> str:
    """The npx launcher's full path, extension-qualified on Windows.

    shutil.which resolves against PATH and PATHEXT, so on Windows this is the absolute
    "C:\\Program Files\\nodejs\\npx.CMD" — a path with a space, and a BATCH file, which
    Windows re-parses through cmd.exe quoting rules. That combination is safe under
    exactly one construction: the path as its own element of a LIST argv with
    shell=False, never interpolated into a command string. build_command() returns that
    list and publish() passes it unmodified; the printed form is for humans only and is
    never what gets executed. Pinned by test_snapshot_publication.py.
    """
    exe = shutil.which("npx") or shutil.which("npx.cmd")
    if not exe:
        raise RuntimeError("npx executable not found on PATH; install Node dependencies or add npm's bin directory to PATH")
    return exe


def build_command(limit=SNAPSHOT_DEFAULT_IPOS, concurrency=SNAPSHOT_DEFAULT_CONCURRENCY, dry_run=False):
    cmd = [resolve_npx(), "tsx", "pipeline/build/build_snapshots.ts", f"--limit={limit}", f"--concurrency={concurrency}"]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def publish(limit=SNAPSHOT_DEFAULT_IPOS, concurrency=SNAPSHOT_DEFAULT_CONCURRENCY, dry_run=False):
    """Run the builder and re-emit everything it said, verbatim and decodable.

    The output is captured and re-printed rather than inherited, for two reasons.
    Decoding is pinned to UTF-8 with errors="replace" HERE, at the boundary where the
    bytes are actually mixed: the builder is Node (UTF-8) but the Windows launcher runs
    under cmd.exe, whose own notices and banners arrive in the console code page. A
    single such byte would otherwise reach the parent's strict decode and fail a
    publication that had already succeeded. And on failure the child's diagnostic is
    attached to the CalledProcessError instead of being lost — `check=True` without
    capture raises with stdout=None, which is how a real builder error reached the
    ledger as a bare "snapshot builder exited 1".
    """
    cmd = build_command(limit, concurrency, dry_run)
    print("snapshot builder command:", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True,
                               encoding="utf-8", errors="replace")
    if completed.stdout:
        print(completed.stdout, end="", flush=True)
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr, flush=True)
    if completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, cmd,
                                            output=completed.stdout, stderr=completed.stderr)
    return completed


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=SNAPSHOT_DEFAULT_IPOS); ap.add_argument("--concurrency",type=int,default=SNAPSHOT_DEFAULT_CONCURRENCY); ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args(); publish(a.limit,a.concurrency,a.dry_run)
