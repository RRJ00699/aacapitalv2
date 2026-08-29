from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        str(row.get("matrix_id") or ""),
        str(row.get("table") or ""),
        str(row.get("row_key") or ""),
        str(row.get("field") or ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build permanent audit ledger for resolved D1 core conflicts")
    ap.add_argument("--resolved", type=Path, required=True, help="CSV emitted by d1_auto_resolve_conflicts.py")
    ap.add_argument("--final", type=Path, required=True, help="Final comparison CSV after apply")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    with args.resolved.open("r", encoding="utf-8-sig", newline="") as f:
        resolved = list(csv.DictReader(f))
    with args.final.open("r", encoding="utf-8-sig", newline="") as f:
        final = list(csv.DictReader(f))

    final_conflicts = {key(r): r for r in final if r.get("status") == "CONFLICT_KEEP_D1"}
    out = []
    missing_final = []
    reasons = Counter()

    for r in resolved:
        if str(r.get("approved") or "").strip().upper() != "YES":
            continue
        k = key(r)
        frow = final_conflicts.get(k)
        if not frow:
            missing_final.append(k)
            continue
        chosen = str(r.get("recommended_value") or "")
        d1_value = str(frow.get("d1_value") or "")
        if d1_value != chosen:
            raise SystemExit(
                f"final D1 value mismatch for {k}: expected={chosen!r} actual={d1_value!r}"
            )
        reason = str(r.get("resolution_reason") or "")
        reasons[reason] += 1
        out.append({
            "matrix_id": r.get("matrix_id", ""),
            "ipo_id": r.get("ipo_id", ""),
            "company_name": r.get("company_name", ""),
            "table": r.get("table", ""),
            "row_key": r.get("row_key", ""),
            "field": r.get("field", ""),
            "neon_value": r.get("neon_value", ""),
            "matrix_value": r.get("matrix_value", ""),
            "chosen_d1_value": d1_value,
            "resolution_reason": reason,
            "final_status": frow.get("status", ""),
        })

    if missing_final:
        raise SystemExit(f"{len(missing_final)} resolved rows missing from final CONFLICT_KEEP_D1 set")
    if len(out) != len(final_conflicts):
        raise SystemExit(
            f"ledger coverage mismatch: resolved_verified={len(out)} final_conflicts={len(final_conflicts)}"
        )

    fields = [
        "matrix_id","ipo_id","company_name","table","row_key","field",
        "neon_value","matrix_value","chosen_d1_value","resolution_reason","final_status",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out)

    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps({
        "ledger_rows": len(out),
        "final_conflicts": len(final_conflicts),
        "reasons": dict(sorted(reasons.items())),
        "sha256": digest,
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
