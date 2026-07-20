#!/usr/bin/env python3
"""The THREE job lists must stay in sync.

2026-07-18: clicking "Schema sync" returned `unknown job 'schema'` even though
the job existed in job_runner.py AND had a console button. Cause: a THIRD
definition — ALLOWED_JOBS in app/api/admin/jobs/route.ts — rejected it before it
reached the queue.

Three places define the job list:
  1. _scripts/job_runner.py                      JOBS          (VM executes)
  2. app/api/admin/jobs/route.ts                 ALLOWED_JOBS  (API accepts)
  3. app/dashboard/admin/AdminConsoleClient.tsx  buttons       (UI offers)

A job missing from ANY of the three is unusable, with a different failure mode
each time. This test keeps them aligned.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "_scripts" / "job_runner.py"
API = ROOT / "app" / "api" / "admin" / "jobs" / "route.ts"
CONSOLE = ROOT / "app" / "dashboard" / "admin" / "AdminConsoleClient.tsx"
pytestmark = pytest.mark.unit

NO_BUTTON_OK = {"pipeline_weekly", "universe_candles", "levels"}


def _runner():
    s = RUNNER.read_text(encoding="utf-8")
    b = s[s.index("JOBS = {"):s.index("def ensure_table")]
    return set(re.findall(r'"([a-z_]+)":\s*\[', b))


def _api():
    s = API.read_text(encoding="utf-8")
    i = s.index("ALLOWED_JOBS")
    return set(re.findall(r'"([a-z_]+)"', s[i:s.index("]);", i)]))


def _console():
    return set(re.findall(r'key:\s*"([a-z_]+)"', CONSOLE.read_text(encoding="utf-8")))


def test_api_accepts_every_runner_job():
    missing = _runner() - _api()
    assert not missing, f'job(s) the VM can run but the API rejects as "unknown job": {sorted(missing)}'


def test_api_accepts_every_console_button():
    missing = _console() - _api()
    assert not missing, f"console button(s) the API will reject: {sorted(missing)}"


def test_console_offers_every_important_job():
    missing = (_runner() - _console()) - NO_BUTTON_OK
    assert not missing, f"job(s) invisible from the phone: {sorted(missing)}"


def test_api_has_no_phantom_jobs():
    phantom = _api() - _runner()
    assert not phantom, f"API allows job(s) the VM cannot run: {sorted(phantom)}"
