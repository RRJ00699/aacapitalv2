#!/usr/bin/env python3
"""Every pipeline step must point at a script that EXISTS.

2026-07-18 stress test: 3 of 41 lean-pipeline steps referenced scripts that are
nowhere in the repo —
    sector cleanup            -> fix_sectors.py            (does not exist)
    peer PE (self-computed)   -> compute_peer_pe.py        (does not exist)
    quality flags             -> compute_quality_flags.py  (does not exist)

The peer-PE one mattered: the real script is `fetch_peer_pe.py`, so that step
failed on EVERY run. That is why peer_median_pe sat at 58% and Fair Value read
"unavailable" on the cards — a broken step, invisible because the pipeline kept
going.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_scripts"
pytestmark = pytest.mark.unit
PIPELINES = ["run_ipo_pipeline_lean.py", "run_ipo_pipeline.py"]


def _steps(pipeline):
    src = (SCRIPTS / pipeline).read_text(encoding="utf-8")
    live = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
    return re.findall(r'step\(\s*"([^"]+)"\s*,\s*\[\s*"([^"]+\.py)"', live)


def _exists(script):
    # steps may carry a subdir prefix, e.g. "ipo/fetch_nse_ipos.py"
    if (SCRIPTS / script).exists():
        return True
    name = pathlib.Path(script).name
    return any(p.name == name for p in SCRIPTS.rglob("*.py")
               if "_archive" not in p.parts)


@pytest.mark.parametrize("pipeline", PIPELINES)
def test_all_step_scripts_exist(pipeline):
    if not (SCRIPTS / pipeline).exists():
        pytest.skip(f"{pipeline} absent")
    missing = [(name, s) for name, s in _steps(pipeline) if not _exists(s)]
    assert not missing, (
        f"{pipeline}: step(s) point at scripts that do not exist — they fail every "
        f"run: {missing}"
    )


def test_peer_pe_step_uses_the_real_script():
    """Fair Value depends on peer_median_pe. Guard the exact regression."""
    src = (SCRIPTS / "run_ipo_pipeline_lean.py").read_text(encoding="utf-8")
    live = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
    assert "compute_peer_pe.py" not in live, "phantom compute_peer_pe.py is back"
    assert "fetch_peer_pe.py" in live, "peer-PE step missing — Fair Value will starve"
