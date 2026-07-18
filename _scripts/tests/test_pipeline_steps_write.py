#!/usr/bin/env python3
"""Steps that WRITE must be invoked with --apply.

2026-07-18: `market regime + VIX (today)` called backfill_market_regimes.py with
no flags. That script defaults to DRY-RUN, so the step "succeeded" every night
and wrote nothing — market_regimes froze at 2026-07-03 while the business spec
(§2C.10) lists regime + VIX as required decision inputs. A green pipeline step
that silently writes nothing is the worst kind of failure.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEAN = ROOT / "_scripts" / "run_ipo_pipeline_lean.py"
pytestmark = pytest.mark.unit

# scripts that default to dry-run and MUST be called with --apply in the pipeline
DRY_RUN_BY_DEFAULT = [
    "backfill_market_regimes.py",
    "compute_quality_score.py",
    "ipo_score.py",
    "compute_verdicts.py",
]


def _steps():
    src = LEAN.read_text(encoding="utf-8")
    return re.findall(r'step\(\s*"([^"]+)"\s*,\s*\[([^\]]*)\]', src)


@pytest.mark.parametrize("script", DRY_RUN_BY_DEFAULT)
def test_write_steps_pass_apply(script):
    hits = [(name, args) for name, args in _steps() if script in args]
    if not hits:
        pytest.skip(f"{script} not in the lean pipeline")
    for name, args in hits:
        assert "--apply" in args, (
            f'step "{name}" runs {script} WITHOUT --apply — it will dry-run and '
            f"write nothing while reporting success"
        )


def test_script_actually_defaults_to_dry_run():
    """Guard the premise: if these scripts ever default to writing, this test's
    reasoning changes and it should be revisited."""
    for s in DRY_RUN_BY_DEFAULT:
        p = ROOT / "_scripts" / s
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        if "--apply" in src:
            assert "action=\"store_true\"" in src or "action='store_true'" in src, \
                f"{s}: --apply is not a store_true flag; dry-run assumption unclear"
