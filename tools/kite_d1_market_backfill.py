from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from kiteconnect import KiteConnect

ROOT = Path(__file__).resolve().parents[1]


def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"


def sqlv(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def d1_query(config: Path, binding: str, sql: str):
    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    cmd = [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
           "--remote", "--command", sql, "--json"]
    cp = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    if cp.returncode != 0:
        if cp.stdout:
            print(cp.stdout, end="")
        if cp.stderr:
            print(cp.stderr, end="")
        raise SystemExit(f"Wrangler D1 query failed with exit code {cp.returncode}: {sql}")
    try:
        payload = json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Wrangler returned non-JSON output for D1 query: {exc}\n{cp.stdout}") from exc
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("results"), list):
                return item["results"]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def get_kite_credentials():
    import psycopg2
    url = os.environ.get("NEON_READONLY_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise SystemExit("NEON_READONLY_DATABASE_URL (preferred) or DATABASE_URL is required")
    conn = psycopg2.connect(url, connect_timeout=20)
    conn.set_session(readonly=True, autocommit=False)
    try:
        cur = conn.cursor()
        cur.execute("SELECT key,value FROM platform_config WHERE key IN ('kite_api_key','kite_access_token')")
        vals = dict(cur.fetchall())
    finally:
        conn.close()
    api_key = vals.get("kite_api_key") or os.environ.get("KITE_API_KEY")
    token = vals.get("kite_access_token") or os.environ.get("KITE_ACCESS_TOKEN")
    if not api_key or not token:
        raise SystemExit("Kite credentials unavailable; run _scripts/refresh_kite_token.py first")
    return api_key, token


def valid_price(value) -> bool:
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def normalize_bar(ipo_id: int, interval: str, candle: dict):
    o, h, lo, c = candle.get("open"), candle.get("high"), candle.get("low"), candle.get("close")
    if not all(valid_price(x) for x in (o, h, lo, c)):
        return None
    od, hd, ld, cd = map(lambda x: Decimal(str(x)), (o, h, lo, c))
    if hd < max(od, cd) or ld > min(od, cd) or hd < ld:
        return None
    raw_date = candle.get("date")
    if interval == "1d":
        if hasattr(raw_date, "date"):
            ts = raw_date.date().isoformat()
        else:
            ts = str(raw_date)[:10]
    else:
        if isinstance(raw_date, datetime):
            ts = raw_date.isoformat()
        else:
            ts = str(raw_date)
    volume = int(candle.get("volume") or 0)
    fp_body = f"kite|{ipo_id}|{interval}|{ts}|{o}|{h}|{lo}|{c}|{volume}"
    fingerprint = hashlib.sha256(fp_body.encode("utf-8")).hexdigest()
    return {
        "ipo_id": ipo_id, "interval": interval, "ts": ts,
        "open_rs": str(o), "high_rs": str(h), "low_rs": str(lo), "close_rs": str(c),
        "volume_shares": volume, "source_name": "zerodha_kite", "content_fingerprint": fingerprint,
    }


def statement(row: dict) -> str:
    return (
        "INSERT INTO market_bars(ipo_id,interval,ts,open_rs,high_rs,low_rs,close_rs,volume_shares,source_name,content_fingerprint) VALUES("
        f"{int(row['ipo_id'])},{sqlv(row['interval'])},{sqlv(row['ts'])},{sqlv(row['open_rs'])},{sqlv(row['high_rs'])},"
        f"{sqlv(row['low_rs'])},{sqlv(row['close_rs'])},{int(row['volume_shares'])},{sqlv(row['source_name'])},{sqlv(row['content_fingerprint'])}) "
        "ON CONFLICT(ipo_id,interval,ts) DO NOTHING;"
    )


def execute_sql_file(config: Path, binding: str, statements: list[str]):
    if not statements:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8", newline="\n") as f:
        f.write("PRAGMA foreign_keys=ON;\n")
        for s in statements:
            f.write(s + "\n")
        path = Path(f.name)
    try:
        subprocess.run([npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
                        "--remote", "--file", str(path)], cwd=ROOT, check=True, text=True,
                       encoding="utf-8", errors="replace")
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill IPO listing->lock30 day + 5m Kite candles into remote D1")
    ap.add_argument("--report", type=Path, default=ROOT / "artifacts/kite-ipo-backfill-report.json")
    ap.add_argument("--wrangler-config", type=Path, required=True)
    ap.add_argument("--binding", default="DB")
    ap.add_argument("--limit", type=int, default=10, help="IPOs to fetch; default 10 pilot; use 0 for all resolved")
    ap.add_argument("--apply", action="store_true", help="write to remote D1; absent = fetch/count only")
    ap.add_argument("--max-statements-per-import", type=int, default=12000)
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()

    if args.apply and os.environ.get("AACAPITAL_D1_STAGING_CONFIRM") != "YES":
        ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES before remote D1 writes")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    windows = [w for w in report.get("windows", []) if w.get("kite_token")]
    if args.limit:
        windows = windows[:args.limit]
    if not windows:
        raise SystemExit("no resolved IPO windows in report")

    config = args.wrangler_config.resolve()
    ids = sorted({int(w["ipo_id"]) for w in windows})
    id_csv = ",".join(map(str, ids))
    parents = d1_query(config, args.binding, f"SELECT id FROM ipo WHERE id IN ({id_csv})")
    parent_ids = {int(r["id"]) for r in parents}
    missing_parents = sorted(set(ids) - parent_ids)
    if missing_parents:
        raise SystemExit(f"D1 parent spine missing ipo ids: {missing_parents[:20]}")

    before = d1_query(config, args.binding,
                      f"SELECT COUNT(*) AS n FROM market_bars WHERE ipo_id IN ({id_csv}) AND interval IN ('1d','5m')")
    before_rows = int(before[0]["n"]) if before else 0

    api_key, token = get_kite_credentials()
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(token)
    profile = kite.profile()
    print(f"Kite token valid for user_id={profile.get('user_id')}")

    statements: list[str] = []
    fetched_rows = 0
    invalid_rows = 0
    failed = []
    per_ipo = []
    for idx, w in enumerate(windows, 1):
        ipo_id = int(w["ipo_id"])
        symbol = w.get("symbol") or ""
        instrument_token = int(w["kite_token"])
        start = date.fromisoformat(w["listing_date"])
        end = date.fromisoformat(w["lock30"])
        counts = {}
        for kite_interval, d1_interval in (("day", "1d"), ("5minute", "5m")):
            try:
                candles = kite.historical_data(instrument_token, start, end, kite_interval)
            except Exception as e:
                failed.append({"ipo_id": ipo_id, "symbol": symbol, "interval": d1_interval, "error": str(e)[:240]})
                counts[d1_interval] = 0
                time.sleep(args.sleep)
                continue
            good = 0
            for candle in candles:
                row = normalize_bar(ipo_id, d1_interval, candle)
                if row is None:
                    invalid_rows += 1
                    continue
                good += 1
                fetched_rows += 1
                statements.append(statement(row))
                if args.apply and len(statements) >= args.max_statements_per_import:
                    execute_sql_file(config, args.binding, statements)
                    statements.clear()
            counts[d1_interval] = good
            time.sleep(args.sleep)
        per_ipo.append({"ipo_id": ipo_id, "symbol": symbol, **counts})
        print(f"[{idx}/{len(windows)}] {symbol:<14} day={counts.get('1d',0):4} 5m={counts.get('5m',0):5}")

    if args.apply and statements:
        execute_sql_file(config, args.binding, statements)
        statements.clear()

    after_rows = before_rows
    if args.apply:
        after = d1_query(config, args.binding,
                         f"SELECT COUNT(*) AS n FROM market_bars WHERE ipo_id IN ({id_csv}) AND interval IN ('1d','5m')")
        after_rows = int(after[0]["n"]) if after else 0

    result = {
        "mode": "APPLY" if args.apply else "FETCH_ONLY",
        "ipos": len(windows),
        "before_rows": before_rows,
        "fetched_valid_rows": fetched_rows,
        "invalid_rows": invalid_rows,
        "failed_requests": len(failed),
        "after_rows": after_rows,
        "new_rows_verified": after_rows - before_rows if args.apply else 0,
        "idempotent_policy": "ON_CONFLICT_DO_NOTHING",
        "persisted_intervals": ["1d", "5m"],
        "derived_not_persisted": ["15m"],
    }
    out = ROOT / "artifacts" / ("kite-d1-market-backfill-apply.json" if args.apply else "kite-d1-market-backfill-fetch.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": result, "per_ipo": per_ipo, "failed": failed}, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    print(f"output={out.relative_to(ROOT)}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
