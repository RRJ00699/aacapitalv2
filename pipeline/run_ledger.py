"""Schema-tolerant pipeline_step_runs writer. Apply runs only; dry runs never call it."""
from __future__ import annotations
import json

DESIRED = {
    "run_id", "step_name", "started_at", "finished_at", "status", "ipo_count",
    "rows_read", "rows_written", "estimated_cost", "actual_cost", "error_summary",
    "retry_number", "source_freshness",
}


def available_columns(conn) -> set[str]:
    cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='pipeline_step_runs'""")
    return {row[0] for row in cur.fetchall()}


def record_step(conn, event: dict, *, dry_run: bool = False) -> bool:
    if dry_run:
        return False
    columns = available_columns(conn)
    usable = [name for name in DESIRED if name in columns and name in event]
    if not usable:
        return False
    values = [json.dumps(event[name]) if name == "source_freshness" else event[name] for name in usable]
    placeholders = ",".join(["%s"] * len(usable))
    cur = conn.cursor()
    cur.execute(f"INSERT INTO pipeline_step_runs ({','.join(usable)}) VALUES ({placeholders})", values)
    conn.commit()
    return True
