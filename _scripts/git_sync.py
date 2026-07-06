#!/usr/bin/env python3
"""git_sync.py — sync the VM working copy to origin/main, from the Admin console.
Whitelisted as job 'sync'. Prints old->new HEAD so the console log shows what moved."""
import subprocess, os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def run(*a):
    return subprocess.run(a, cwd=REPO, capture_output=True, text=True).stdout.strip()
old = run("git", "rev-parse", "--short", "HEAD")
print(run("git", "fetch", "origin", "main"))
print(run("git", "reset", "--hard", "origin/main"))
new = run("git", "rev-parse", "--short", "HEAD")
print(f"SYNCED {old} -> {new}")
