#!/usr/bin/env python3
"""Tests for vm_verify.py (2026-07-21). Offline — pure functions executed for
real; reality-over-configuration rules contract-checked."""
import datetime as dt
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("vm_verify", os.path.join(ROOT, "vm_verify.py"))
vv = importlib.util.module_from_spec(spec); spec.loader.exec_module(vv)


def _read():
    return open(os.path.join(ROOT, "vm_verify.py"), encoding="utf-8").read()


# ── pure functions, executed ────────────────────────────────────────────────
def test_slugify_matches_repo_convention():
    assert vv.slugify("Lohia Corp Limited") == "lohia-corp"
    assert vv.slugify("Indo-MIM Ltd") == "indo-mim"
    assert vv.slugify("Laser Power & Infra Pvt Ltd") == "laser-power-infra"

def test_tz_triple_is_dst_aware_and_dual_labeled():
    s = vv.tz_triple(8, 30)
    assert "08:30 IST" in s and "US-Central" in s
    # 08:30 IST is always the previous US-Central day (22:00 CDT / 21:00 CST)
    assert "(" in s, "prev-day marker expected for early-IST times"

def test_cron_regex_parses_real_vm_lines():
    m = vv.CRON_RE.match("30 8 * * 1-5 cd /root/aac && venv/bin/python _scripts/run_ipo_pipeline_lean.py")
    assert m and m.group(1) == "30" and m.group(2) == "8"
    assert vv.CRON_RE.match("* * * * * cd /root/aac && x") is None  # every-minute line skipped safely

def test_q_returns_none_not_success_without_db():
    assert vv.q(None, "SELECT 1") is None, "no DB must map to NOT VERIFIED, never success"


# ── reality-over-configuration contracts ────────────────────────────────────
def test_never_ran_is_failed_or_not_verified_never_success():
    src = _read()
    assert "cron_exec = CONF if steps else FAIL" in src, \
        "scheduled-but-zero-runs must be FAILED (cron broken), not success"
    assert ', NV = ' in src or 'NV = "NOT VERIFIED"' in src or '"NOT VERIFIED"' in src

def test_five_evidence_columns_and_states_present():
    src = _read()
    for token in ("CONFIRMED", "PARTIAL", "PENDING", "FAILED", "NOT VERIFIED"):
        assert token in src
    for col in ("CODE", "CRON", "RUN", "DB", "UI"):
        assert col in src

def test_discovery_is_query_not_hardcoded_names():
    src = _read()
    assert "FROM ipo_intelligence" in src and "LIMIT 2" in src
    for banned in ("Lohia", "Indo-MIM", "Caliber", "LASERPOWER"):
        assert banned not in src, f"hard-coded IPO name: {banned}"

def test_exit_code_covers_critical_stages_only():
    src = _read()
    assert "return 1 if crit_fail else 0" in src
    assert "PENDING" in src and "never fails" in src.lower() or "not a failure" in src.lower()

def test_size_pending_ipos_not_hidden_by_discovery():
    src = _read()
    assert "issue_size_cr >= 200" not in src, \
        "discovery matrix must SHOW sub-200/size-pending rows so gaps are visible (UI filter is separate)"

def test_read_only_no_ddl():
    src = _read()
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE", "ALTER "):
        assert verb not in src, f"vm_verify must be read-only, found {verb}"
