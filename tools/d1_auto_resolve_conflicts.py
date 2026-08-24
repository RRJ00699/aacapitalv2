from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import tools.d1_apply_core_csv as importer


def dec(value: str | None):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None


def canonical_decimal(value: str) -> str:
    number = dec(value)
    if number is None:
        return value
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def parse_date(value: str | None):
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%a, %b %d, %Y", "%a, %b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    # IPO Matrix sometimes emits single-digit day without zero padding; %d accepts both.
    return None


def registrar_norm(value: str | None) -> str:
    text = (value or "").lower()
    text = text.replace("private", "pvt").replace("limited", "ltd")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def resolve(row: dict[str, str]) -> tuple[str | None, str]:
    field = row.get("field", "")
    neon = row.get("neon_value", "")
    matrix = row.get("matrix_value", "")
    company = row.get("company_name", "")

    if row.get("status") != "MISSING_D1_SOURCE_CONFLICT":
        return None, "NOT_CONFLICT"

    if field == "face_value_rs":
        if dec(neon) is not None and dec(neon) == dec(matrix):
            return canonical_decimal(matrix), "NUMERIC_EQUIVALENT"
        return matrix or None, "MATRIX_CANONICAL_FACE_VALUE"

    if field in {"open_date", "close_date", "listing_date"}:
        nd, md = parse_date(neon), parse_date(matrix)
        if nd and md and nd == md:
            return nd, "DATE_FORMAT_ONLY"
        # For historical issue timetable, prefer the normalized ISO Neon date when they disagree.
        return nd or md, "CANONICAL_TIMETABLE_DATE"

    if field == "registrar_name":
        if registrar_norm(neon) == registrar_norm(matrix):
            return neon or matrix, "REGISTRAR_NAME_VARIANT"
        return neon or matrix, "REGISTRAR_CANONICAL_NEON"

    if field in {"issue_size_cr", "fresh_cr", "ofs_cr"}:
        n, m = dec(neon), dec(matrix)
        if m is None:
            return neon or None, "MATRIX_MISSING"
        if n is None:
            return canonical_decimal(matrix), "MATRIX_ISSUE_STRUCTURE"
        # Proven legacy Neon defect: some crore columns contain raw rupees (x10,000,000).
        if m != 0:
            ratio = abs(n / m)
            if Decimal("9000000") <= ratio <= Decimal("11000000"):
                return canonical_decimal(matrix), "NEON_RAW_RUPEE_SCALE_ERROR"
        # For the remaining historical issue-structure disagreements, IPO Matrix is the
        # reviewed archive source and D1 is currently NULL, so take Matrix without overwrite.
        return canonical_decimal(matrix), "MATRIX_ISSUE_STRUCTURE"

    if field in {"band_lo_rs", "band_hi_rs"}:
        n, m = dec(neon), dec(matrix)
        if m is not None and n is not None and n > 0 and m / n >= Decimal("50"):
            return canonical_decimal(matrix), "NEON_PRICE_BAND_SCALE_ERROR"
        return canonical_decimal(matrix), "MATRIX_PRICE_BAND"

    if field == "issue_price_rs":
        # The current two conflicts were externally verified:
        # Fineotex Chemical IPO issue price = Rs 70 (SEBI prospectus),
        # Future Ventures India IPO issue price = Rs 10 (official/market records).
        verified = {
            "Fineotex Chemical Ltd.": "70",
            "Future Ventures India Ltd.": "10",
        }
        if company in verified:
            return verified[company], "EXTERNALLY_VERIFIED_ISSUE_PRICE"
        return None, "MANUAL_ISSUE_PRICE_REQUIRED"

    return None, "UNRESOLVED_RULE"


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve known systematic D1/Neon/IPO Matrix core conflicts and optionally apply them")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    target = ap.add_mutually_exclusive_group()
    target.add_argument("--apply-local", action="store_true")
    target.add_argument("--apply-staging", action="store_true")
    ap.add_argument("--wrangler-config", type=Path, default=importer.ROOT / "d1/wrangler.jsonc")
    ap.add_argument("--binding", default="DB")
    ap.add_argument("--max-file-bytes", type=int, default=5_000_000)
    args = ap.parse_args()

    with args.csv.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    resolved = 0
    unresolved = 0
    reasons: dict[str, int] = {}
    out = []
    for row in rows:
        if row.get("status") != "MISSING_D1_SOURCE_CONFLICT":
            continue
        value, reason = resolve(row)
        row = dict(row)
        row["resolution_reason"] = reason
        if value not in (None, ""):
            row["recommended_value"] = str(value)
            row["approved"] = "YES"
            resolved += 1
        else:
            row["approved"] = ""
            unresolved += 1
        reasons[reason] = reasons.get(reason, 0) + 1
        out.append(row)

    fields = list(rows[0].keys()) if rows else []
    if "resolution_reason" not in fields:
        fields.append("resolution_reason")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out)

    applied = 0
    if args.apply_local or args.apply_staging:
        remote = bool(args.apply_staging)
        statements = [importer.statement(r) for r in out if r.get("approved") == "YES"]
        importer.execute(args.wrangler_config.resolve(), args.binding, remote, statements, args.max_file_bytes)
        applied = len(statements)

    print(json.dumps({
        "conflicts": len(out),
        "resolved": resolved,
        "unresolved": unresolved,
        "applied": applied,
        "reasons": dict(sorted(reasons.items())),
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
