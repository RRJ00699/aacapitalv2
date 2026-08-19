#!/usr/bin/env python3
"""Supported daily pipeline entry point for Windows and CI-safe dry runs."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import psycopg2

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
TEMP_ROOT = Path(os.environ.get("RUNNER_TEMP", REPO_ROOT / ".tmp")).resolve()
SBI_DIR = TEMP_ROOT / "sbi-notes"
ACTIVE_DAYS = 100
DOC_FRESH_DAYS = 30
DEFAULT_CAP = 2.0
RHP_DOWNLOAD_SCRIPT = "_scripts/download_sebi_rhps_playwright.py"
SBI_DOWNLOAD_SCRIPT = "_scripts/download_sbi_notes.py"
KITE_REFRESH_SCRIPT = "_scripts/refresh_kite_token.py"
NSE_LIFECYCLE_SCRIPT = "pipeline/nse_lifecycle.py"
NSE_IDENTITY_SCRIPT = "pipeline/nse_identity_backfill.py"
KITE_FETCH_SCRIPT = "pipeline/kite_fetch.py"
KITE_FETCH_15M_SCRIPT = "pipeline/kite_fetch_15m.py"
TOP_DETECTOR_SCRIPT = "pipeline/topout_online.py"
DRIVE_SCRIPT = "pipeline/drive.py"
SNAPSHOT_PUBLISH_SCRIPT = "pipeline/publish_snapshot_with_ledger.py"
RULE_VALIDATION_SCRIPT = "pipeline/rule_validation.py"
# Canonical snapshot producer invoked by the protected publisher: "warm_kv.py"

KITE_REFRESH_STATUS_TO_STEP = {
    "SUCCESS_ROTATED": "ok", "SUCCESS_VALIDATED_ONLY": "skipped",
    "SUCCESS_VALIDATED_HANDED_OFF": "ok",
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
    ("ANTHROPIC_API_KEY", "SBI and RHP paid extraction", "owner: configure paid extraction"),
    ("SBI_SONNET_OWNER_APPROVED", "SBI paid extraction", "owner: approve SBI paid extraction"),
    ("SBI_SONNET_INPUT_USD_PER_MTOK", "SBI price card", "owner: configure SBI paid extraction"),
    ("SBI_SONNET_OUTPUT_USD_PER_MTOK", "SBI price card", "owner: configure SBI paid extraction"),
    ("SBI_SONNET_OUTPUT_CAP", "SBI price card", "owner: configure SBI paid extraction"),
    ("SBI_SONNET_RUN_CAP_USD", "SBI price card", "owner: configure SBI paid extraction"),
    ("RHP_EXTRACTION_OWNER_APPROVED", "RHP paid extraction", "owner: approve RHP paid extraction"),
    ("KITE_API_KEY", "Kite refresh/candles", "owner: configure Kite"),
    ("KITE_API_SECRET", "Kite refresh/candles", "owner: configure Kite"),
    ("KITE_USER_ID", "Kite refresh", "owner: configure Kite"),
    ("KITE_PASSWORD", "Kite refresh", "owner: configure Kite"),
    ("KITE_TOTP_SECRET", "Kite refresh", "owner: configure Kite"),
    ("ALLOW_LEGACY_KITE_DB_TOKEN_WRITE", "Kite local token handoff", "owner: set to 1 with KITE_REFRESH_VALIDATE_ONLY"),
    ("KITE_REFRESH_VALIDATE_ONLY", "Kite local token handoff", "owner: set to 1 with ALLOW_LEGACY_KITE_DB_TOKEN_WRITE"),
    ("EXECUTE_CLOUDFLARE_SECRET_ROTATION", "Kite secret rotation", "optional; when 1, proxy configuration is required"),
    ("KITE_BROKER_PROXY_URL", "Kite rotation only when EXECUTE_CLOUDFLARE_SECRET_ROTATION=1", "owner: configure only for rotation"),
    ("KITE_BROKER_PROXY_AUTH_SECRET", "Kite rotation only when EXECUTE_CLOUDFLARE_SECRET_ROTATION=1", "owner: configure only for rotation"),
    ("SNAPSHOT_PUBLISH_URL", "snapshot publication", "owner: configure snapshot publication"),
    ("SNAPSHOT_PUBLISH_KEY", "snapshot publication", "owner: configure snapshot publication"),
    ("NTFY_TOPIC", "drive.py completeness alerts", "owner: configure completeness alerts (optional)"),
    ("RULE_VALIDATION_OWNER_APPROVED", "rule_validation_results writes",
     "optional; without it the rules step reports but persists nothing"),
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


def db(*, attempts=4, base_delay=2.0, sleep=time.sleep):
    """Open a DB connection, retrying transient connect failures — DNS blips, dead Neon
    sessions, connect timeouts — with bounded exponential backoff. Raises the last
    OperationalError only after every attempt fails."""
    last = None
    for attempt in range(attempts):
        try:
            return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=25,
                                    keepalives=1, keepalives_idle=30,
                                    keepalives_interval=10, keepalives_count=3)
        except psycopg2.OperationalError as exc:
            last = exc
            if attempt == attempts - 1:
                raise
            sleep(base_delay * (2 ** attempt))
    raise last  # pragma: no cover - the loop returns or raises above


def with_db(fn, *args, **kwargs):
    """Invoke an arbitrary callback exactly once; only connection opening retries."""
    conn = db()
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


def with_db_read_retry(fn, *args, attempts=2, **kwargs):
    """Retry a report-only SELECT callback on a fresh session.

    This helper is deliberately used only by ``measure_db``. Writers, SBI/R2,
    paid work and publication must use the one-shot ``with_db`` seam above.
    """
    for attempt in range(attempts):
        conn = db()
        try:
            return fn(conn, *args, **kwargs)
        except psycopg2.OperationalError:
            if attempt + 1 == attempts:
                raise
        finally:
            conn.close()


def measure_db(steps, name, fn, default, *args, **kwargs):
    """Run one report-critical DB measurement without jeopardising the report."""
    started = time.monotonic()
    try:
        return with_db_read_retry(fn, *args, **kwargs), True
    except Exception as exc:
        tail = traceback.format_exc().strip().splitlines()[-12:]
        print(f"\n=== {name}\n    failed - {type(exc).__name__}: {exc}")
        print("    traceback tail:")
        for line in tail:
            print("    " + line[:500])
        steps.append({"step": name, "status": "failed",
                      "duration": time.monotonic() - started,
                      "reason": f"{type(exc).__name__}: {exc}",
                      "traceback_tail": "\n".join(tail)})
        return default, False


def get_cap(conn):
    cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key='daily_spend_cap_usd'")
    row = cur.fetchone()
    return float(row[0]) if row and row[0] else DEFAULT_CAP


def spent_today(conn):
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM rhp_findings WHERE analyzed_at >= date_trunc('day', now())")
    return float(cur.fetchone()[0] or 0)


def select_active(conn, limit, backfill=False):
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    cur = conn.cursor()
    if backfill:
        cur.execute(f"""SELECT id,name_display,listing_date FROM ipo i
                       WHERE in_backtest_universe=TRUE AND {CANONICAL_UNIVERSE_SQL}
                       ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (limit,))
        return cur.fetchall(), "BACKFILL (most recently listed)"
    cur.execute(f"""SELECT i.id,i.name_display,i.listing_date FROM ipo i
      LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id
      WHERE {CANONICAL_UNIVERSE_SQL}
      AND ((i.listing_date IS NOT NULL AND i.listing_date>=current_date-%s)
        OR (i.listing_date IS NULL AND (ii.close_date>=current_date-30
          OR ii.open_date>=current_date-30 OR EXISTS
          (SELECT 1 FROM documents d WHERE d.ipo_id=i.id
           AND d.fetched_at>=now()-(%s||' days')::interval))))
      ORDER BY COALESCE(i.listing_date,current_date+365) DESC LIMIT %s""",
                (ACTIVE_DAYS, DOC_FRESH_DAYS, limit))
    return cur.fetchall(), f"ACTIVE (unlisted, or listed within {ACTIVE_DAYS}d)"


def select_market(conn, limit):
    """Independently bounded listed cohort, prioritising missing then stale bars."""
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    cur = conn.cursor()
    cur.execute(f"""SELECT i.id,i.name_display,i.listing_date
      FROM ipo i
      LEFT JOIN (SELECT ipo_id,max(d)::timestamptz AS latest FROM market_candles GROUP BY ipo_id) d
        ON d.ipo_id=i.id
      LEFT JOIN (SELECT ipo_id,max(ts) AS latest FROM market_candles_15m GROUP BY ipo_id) m
        ON m.ipo_id=i.id
      WHERE {CANONICAL_UNIVERSE_SQL}
        AND i.listing_date IS NOT NULL
        AND i.listing_date BETWEEN (now() AT TIME ZONE 'Asia/Kolkata')::date-%s
                               AND (now() AT TIME ZONE 'Asia/Kolkata')::date
        AND NULLIF(trim(i.symbol),'') IS NOT NULL
      ORDER BY (d.latest IS NULL AND m.latest IS NULL) DESC,
               GREATEST(d.latest,m.latest) ASC NULLS FIRST,i.id
      LIMIT %s""", (ACTIVE_DAYS, limit))
    return cur.fetchall()


def script(relative: str) -> Path:
    return (REPO_ROOT / relative).resolve()


def skip(step, reason, *, counts=None):
    print(f"\n=== {step}\n    skipped - {reason}")
    return {"step": step, "status": "skipped", "duration": 0.0,
            "reason": reason, "counts": counts or {}}


def run(step, script_path, args, *, dry=False, timeout=1800, required=True, cwd=None):
    """Execute a Python file using an absolute path and an explicit working directory."""
    started = time.monotonic()
    path = (REPO_ROOT / script_path).resolve()
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
        traceback_tail = (proc.stderr or "").strip().splitlines()[-12:]
        if traceback_tail:
            print("    stderr tail:")
            for line in traceback_tail:
                print("    " + line[:500])
        detail = traceback_tail[-1:] or [f"exit {proc.returncode}"]
        print("    failed - " + detail[0][:300])
        return {"step": step, "status": "failed", "duration": time.monotonic()-started,
                "reason": detail[0][:300], "traceback_tail": "\n".join(traceback_tail),
                "rc": proc.returncode}
    return {"step": step, "status": "dry" if dry else "ok",
            "duration": time.monotonic()-started, "output": proc.stdout or ""}


def structured_objects(output):
    """Decode JSON objects embedded in a child's otherwise human-readable output."""
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


def require_child_json(item, key):
    for value in reversed(structured_objects(item.get("output", ""))):
        if key in value:
            return value[key]
    item.update(status="failed", reason=f"required child output contract absent: {key}")
    return {}


def discovery_counts(item):
    data = require_child_json(item, "DISCOVERY")
    rows = data.get("discovered_ipos", [])
    resolutions = [row.get("resolution") for row in rows]
    return {
        "returned": data.get("returned_count", 0), "processed": len(rows),
        "matched_existing": sum(value in {"matched_existing", "unchanged", "updated"} for value in resolutions),
        "created": resolutions.count("inserted"),
        "would_create": resolutions.count("bootstrap_required"),
        "bounded_not_created": resolutions.count("bounded_not_created"),
        "failures": len(data.get("errors", [])) + resolutions.count("failed"),
    }


def identity_counts(item):
    data = next((value for value in reversed(structured_objects(item.get("output", "")))
                 if "selected" in value and "rows" in value), None)
    skipped = next((value for value in reversed(structured_objects(item.get("output", "")))
                    if value.get("status") == "skipped"), None)
    if skipped:
        item.update(status="skipped", reason=skipped.get("reason", "source_unavailable"))
        item["evidence"] = skipped.get("evidence")
        return {}
    if data is None:
        item.update(status="failed", reason="required child output contract absent: identity counts")
        return {}
    outcomes = [row.get("outcome") for row in data.get("rows", [])]
    selected_by_need = data.get("selected_by_need", {})
    return {"selected": data.get("selected", 0),
            "isin_selected": selected_by_need.get("isin", 0),
            "date_selected": selected_by_need.get("listing_date", 0),
            "updated": data.get("updates", 0),
            "name_mismatch": outcomes.count("name_mismatch"),
            "isin_conflict": outcomes.count("isin_owner_conflict"),
            "not_found": outcomes.count("not_found")}


def configured(names):
    missing = [name for name in names if not os.environ.get(name)]
    return not missing, missing


def kite_configuration(environ=None):
    environ = os.environ if environ is None else environ
    baseline = ("KITE_API_KEY", "KITE_API_SECRET", "KITE_USER_ID", "KITE_PASSWORD", "KITE_TOTP_SECRET")
    missing = [name for name in baseline if not environ.get(name)]
    rotation_missing = []
    if environ.get("EXECUTE_CLOUDFLARE_SECRET_ROTATION") == "1":
        rotation_missing = [name for name in ("KITE_BROKER_PROXY_URL", "KITE_BROKER_PROXY_AUTH_SECRET")
                            if not environ.get(name)]
    return not missing, missing, rotation_missing


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


def kite_refresh_guarantees_fetch(refresh_status, structured_status):
    """Only structured refresh success proves kite_fetch's token source is usable."""
    return (refresh_status == "ok"
            and structured_status in {"SUCCESS_ROTATED", "SUCCESS_VALIDATED_HANDED_OFF"})


def attach_lane_counts(item, key):
    prefix = key + "="
    lines = [line[len(prefix):] for line in item.get("output", "").splitlines()
             if line.startswith(prefix)]
    try:
        data = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        item.update(status="failed", reason=f"required child output contract absent: {key}")
        return
    if key == "FIFTEEN_MIN_CANDLES":
        item["counts"] = {name: data.get(name, 0) for name in
                          ("selected", "attempted", "bars_received", "bars_inserted",
                           "duplicates", "no_data", "transient_failed")}
    else:
        item["counts"] = {"selected": data.get("selected", 0),
                          "observations_inserted": data.get("observations_inserted", 0),
                          **{f"state_{k}": v for k, v in data.get("state_counts", {}).items()}}


def attach_daily_counts(item):
    prefix = "KITE_DAILY_SUMMARY="
    lines = [line[len(prefix):] for line in item.get("output", "").splitlines()
             if line.startswith(prefix)]
    if not lines:
        item.update(status="failed", reason="required child output contract absent: KITE_DAILY_SUMMARY")
        return
    try:
        item["counts"] = json.loads(lines[-1])
    except json.JSONDecodeError:
        item.update(status="failed", reason="malformed KITE_DAILY_SUMMARY")


def attach_sebi_status(item):
    prefix = "SEBI_DOWNLOAD_SUMMARY="
    lines = [line[len(prefix):] for line in item.get("output", "").splitlines()
             if line.startswith(prefix)]
    if not lines:
        item.update(status="failed", reason="required downloader summary absent")
        return
    try:
        data = json.loads(lines[-1])
    except (json.JSONDecodeError, TypeError):
        item.update(status="failed", reason="malformed downloader summary")
        return
    item["counts"] = {f"this_run_{key}": value for key, value in data.get("this_run", {}).items()}
    item["counts"].update({f"backlog_{key}": value for key, value in data.get("backlog", {}).items()})
    exhausted = data.get("backlog", {}).get("owner_action_exhausted", 0)
    if exhausted:
        item["owner_action"] = f"owner: retry or resolve {exhausted} exhausted SEBI filing(s)"
    current = data.get("this_run", {})
    backlog = data.get("backlog", {})
    if (data.get("status") == "RETRY_PENDING" and current.get("succeeded", 0) > 0
            and current.get("failed", 0) == 0 and not exhausted):
        item.update(status="ok", reason="ok/progress_pending")
    elif data.get("status") in {"PARTIAL", "RETRY_PENDING"}:
        item.update(status="partial", reason=data["status"])


def completeness_plan(conn, ids):
    from completeness import check_completeness
    return [check_completeness(conn, ipo_id) for ipo_id in ids]


def completeness_counts(before, after=None):
    later = {row["ipo_id"]: row for row in (after or before)}
    return {str(row["ipo_id"]):
            f"before={row['completeness_pct']}% after={later[row['ipo_id']]['completeness_pct']}% "
            f"missing={len(later[row['ipo_id']]['missing'])} pending={len(later[row['ipo_id']]['pending'])} "
            f"retry={later[row['ipo_id']]['retry_lanes']}"
            for row in before}


def write_completeness_manifest(rows):
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT / "completeness-missing.json"
    path.write_text(json.dumps(rows, default=str, indent=2, sort_keys=True), encoding="utf-8")
    return path


def run_kite_live(ids, rotation_missing):
    """Refresh then fetch only when the refresh proves the shared token is usable."""
    results = []
    token_ready = False
    structured = None
    if rotation_missing:
        results.append(skip("Kite token refresh", "owner: configure " +
                            ", ".join(rotation_missing) + " for activated rotation"))
    else:
        refresh = run("Kite token refresh", KITE_REFRESH_SCRIPT, [], timeout=300)
        refresh_status, structured = classify_kite_refresh(
            refresh.get("rc", 0), refresh.get("output", ""))
        refresh["status"] = refresh_status
        if structured == "SKIPPED_NOT_ACTIVATED":
            refresh["reason"] = "owner: activate Kite token rotation"
        elif structured == "SUCCESS_VALIDATED_ONLY":
            refresh["reason"] = ("owner: set ALLOW_LEGACY_KITE_DB_TOKEN_WRITE=1 "
                                 "with KITE_REFRESH_VALIDATE_ONLY=1")
        results.append(refresh)
        token_ready = kite_refresh_guarantees_fetch(refresh_status, structured)
    if token_ready:
        daily = run("Daily candles/outcomes", KITE_FETCH_SCRIPT,
                    ["--ids", ids, "--write", "--no-15m"], timeout=900, cwd=PIPELINE_DIR)
        if daily["status"] != "failed": attach_daily_counts(daily)
        results.append(daily)
        if daily["status"] == "failed":
            reason = "daily candles/outcomes failed; dependent Kite lanes not run"
            results.append(skip("15-min candles", reason))
            results.append(skip("TOP DISCOVERY", reason))
            return results
        limit = max(1, len([value for value in ids.split(",") if value]))
        candles = run("15-min candles", KITE_FETCH_15M_SCRIPT,
                      ["--ids", ids, "--limit", limit, "--write"], timeout=900, cwd=PIPELINE_DIR)
        if candles["status"] != "failed": attach_lane_counts(candles, "FIFTEEN_MIN_CANDLES")
        results.append(candles)
        if candles["status"] == "failed":
            results.append(skip("TOP DISCOVERY", "15-min candles failed; TOP requires fresh input"))
        else:
            detector = run("TOP DISCOVERY", TOP_DETECTOR_SCRIPT,
                           ["--ids", ids, "--limit", limit, "--write"], timeout=300, cwd=PIPELINE_DIR)
            if detector["status"] != "failed": attach_lane_counts(detector, "TOP_DETECTOR")
            results.append(detector)
    else:
        reason = ("owner: set ALLOW_LEGACY_KITE_DB_TOKEN_WRITE=1 with "
                  "KITE_REFRESH_VALIDATE_ONLY=1" if structured == "SUCCESS_VALIDATED_ONLY"
                  else "owner: refresh did not guarantee a usable kite_fetch token")
        results.append(skip("Daily candles/outcomes", reason))
        results.append(skip("15-min candles", reason))
        results.append(skip("TOP DISCOVERY", reason))
    return results


def classify_sbi_configuration(config):
    """Keep the SBI worker's typed configuration states visible to the orchestrator."""
    return {"SKIPPED_OWNER_NOT_CONFIGURED": "skipped",
            "WARNING_CONFIGURATION_ERROR": "warning"}.get(config.status, "configured")


def report(steps, started, *, dry, targets, market_targets=None,
           selector_available=True, market_selector_available=True, cap=0.0, spent=0.0):
    duration = time.monotonic() - started
    failed = [s for s in steps if s["status"] == "failed"]
    partial = [s for s in steps if s["status"] == "partial"]
    total = "failed" if failed else ("partial/retry_required" if partial else ("dry" if dry else "ok"))
    print("\n" + "=" * 72)
    print("END-OF-RUN REPORT")
    active = str(len(targets)) if selector_available else "UNKNOWN — selector failed"
    market = str(len(market_targets or [])) if market_selector_available else "UNKNOWN — selector failed"
    print(f"total status: {total} | runtime: {duration:.1f}s | active pipeline IPOs: {active} | market IPOs: {market}")
    for item in steps:
        why = f" | {item['reason']}" if item.get("reason") else ""
        print(f"{item['status']:7} {item['duration']:7.1f}s  {item['step']}{why}")
        if item.get("counts"):
            print(" " * 17 + "counts: " + ", ".join(f"{key}={value}" for key, value in item["counts"].items()))
        if item.get("traceback_tail"):
            print(" " * 17 + "traceback_tail:")
            for line in item["traceback_tail"].splitlines():
                print(" " * 17 + line[:500])
    print("what changed: " + ("none (read-only dry-run)" if dry else "see per-step counts above"))
    snapshot = next((s for s in steps if s["step"].startswith("snapshot publication")), None)
    print("snapshot pointer/consumer proof: " +
          (f"active_version={snapshot.get('counts', {}).get('active_version')} consumer_source=active" if snapshot and snapshot["status"] == "ok"
           else (snapshot.get("reason", snapshot["status"]) if snapshot else "not run")))
    print(f"paid calls: {'0 (dry-run)' if dry else f'bounded by ${cap:.2f}; measured ${spent:.3f}'}")
    print(f"production writes: {'0 (dry-run)' if dry else 'authorized by this live command; see steps'}")
    actions = [value for s in steps for value in (s.get("reason"), s.get("owner_action"))
               if value and value.startswith("owner:")]
    print("owner actions still required: " + ("; ".join(actions) if actions else "none"))
    print("=" * 72)
    return 1 if failed else (3 if partial else 0)


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
        sebi = run("SEBI RHP download", RHP_DOWNLOAD_SCRIPT,
                   ["--max", args.max_rhps], timeout=2400)
        if sebi["status"] != "failed":
            attach_sebi_status(sebi)
        steps.append(sebi)
    if dry or args.skip_download:
        steps.append(skip("SBI note download", "dry-run: external download disabled" if dry else "owner: command-line download skip"))
    else:
        steps.append(run("SBI note download", SBI_DOWNLOAD_SCRIPT,
                         ["--out", SBI_DIR], timeout=1200))

    # Structural lane handshake: 2c. NSE discovery -> 2d. bounded NSE identity ->
    # 2e/2f. SBI ingest -> 3. NSE per-IPO lifecycle.
    discovery = run("NSE discovery", NSE_LIFECYCLE_SCRIPT,
                     ["--discovery-only", "--limit", args.limit, "--max-new-rows", 10,
                      "--dry-run" if dry else "--write"], dry=dry, timeout=300, cwd=PIPELINE_DIR)
    if discovery["status"] != "failed":
        discovery["counts"] = discovery_counts(discovery)
    steps.append(discovery)
    identity = run("NSE identity/ISIN/listing-date backfill", NSE_IDENTITY_SCRIPT,
                     ["--limit", args.limit, "--quote-limit", args.limit,
                      "--dry-run" if dry else "--write"], dry=dry, timeout=300, cwd=PIPELINE_DIR)
    if identity["status"] != "failed":
        identity["counts"] = identity_counts(identity)
    steps.append(identity)
    targets, selector_ok = measure_db(steps, "Active IPO selector", select_active,
                                      ([], "failed"), args.limit, args.backfill)
    scope = targets[1] if selector_ok else "failed"
    targets = targets[0]
    print(f"\nActive IPO selector = {'ok' if selector_ok else 'failed'}")
    if selector_ok:
        print(f"selector: {scope}; selected={len(targets)}")
    ids = ",".join(str(row[0]) for row in targets)
    target_ids = [row[0] for row in targets]
    market_targets, market_selector_ok = measure_db(
        steps, "Market IPO selector", select_market, [], args.limit)
    market_ids = ",".join(str(row[0]) for row in market_targets)
    print(f"Market IPO selector = {'ok' if market_selector_ok else 'failed'}; selected="
          f"{len(market_targets) if market_selector_ok else 'UNKNOWN'}")
    pre_completeness, pre_ok = (measure_db(steps, "Pre-run V2 completeness plan",
                                           completeness_plan, [], target_ids)
                                if selector_ok and target_ids else ([], selector_ok))
    if pre_ok:
        steps.append({"step": "Pre-run V2 completeness plan", "status": "dry" if dry else "ok",
                      "duration": 0.0, "counts": completeness_counts(pre_completeness)})

    sbi_names = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_DOCUMENT_BUCKET")
    sbi_ready, sbi_missing = configured(sbi_names)
    if dry:
        from sbi_ongoing import ongoing_configuration, run_sbi_lane  # exercise imports/config
        config = ongoing_configuration(os.environ)
        steps.append({"step": "SBI ingest", "status": "dry", "duration": 0.0,
                      "reason": "no DB/R2 writes", "counts": {}})
        steps.append({"step": "SBI extraction", "status": "dry", "duration": 0.0,
                      "reason": f"configuration={config.status}; no paid calls", "counts": {}})
    elif not sbi_ready or os.environ.get("SBI_OWNER_APPROVED") != "YES":
        reason = "owner: set SBI_OWNER_APPROVED=YES" if sbi_ready else "owner: configure " + ", ".join(sbi_missing)
        steps.append(skip("SBI ingest", reason))
        steps.append(skip("SBI extraction", "owner: SBI ingest must be configured first"))
    else:
        lane_started = time.monotonic()
        try:
            from sbi_ongoing import run_sbi_lane
            result = with_db(run_sbi_lane, directory=SBI_DIR, dry_run=False)
            print("SBI summary: " + json.dumps(result["summary"], sort_keys=True))
            summary = result["summary"]
            ingest_counts = {key: summary.get(key, 0) for key in
                             ("downloaded", "resolved", "unresolved", "newly_ledgered", "already_ledgered", "ingest_errors")}
            extraction_counts = {"selected": summary.get("selected", 0),
                                 "completed": summary.get("EXTRACTED", 0) + summary.get("EXTRACTED_WITH_DROPS", 0),
                                 "skipped": summary.get("ALREADY_EXTRACTED", 0),
                                 "rejected": summary.get("EVIDENCE_REJECTED", 0)}
            steps.append({"step": "SBI ingest", "status": "ok",
                          "duration": time.monotonic()-lane_started, "counts": ingest_counts})
            extraction_status = summary.get("extraction_status")
            if extraction_status == "CONFIGURED":
                steps.append({"step": "SBI extraction", "status": "ok", "duration": 0.0,
                              "counts": extraction_counts})
            else:
                detail = summary.get("configuration_error") or extraction_status
                steps.append(skip("SBI extraction", f"owner: {detail}", counts=extraction_counts))
        except Exception as exc:
            # isolated SBI lane failure (reported as a hard failure; never hidden)
            steps.append({"step": "SBI ingest", "status": "failed",
                          "duration": time.monotonic()-lane_started, "reason": f"{type(exc).__name__}: {exc}"})
            steps.append(skip("SBI extraction", "owner: ingest failed"))

    cap, cap_ok = measure_db(steps, "Spend cap measurement", get_cap, 0.0)
    before, before_ok = measure_db(steps, "Spend before measurement", spent_today, 0.0)
    spend_available = cap_ok and before_ok
    if targets and selector_ok:
        steps.append(run("3. NSE per-IPO lifecycle", NSE_LIFECYCLE_SCRIPT,
                         ["--limit", args.limit, "--skip-discovery", "--dry-run" if dry else "--write"],
                         dry=dry, timeout=900, cwd=PIPELINE_DIR))
        steps.append(skip("Anchor allocation parsing",
                          "owner: BLOCKER_ANCHOR_OFFICIAL_SOURCE_UNPROVEN"))
        kite_ready, kite_missing, rotation_missing = kite_configuration()
        if not market_selector_ok:
            reason = "market selector failed; dependent market work skipped"
            steps.extend([skip("Kite token refresh", reason), skip("Daily candles/outcomes", reason),
                          skip("15-min candles", reason), skip("TOP DISCOVERY", reason)])
        elif not market_targets:
            reason = "no eligible listed IPOs in market cohort"
            steps.extend([skip("Kite token refresh", reason, counts={"selected": 0}),
                          skip("Daily candles/outcomes", reason, counts={"selected": 0}),
                          skip("15-min candles", reason, counts={"selected": 0}),
                          skip("TOP DISCOVERY", reason, counts={"selected": 0})])
        elif args.skip_kite or not kite_ready:
            reason = "owner: configure " + ", ".join(kite_missing) if not kite_ready else "owner: --skip-kite selected"
            steps.append(skip("Kite token refresh", reason))
            steps.append(skip("Daily candles/outcomes", reason))
            steps.append(skip("15-min candles", reason))
            steps.append(skip("TOP DISCOVERY", "owner: 15-min candle supply unavailable"))
        elif dry:
            steps.append(skip("Kite token refresh", "dry-run: authentication/network operation disabled"))
            daily = run("Daily candles/outcomes", KITE_FETCH_SCRIPT,
                        ["--ids", market_ids, "--dry-run", "--no-15m"], dry=True, timeout=300, cwd=PIPELINE_DIR)
            if daily["status"] != "failed": attach_daily_counts(daily)
            steps.append(daily)
            candles = run("15-min candles", KITE_FETCH_15M_SCRIPT,
                          ["--ids", market_ids, "--limit", len(market_targets), "--dry-run"], dry=True, timeout=300, cwd=PIPELINE_DIR)
            if candles["status"] != "failed": attach_lane_counts(candles, "FIFTEEN_MIN_CANDLES")
            steps.append(candles)
            detector = run("TOP DISCOVERY", TOP_DETECTOR_SCRIPT,
                           ["--ids", market_ids, "--limit", len(market_targets), "--dry-run"], dry=True, timeout=300, cwd=PIPELINE_DIR)
            if detector["status"] != "failed": attach_lane_counts(detector, "TOP_DETECTOR")
            steps.append(detector)
        else:
            steps.extend(run_kite_live(market_ids, rotation_missing))

        if dry:
            steps.append(skip("RHP paid extraction", "dry-run: paid extraction disabled"))
        elif not spend_available:
            steps.append(skip("RHP paid extraction", "paid execution disabled: spend measurement unavailable"))
        elif os.environ.get("RHP_EXTRACTION_OWNER_APPROVED") != "YES":
            steps.append(skip("RHP paid extraction", "owner: approve RHP paid extraction"))
        elif not os.environ.get("ANTHROPIC_API_KEY"):
            steps.append(skip("RHP paid extraction", "owner: configure ANTHROPIC_API_KEY and approve paid lane"))
        elif cap <= before:
            steps.append(skip("RHP paid extraction", "owner: daily paid-call cap exhausted"))
        else:
            steps.append(run("RHP paid extraction", DRIVE_SCRIPT,
                             ["--ids", ids, "--write", "--rhp", "--max-spend", f"{cap-before:.2f}"] +
                             (["--ignore-local"] if args.ignore_local else []), timeout=3600, cwd=PIPELINE_DIR))
        steps.append(run("score/verdict/completeness", DRIVE_SCRIPT,
                         ["--ids", ids, "--dry-run" if dry else "--write"], dry=dry, timeout=900, cwd=PIPELINE_DIR))
        post_completeness, post_ok = measure_db(steps, "Post-run V2 completeness measurement",
                                                completeness_plan, [], target_ids)
        if post_ok:
            manifest_path = write_completeness_manifest(post_completeness)
            steps.append({"step": "Post-run V2 completeness measurement",
                          "status": "dry" if dry else "ok", "duration": 0.0,
                          "reason": f"full detail: {manifest_path}",
                          "counts": completeness_counts(pre_completeness, post_completeness)})
        # Bounded, free, and owner-gated only when it persists. The dry run still
        # evaluates every rule and reports NOT_EVALUABLE with the absent inputs named,
        # which is the point: a rule nobody can evaluate must be visible, not silent.
        if dry:
            steps.append(run("Database-backed Listing rules layers", RULE_VALIDATION_SCRIPT,
                             ["--dry-run"], dry=True, timeout=600, cwd=PIPELINE_DIR))
        elif os.environ.get("RULE_VALIDATION_OWNER_APPROVED") != "1":
            steps.append(run("Database-backed Listing rules layers", RULE_VALIDATION_SCRIPT,
                             ["--dry-run"], timeout=600, cwd=PIPELINE_DIR))
        else:
            steps.append(run("Database-backed Listing rules layers", RULE_VALIDATION_SCRIPT,
                             ["--write"], timeout=600, cwd=PIPELINE_DIR))
    elif not selector_ok:
        steps.append(skip("active IPO processing", "selector failed; dependent cohort work skipped",
                          counts={"selected": 0}))
    else:
        steps.append(skip("active IPO processing", "no active IPOs selected", counts={"selected": 0}))

    snapshot_ready, snapshot_missing = configured(("SNAPSHOT_PUBLISH_URL", "SNAPSHOT_PUBLISH_KEY"))
    if dry:
        steps.append(run("snapshot publication consumer proof", SNAPSHOT_PUBLISH_SCRIPT,
                         ["--dry-run"], dry=True, timeout=300, cwd=REPO_ROOT))
    elif not snapshot_ready:
        steps.append(skip("snapshot publication consumer proof", "owner: configure " + ", ".join(snapshot_missing)))
    else:
        snapshot = run("snapshot publication consumer proof", SNAPSHOT_PUBLISH_SCRIPT, [], timeout=300, cwd=REPO_ROOT)
        if snapshot["status"] == "ok":
            proofs = [value["SNAPSHOT_CONSUMER_PROOF"] for value in structured_objects(snapshot.get("output", ""))
                      if "SNAPSHOT_CONSUMER_PROOF" in value]
            if not proofs or proofs[-1].get("consumer_source") != "active":
                snapshot.update(status="failed", reason="snapshot publication lacked active-pointer consumer proof")
            else:
                snapshot["counts"] = {"published": proofs[-1].get("snapshots_published", 0),
                                      "active_version": proofs[-1].get("active_version")}
        steps.append(snapshot)

    after, after_ok = ((before, before_ok) if dry else
                       measure_db(steps, "Spend after measurement", spent_today, before))
    return report(steps, started, dry=dry, targets=targets,
                  market_targets=market_targets, selector_available=selector_ok,
                  market_selector_available=market_selector_ok,
                  cap=cap, spent=max(0.0, after-before))


if __name__ == "__main__":
    raise SystemExit(main())
