from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFE = {"VERIFIED_CURRENT_TOKEN", "RECOVERED_CURRENT_IDENTITY"}


def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"


def d1_query(config: Path, binding: str, sql: str):
    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    cp = subprocess.run(
        [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
         "--remote", "--command", sql, "--json"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if cp.returncode != 0:
        raise SystemExit(f"Wrangler D1 query failed\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    payload = json.loads(cp.stdout)
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("results"), list):
                return item["results"]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="List audited-safe IPOs missing D1 day/5m candles")
    ap.add_argument("--identity-audit", type=Path, required=True)
    ap.add_argument("--wrangler-config", type=Path, required=True)
    ap.add_argument("--binding", default="DB")
    args = ap.parse_args()

    audit = json.loads(args.identity_audit.read_text(encoding="utf-8"))
    safe = [r for r in audit.get("rows", []) if r.get("status") in SAFE and r.get("chosen_token")]
    ids = [int(r["ipo_id"]) for r in safe]
    if not ids:
        raise SystemExit("no safe audited IPOs")
    id_csv = ",".join(map(str, ids))
    rows = d1_query(args.wrangler_config.resolve(), args.binding,
        f"SELECT ipo_id, SUM(CASE WHEN interval='1d' THEN 1 ELSE 0 END) AS d1, "
        f"SUM(CASE WHEN interval='5m' THEN 1 ELSE 0 END) AS m5 "
        f"FROM market_bars WHERE ipo_id IN ({id_csv}) GROUP BY ipo_id")
    have = {int(r["ipo_id"]): (int(r.get("d1") or 0), int(r.get("m5") or 0)) for r in rows}
    missing = []
    for r in safe:
        ipo_id = int(r["ipo_id"])
        d1, m5 = have.get(ipo_id, (0, 0))
        if d1 == 0 or m5 == 0:
            missing.append({
                "ipo_id": ipo_id,
                "name": r.get("name"),
                "symbol": r.get("symbol"),
                "status": r.get("status"),
                "chosen_token": r.get("chosen_token"),
                "rows_1d": d1,
                "rows_5m": m5,
            })
    print(json.dumps({"safe_total": len(safe), "missing_total": len(missing), "missing": missing}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
