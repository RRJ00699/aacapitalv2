#!/usr/bin/env python3
"""Every phone-triggerable job must be runnable and safe.

The admin job console is the ONLY way to run VM work from a phone. A whitelist
entry pointing at a missing script, or a writer missing --apply, fails silently
in a place the owner cannot debug without a laptop.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "_scripts" / "job_runner.py"
pytestmark = pytest.mark.unit

DRY_RUN_DEFAULT = {"compute_verdicts.py", "ipo_score.py", "compute_quality_score.py",
                   "rhp_auto.py", "ipomatrix_ingest.py"}


def _jobs():
    s = RUNNER.read_text(encoding="utf-8")
    block = s[s.index("JOBS = {"):s.index("def ensure_table")]
    return {m[0]: re.findall(r'"([^"]+)"', m[1])
            for m in re.findall(r'"([a-z_]+)":\s*\[([^\]]*)\]', block)}


def test_every_job_script_exists():
    missing = {j: a[0] for j, a in _jobs().items()
               if a and a[0].endswith(".py") and not (ROOT / a[0]).exists()}
    assert not missing, f"job whitelist points at missing script(s): {missing}"


def test_write_jobs_pass_apply():
    """A job that dry-runs reports success and changes nothing — invisible from a phone."""
    bad = []
    for job, args in _jobs().items():
        if not args:
            continue
        script = pathlib.Path(args[0]).name
        if script in DRY_RUN_DEFAULT and "--apply" not in args:
            bad.append(f"{job} -> {script}")
    assert not bad, f"job(s) will dry-run and silently write nothing: {bad}"


def test_legacy_duplicate_jobs_are_not_phone_triggerable():
    jobs = _jobs()
    for retired in ("verdicts", "score", "quality", "sbi_download", "sbi_haiku"):
        assert retired not in jobs


def test_no_job_shells_out_unsafely():
    s = RUNNER.read_text(encoding="utf-8")
    assert "shell=True" not in s, "job_runner must not use shell=True with job args"
