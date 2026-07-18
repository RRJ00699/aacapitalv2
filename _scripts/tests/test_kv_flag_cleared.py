#!/usr/bin/env python3
"""The KV job-flag must be CLEARED when the queue drains.

2026-07-18: `_clear_flag()` was defined in job_runner.py but NEVER CALLED. The
flag read `pending:true` forever after the first enqueue, so the minute-cron
runner opened a Neon connection EVERY MINUTE — silently defeating the
scale-to-zero design the flag exists to protect.

Evidence: `curl /api/admin/job-flag` returned {"ok":true,"pending":true} with an
empty job_runs queue.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "_scripts" / "job_runner.py"
pytestmark = pytest.mark.unit


def _src():
    return RUNNER.read_text(encoding="utf-8")


def test_clear_flag_is_actually_called():
    s = _src()
    assert "def _clear_flag" in s, "_clear_flag helper missing"
    assert re.search(r"^\s+_clear_flag\(\)", s, re.M), \
        "_clear_flag defined but NEVER CALLED — flag stays pending forever"


def test_flag_cleared_on_empty_queue_branch():
    s = _src()
    i = s.index("if not claimed")
    assert "_clear_flag()" in s[i:i + 500], "flag not cleared when the queue drains"


def test_flag_check_precedes_db_import():
    s = _src()
    assert s.index("_flag_pending()") < s.index("import psycopg2"), \
        "flag check must run before psycopg2 import"
