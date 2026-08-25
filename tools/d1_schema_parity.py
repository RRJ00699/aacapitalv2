#!/usr/bin/env python3
"""Compare a production D1 SQLite export with canonical migrations, read-only.

The actual export is always opened ``mode=ro``. Canonical migrations are replayed only
into temporary local SQLite files. No reconciliation SQL is generated or executed.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


SYSTEM_PREFIXES = ("sqlite_",)


def normalize_sql(sql: str | None) -> str | None:
    if not sql:
        return None
    value = re.sub(r"\s+", " ", sql.strip()).casefold()
    return re.sub(r"\s*([(),])\s*", r"\1", value)


def columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    # table_xinfo, unlike table_info, includes generated/hidden columns. `hidden` is
    # 2 or 3 for generated columns in SQLite.
    return [dict(cid=r[0], name=r[1], type=r[2], notnull=r[3], default=r[4],
                 pk=r[5], hidden=r[6])
            for r in conn.execute(f'PRAGMA table_xinfo("{table}")')]


def object_map(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    result = {}
    for kind, name, table, sql in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE type IN ('table','index','trigger') ORDER BY type,name"):
        if name.startswith(SYSTEM_PREFIXES):
            continue
        item = {"kind": kind, "name": name, "table": table,
                "sql": normalize_sql(sql)}
        if kind == "table":
            item["columns"] = columns(conn, name)
        elif kind == "index":
            item["columns"] = [dict(seqno=r[0], cid=r[1], name=r[2], desc=r[3],
                                    coll=r[4], key=r[5])
                               for r in conn.execute(f'PRAGMA index_xinfo("{name}")')]
        result[(kind, name)] = item
    return result


def ledger_names(conn: sqlite3.Connection) -> set[str]:
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'")}
    if "d1_migrations" not in tables:
        return set()
    names = [r[1] for r in conn.execute("PRAGMA table_xinfo('d1_migrations')")]
    column = next((x for x in ("name", "migration_name", "filename") if x in names), None)
    if column is None:
        raise RuntimeError("d1_migrations has no recognized migration-name column")
    return {str(r[0]) for r in conn.execute(f'SELECT "{column}" FROM d1_migrations')}


def migration_files(path: Path) -> list[Path]:
    files = sorted(path.glob("*.sql"))
    if not files:
        raise RuntimeError(f"no canonical migrations found in {path}")
    return files


def is_recorded(filename: str, recorded: set[str]) -> bool:
    stem = Path(filename).stem
    return filename in recorded or stem in recorded or any(
        str(value).startswith(stem.split("_", 1)[0]) for value in recorded)


@dataclass
class Row:
    kind: str
    name: str
    state: str
    required_by: str | None
    deployment_state: str | None
    actual_rows: int | None = None


def compare(actual_path: Path, migrations_path: Path) -> dict:
    actual = sqlite3.connect(f"file:{actual_path}?mode=ro", uri=True)
    recorded = ledger_names(actual)
    files = migration_files(migrations_path)
    origins: dict[tuple[str, str], str] = {}
    with tempfile.NamedTemporaryFile(suffix=".sqlite") as target:
        expected = sqlite3.connect(target.name)
        previous = {}
        for migration in files:
            expected.executescript(migration.read_text(encoding="utf-8"))
            current = object_map(expected)
            for key, value in current.items():
                if key not in previous or previous[key] != value:
                    origins[key] = migration.name
            previous = current
        expected_objects = object_map(expected)
        expected.close()

    actual_objects = object_map(actual)
    rows = []
    for key in sorted(expected_objects.keys() | actual_objects.keys()):
        exp, act = expected_objects.get(key), actual_objects.get(key)
        required = origins.get(key)
        if exp is None:
            state = "EXTRA_ACTUAL"
        elif act is None:
            state = "MISSING_EXPECTED"
        elif exp == act:
            state = "PRESENT_MATCH"
        else:
            state = "PRESENT_DRIFT"
        deployment = None
        if state == "MISSING_EXPECTED" and required:
            deployment = ("ALREADY_RECORDED_BUT_MISSING" if is_recorded(required, recorded)
                          else "NEVER_DEPLOYED")
        count = None
        if act and key[0] == "table":
            count = actual.execute(f'SELECT COUNT(*) FROM "{key[1]}"').fetchone()[0]
        rows.append(Row(key[0], key[1], state, required, deployment, count))
    actual.close()
    return {"actual": str(actual_path), "migrations": [x.name for x in files],
            "recorded_migrations": sorted(recorded),
            "matrix": [asdict(row) for row in rows]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actual_export", type=Path)
    parser.add_argument("--migrations", type=Path, default=Path("d1/migrations"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = compare(args.actual_export, args.migrations)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("STATE\tKIND\tNAME\tREQUIRED_BY\tDEPLOYMENT_STATE\tACTUAL_ROWS")
        for row in report["matrix"]:
            print("\t".join(str(row[x] if row[x] is not None else "") for x in
                ("state", "kind", "name", "required_by", "deployment_state", "actual_rows")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
