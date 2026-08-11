#!/usr/bin/env python3
"""Supported daily pipeline entry point for Windows and CI-safe dry runs."""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psycopg2

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
SCRIPTS_DIR = REPO_ROOT / "_scripts"
TEMP_ROOT = Path(os.environ.get("RUNNER_TEMP", REPO_ROOT / ".tmp")).resolve()
SBI_DIR = TEMP_ROOT / "sbi-notes"
ACTIVE_DAYS = 90
DOC_FRESH_DAYS = 30
DEFAULT_CAP = 2.0
# The protected publisher below invokes the one canonical producer: "warm_kv.py"

KITE_REFRESH_STATUS_TO_STEP = {
    "SUCCESS_ROTATED": "ok", "SUCCESS_VALIDATED_ONLY": "ok",
    "SKIPPED_NOT_ACTIVATED": "skipped", "FAILED_LOGIN": "failed",
    "FAILED_ROTATION": "failed", "FAILED_VERIFICATION": "failed",
}

ENVIRONMENT = (
    ("DATABASE_URL", "all database selectors and writers", "required; pipeline stops"),
    ("R2_ACCOUNT_ID", "SBI/R2 ingest", "owner: configure the SBI/R2 lane"),
    ("R2_ACCESS_KEY_ID", "SBI/R2 ingest", "owner: configure the SBI/R2 lane"),
    ("R2_SECRET_ACCESS_KEY", "SBI/R2 ingest", "owner: configure the SBI/R2 lane"),
    ("R2_DOCUMENT_BUCKET", "SBI/R2 ingest", "owner: configure the SBI/R2 lane"),
    ("SBI_OWNER_APPROVED", "SBI/R2 production writes", "owner: approve SBI ingest"),
    ("ANTHROPIC_API_KEY", "SBI and RHP paid extraction", "owner: configure and approve paid lanes"),
    ("KITE_API_KEY", "Kite refresh/candles", "owner: configure Kite"),
    ("KITE_API_SECRET", "Kite refresh/candles", "owner: configure Kite"),
    ("KITE_USER_ID", "Kite refresh", "owner: configure Kite"),
    ("KITE_PASSWORD", "Kite refresh", "owner: configure Kite"),
    ("KITE_TOTP_SECRET", "Kite refresh", "owner: configure Kite"),
    ("KITE_BROKER_PROXY_URL", "Kite token verification", "owner: configure Kite broker proxy"),
    ("KITE_BROKER_PROXY_AUTH_SECRET", "Kite token verification", "owner: configure Kite broker proxy"),
    ("SNAPSHOT_PUBLISH_URL", "snapshot publication", "owner: configure snapshot publication"),
    ("SNAPSHOT_PUBLISH_KEY", "snapshot publication", "owner: configure snapshot publication"),
    ("NTFY_TOPIC", "failure notification", "owner: configure notifications (optional)"),
)


def _utf8_console() -> None:
    if __name__ == "__main__":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def environment_preflight(environ=None) -> bool:
    """Print names and classifications only; never interpolate secret values."""
    environ = os.environ if environ is None else environ
    print("STEP 0 - ENVIRONMENT PREFLIGHT")
    print(f"{'variable':34} {'state':7} {'required by':30} effect of absence")
    print("-" * 112)
    for name, consumers, effect in ENVIRONMENT:
        print(f"{name:34} {'present' if environ.get(name) else 'absent':7} {consumers:30} {effect}")
    if not environ.get("DATABASE_URL"):
        print("STOP: required environment variable absent: DATABASE_URL")
        return False
    return True


def db():
    return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=25,
                            keepalives=1, keepalives_idle=30,
                            keepalives_interval=10, keepalives_count=3)


def with_db(fn, *args, **kwargs):
    conn = db()
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


def get_cap(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM platform_config WHERE key='daily_spend_cap_usd'")
        row = cur.fetchone()
        return float(row[0]) if row and row[0] else DEFAULT_CAP
    except Exception:
        conn.rollback()
        return DEFAULT_CAP


def spent_today(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM rhp_findings WHERE analyzed_at >= date_trunc('day', now())")
        return float(cur.fetchone()[0] or 0)
    except Exception:
        conn.rollback()
        return 0.0


def select_active(conn, limit, backfill=False):
    cur = conn.cursor()
    if backfill:
        cur.execute("""SELECT id,name_display,listing_date FROM ipo
                       WHERE in_backtest_universe=TRUE AND COALESCE(is_mainboard,TRUE)=TRUE
                       ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (limit,))
        return cur.fetchall(), "BACKFILL (most recently listed)"
    cur.execute("""SELECT i.id,i.name_display,i.listing_date FROM ipo i
      LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id
      WHERE COALESCE(i.is_mainboard,TRUE)=TRUE AND COALESCE(ii.issue_size_cr,999999)>=150
      AND ((i.listing_date IS NOT NULL AND i.listing_date>=current_date-%s)
        OR (i.listing_date IS NULL AND (ii.close_date>=current_date-30
          OR ii.open_date>=current_date-30 OR EXISTS
          (SELECT 1 FROM documents d WHERE d.ipo_id=i.id
           AND d.fetched_at>=now()-(%s||' days')::interval))))
      ORDER BY COALESCE(i.listing_date,current_date+365) DESC LIMIT %s""",
                (ACTIVE_DAYS, DOC_FRESH_DAYS, limit))
    return cur.fetchall(), f"ACTIVE (unlisted, or listed within {ACTIVE_DAYS}d)"


def script(relative: str) -> Path:
    return (REPO_ROOT / relative).resolve()


def skip(step, reason, *, counts=None):
    print(f"\n=== {step}\n    skipped - {reason}")
    return {"step": step, "status": "skipped", "duration": 0.0,
            "reason": reason, "counts": counts or {}}


def run(step, script_path, args, *, dry=False, timeout=1800, required=True, cwd=None):
    """Execute a Python file using an absolute path and an explicit working directory."""
    started = time.monotonic()
    path = Path(script_path).resolve()
    print(f"\n=== {step}")
    if not path.is_file():
        status = "failed" if required else "skipped"
        reason = f"required script absent: {path}" if required else f"owner: install optional script {path.name}"
        print(f"    {status} - {reason}")
        return {"step": step, "status": status, "duration": time.monotonic()-started, "reason": reason}
    cmd = [sys.executable, str(path), *map(str, args)]
    print("    $ " + " ".join(cmd))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        proc = subprocess.run(cmd, cwd=str((cwd or REPO_ROOT).resolve()), env=env,
                              capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"step": step, "status": "failed", "duration": time.monotonic()-started,
                "reason": f"timeout after {timeout}s"}
    for line in (proc.stdout or "").splitlines()[-30:]:
        print("    " + line)
    if proc.returncode:
        detail = (proc.stderr or "").strip().splitlines()[-1:] or [f"exit {proc.returncode}"]
        print("    failed - " + detail[0][:300])
        return {"step": step, "status": "failed", "duration": time.monotonic()-started,
                "reason": detail[0][:300], "rc": proc.returncode}
    return {"step": step, "status": "dry" if dry else "ok",
            "duration": time.monotonic()-started, "output": proc.stdout or ""}


def configured(names):
    missing = [name for name in names if not os.environ.get(name)]
    return not missing, missing


def classify_kite_refresh(returncode, output):
    matches = [line.split("=", 1)[1].strip() for line in output.splitlines()
               if line.startswith("KITE_REFRESH_STATUS=")]
    if len(matches) != 1 or matches[0] not in KITE_REFRESH_STATUS_TO_STEP:
        return ("failed" if returncode else "ok"), None
    value = matches[0]
    status = KITE_REFRESH_STATUS_TO_STEP[value]
    if returncode != (1 if status == "failed" else 0):
        return "failed", value
    return status, value


def classify_sbi_configuration(config):
    """Keep the SBI worker's typed configuration states visible to the orchestrator."""
    return {"SKIPPED_OWNER_NOT_CONFIGURED": "skipped",
            "WARNING_CONFIGURATION_ERROR": "warning"}.get(config.status, "configured")


def report(steps, started, *, dry, targets, cap=0.0, spent=0.0):
    duration = time.monotonic() - started
    failed = [s for s in steps if s["status"] == "failed"]
    total = "failed" if failed else ("dry" if dry else "ok")
    print("\n" + "=" * 72)
    print("END-OF-RUN REPORT")
    print(f"total status: {total} | runtime: {duration:.1f}s | active IPOs: {len(targets)}")
    for item in steps:
        why = f" | {item['reason']}" if item.get("reason") else ""
        print(f"{item['status']:7} {item['duration']:7.1f}s  {item['step']}{why}")
    print("what changed: " + ("none (read-only dry-run)" if dry else "see per-step counts above"))
    print("NSE discovery: counts are printed by the discovery step")
    print("discovery identity: matched/created/bounded counts are printed by identity backfill")
    print("ISIN/listing-date backfill: counts are printed by identity backfill")
    print("SBI ingest/extraction: summary is printed by the SBI step or its skip reason")
    snapshot = next((s for s in steps if s["step"].startswith("snapshot publication")), None)
    print("snapshot pointer/consumer proof: " +
          ("verified by publish_snapshot_with_ledger output" if snapshot and snapshot["status"] == "ok"
           else (snapshot.get("reason", snapshot["status"]) if snapshot else "not run")))
    print(f"paid calls: {'0 (dry-run)' if dry else f'bounded by ${cap:.2f}; measured ${spent:.3f}'}")
    print(f"production writes: {'0 (dry-run)' if dry else 'authorized by this live command; see steps'}")
    actions = [s["reason"] for s in steps if s.get("reason", "").startswith("owner:")]
    print("owner actions still required: " + ("; ".join(actions) if actions else "none"))
    print("=" * 72)
    return 1 if failed else 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true", help="backward-compatible live alias")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--skip-rhp-download", action="store_true")
    ap.add_argument("--skip-kite", action="store_true")
    ap.add_argument("--max-rhps", type=int, default=4)
    ap.add_argument("--ignore-local", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    _utf8_console()
    args = parse_args(argv)
    dry = args.dry_run
    started = time.monotonic()
    if not environment_preflight():
        return 2
    steps = []

    # Downloads are intentionally skipped in dry mode: they are external writes.
    if dry or args.skip_download or args.skip_rhp_download:
        steps.append(skip("SEBI RHP download", "dry-run: external download disabled" if dry else "owner: command-line download skip"))
    else:
        steps.append(run("SEBI RHP download", SCRIPTS_DIR / "download_sebi_rhps_playwright.py",
                         ["--max", args.max_rhps], timeout=2400))
    if dry or args.skip_download:
        steps.append(skip("SBI note download", "dry-run: external download disabled" if dry else "owner: command-line download skip"))
    else:
        steps.append(run("SBI note download", SCRIPTS_DIR / "download_sbi_notes.py",
                         ["--out", SBI_DIR], timeout=1200))

    # Structural lane handshake: 2c. NSE discovery -> 2d. bounded NSE identity ->
    # 2e/2f. SBI ingest -> 3. NSE per-IPO lifecycle.
    steps.append(run("NSE discovery", PIPELINE_DIR / "nse_lifecycle.py",
                     ["--discovery-only", "--limit", args.limit, "--max-new-rows", 10,
                      "--dry-run" if dry else "--write"], dry=dry, timeout=300, cwd=PIPELINE_DIR))
    steps.append(run("NSE identity/ISIN/listing-date backfill", PIPELINE_DIR / "nse_identity_backfill.py",
                     ["--limit", args.limit, "--quote-limit", args.limit,
                      "--dry-run" if dry else "--write"], dry=dry, timeout=300, cwd=PIPELINE_DIR))

    sbi_names = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                 "R2_DOCUMENT_BUCKET", "ANTHROPIC_API_KEY")
    sbi_ready, sbi_missing = configured(sbi_names)
    if dry:
        from sbi_ongoing import ongoing_configuration, run_sbi_lane  # exercise imports/config
        config = ongoing_configuration(os.environ)
        steps.append({"step": "SBI ingest/extraction", "status": "dry", "duration": 0.0,
                      "reason": f"configuration={config.status}; no DB/R2/paid calls", "counts": {}})
    elif not sbi_ready or os.environ.get("SBI_OWNER_APPROVED") != "YES":
        reason = "owner: set SBI_OWNER_APPROVED=YES" if sbi_ready else "owner: configure " + ", ".join(sbi_missing)
        steps.append(skip("SBI ingest/extraction", reason))
    else:
        lane_started = time.monotonic()
        try:
            from sbi_ongoing import run_sbi_lane
            result = with_db(run_sbi_lane, directory=SBI_DIR, dry_run=False)
            print("SBI summary: " + json.dumps(result["summary"], sort_keys=True))
            steps.append({"step": "SBI ingest/extraction", "status": "ok",
                          "duration": time.monotonic()-lane_started, "counts": result["summary"]})
        except Exception as exc:
            # isolated SBI lane failure (reported as a hard failure; never hidden)
            steps.append({"step": "SBI ingest/extraction", "status": "failed",
                          "duration": time.monotonic()-lane_started, "reason": f"{type(exc).__name__}: {exc}"})

    cap = with_db(get_cap)
    before = with_db(spent_today)
    targets, scope = with_db(select_active, args.limit, args.backfill)
    print(f"\nselector: {scope}; selected={len(targets)}")
    ids = ",".join(str(row[0]) for row in targets)

    if targets:
        steps.append(run("3. NSE per-IPO lifecycle", PIPELINE_DIR / "nse_lifecycle.py",
                         ["--limit", args.limit, "--skip-discovery", "--dry-run" if dry else "--write"],
                         dry=dry, timeout=900, cwd=PIPELINE_DIR))
        kite_names = ("KITE_API_KEY", "KITE_API_SECRET", "KITE_USER_ID", "KITE_PASSWORD",
                      "KITE_TOTP_SECRET", "KITE_BROKER_PROXY_URL", "KITE_BROKER_PROXY_AUTH_SECRET")
        kite_ready, kite_missing = configured(kite_names)
        if args.skip_kite or not kite_ready:
            steps.append(skip("Kite refresh/candles", "owner: configure " + ", ".join(kite_missing) if not kite_ready else "owner: --skip-kite selected"))
        elif dry:
            steps.append(skip("Kite refresh/candles", "dry-run: authentication/network operation disabled"))
        else:
            refresh = run("Kite token refresh", SCRIPTS_DIR / "refresh_kite_token.py", [], timeout=300)
            refresh_status, structured = classify_kite_refresh(refresh.get("rc", 0), refresh.get("output", ""))
            refresh["status"] = refresh_status
            if structured == "SKIPPED_NOT_ACTIVATED":
                refresh["reason"] = "owner: activate Kite token rotation"
            steps.append(refresh)
            steps.append(run("Kite candles/outcomes", PIPELINE_DIR / "kite_fetch.py", ["--ids", ids, "--write"], timeout=900, cwd=PIPELINE_DIR))

        if dry:
            steps.append(run("score/verdict/completeness", PIPELINE_DIR / "drive.py",
                             ["--ids", ids, "--dry-run"], dry=True, timeout=900, cwd=PIPELINE_DIR))
            steps.append(skip("RHP paid extraction", "owner: live paid lane requires ANTHROPIC_API_KEY and spend cap"))
        elif not os.environ.get("ANTHROPIC_API_KEY"):
            steps.append(skip("RHP paid extraction", "owner: configure ANTHROPIC_API_KEY and approve paid lane"))
        elif cap <= before:
            steps.append(skip("RHP paid extraction", "owner: daily paid-call cap exhausted"))
        else:
            steps.append(run("RHP paid extraction", PIPELINE_DIR / "drive.py",
                             ["--ids", ids, "--write", "--rhp", "--max-spend", f"{cap-before:.2f}"] +
                             (["--ignore-local"] if args.ignore_local else []), timeout=3600, cwd=PIPELINE_DIR))
            steps.append(run("score/verdict/completeness", PIPELINE_DIR / "drive.py",
                             ["--ids", ids, "--write"], timeout=900, cwd=PIPELINE_DIR))
    else:
        steps.append(skip("active IPO processing", "no active IPOs selected", counts={"selected": 0}))

    snapshot_ready, snapshot_missing = configured(("SNAPSHOT_PUBLISH_URL", "SNAPSHOT_PUBLISH_KEY"))
    if dry:
        steps.append(run("snapshot publication consumer proof", PIPELINE_DIR / "publish_snapshot_with_ledger.py",
                         ["--dry-run"], dry=True, timeout=300, cwd=REPO_ROOT))
    elif not snapshot_ready:
        steps.append(skip("snapshot publication consumer proof", "owner: configure " + ", ".join(snapshot_missing)))
    else:
        steps.append(run("snapshot publication consumer proof", PIPELINE_DIR / "publish_snapshot_with_ledger.py",
                         [], timeout=300, cwd=REPO_ROOT))

    after = before if dry else with_db(spent_today)
    return report(steps, started, dry=dry, targets=targets, cap=cap, spent=max(0.0, after-before))


if __name__ == "__main__":
    raise SystemExit(main())
