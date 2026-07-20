#!/usr/bin/env python3
"""Every job in the runner whitelist must have a button in the Admin console.

2026-07-18: six jobs (schema, verdicts, score, quality, smoke, sbi_haiku) were
added to job_runner's JOBS whitelist but NOT to AdminConsoleClient's button list.
Runnable in principle, invisible in practice — the owner could not find "the
schema job" because no button existed. The console is the phone's only route to
the VM, so a whitelist entry with no button is a job that does not exist.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "_scripts" / "job_runner.py"
CONSOLE = ROOT / "app" / "dashboard" / "admin" / "AdminConsoleClient.tsx"
pytestmark = pytest.mark.unit

NO_BUTTON_OK = {"pipeline_weekly", "universe_candles", "levels"}


def _whitelist():
    s = RUNNER.read_text(encoding="utf-8")
    block = s[s.index("JOBS = {"):s.index("def ensure_table")]
    return set(re.findall(r'"([a-z_]+)":\s*\[', block))


def _buttons():
    return set(re.findall(r'key:\s*"([a-z_]+)"', CONSOLE.read_text(encoding="utf-8")))


def test_every_button_maps_to_a_real_job():
    orphan = _buttons() - _whitelist()
    assert not orphan, f"console button(s) with no job_runner entry: {sorted(orphan)}"


def test_important_jobs_have_buttons():
    missing = (_whitelist() - _buttons()) - NO_BUTTON_OK
    assert not missing, (
        f"job(s) runnable but INVISIBLE from the phone (no console button): {sorted(missing)}")


def test_schema_job_is_present_and_first_class():
    assert "schema" in _buttons(), "no Schema sync button — DDL cannot be applied from a phone"
    assert "schema" in _whitelist(), "schema job missing from the runner whitelist"
