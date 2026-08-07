#!/usr/bin/env python3
"""_scripts/lib/stage_state.py — PR-C: per-IPO pipeline stage truth.

record() upserts ipo_stage_state (created by schema_sync). Stages/states per
docs/specifications/PROVENANCE_DESIGN.md §2-3; states: CONFIRMED / PARTIAL / PENDING /
FAILED. NEVER raises — observability must not break the pipeline. attempt_count
increments on every non-CONFIRMED write; next_retry_at (minutes) lets fetchers
skip an IPO until its backoff elapses (bounded retries, one failed IPO never
blocks another).
"""
from __future__ import annotations


def _ipo_id(cur, company: str):
    cur.execute(
        """SELECT id FROM ipo_intelligence
           WHERE regexp_replace(lower(company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')
               = regexp_replace(lower(%s),'(ltd|limited|and|&)|[^a-z0-9]','','g')
           LIMIT 1""", (company,))
    r = cur.fetchone()
    return r[0] if r else None


def record(conn, company: str, stage: str, status: str, *, error: str | None = None,
           retry_minutes: int | None = None, input_fp: str | None = None,
           output_fp: str | None = None, version: str | None = None) -> bool:
    """True if a row was written. Own transaction; swallows every failure."""
    try:
        cur = conn.cursor()
        iid = _ipo_id(cur, company)
        if iid is None:
            return False
        cur.execute(
            """INSERT INTO ipo_stage_state (ipo_id, stage, status, attempt_count,
                   started_at, completed_at, last_error, next_retry_at,
                   input_fingerprint, output_fingerprint, pipeline_version)
               VALUES (%s,%s,%s,1, NOW(),
                       CASE WHEN %s='CONFIRMED' THEN NOW() END, %s,
                       CASE WHEN %s IS NOT NULL THEN NOW() + (%s || ' minutes')::interval END,
                       %s,%s,%s)
               ON CONFLICT (ipo_id, stage) DO UPDATE SET
                   status = EXCLUDED.status,
                   attempt_count = ipo_stage_state.attempt_count
                       + CASE WHEN EXCLUDED.status='CONFIRMED'
                              AND ipo_stage_state.status='CONFIRMED' THEN 0 ELSE 1 END,
                   completed_at = CASE WHEN EXCLUDED.status='CONFIRMED' THEN NOW()
                                       ELSE ipo_stage_state.completed_at END,
                   last_error = EXCLUDED.last_error,
                   next_retry_at = EXCLUDED.next_retry_at,
                   input_fingerprint = COALESCE(EXCLUDED.input_fingerprint, ipo_stage_state.input_fingerprint),
                   output_fingerprint = COALESCE(EXCLUDED.output_fingerprint, ipo_stage_state.output_fingerprint),
                   pipeline_version = COALESCE(EXCLUDED.pipeline_version, ipo_stage_state.pipeline_version)""",
            (iid, stage, status, status, (error or "")[:400] or None,
             retry_minutes, retry_minutes, input_fp, output_fp, version))
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
