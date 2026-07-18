"""Guard: the equity multibagger .ts engines stay archived.

Last equity-platform residue on the .ts side — the multibagger engines and the
signal-sync that fed technical_signals. None are imported by the app or any wired
script (only package.json's similarity npm-script referenced one; removed).

Fails on the pre-change tree (engines under _scripts/engines/), passes after.
"""
import json
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

ARCHIVED_TS = [
    "engines/historical_multibagger_miner.ts",
    "engines/indicator_calculator.ts",
    "engines/multibagger_screener.ts",
    "engines/multibagger_similarity_engine.ts",
    "sync-signals-to-neon.ts",
]


def test_equity_engines_not_in_scripts():
    present = [f for f in ARCHIVED_TS if (ROOT / "_scripts" / f).exists()]
    assert not present, f"equity .ts residue still under _scripts/: {present}"


def test_equity_engines_preserved_in_archive():
    missing = [f for f in ARCHIVED_TS if not (ROOT / "_archive" / "_scripts" / (f + ".txt")).exists()]
    assert not missing, f"archived engines missing from _archive/: {missing}"


def test_similarity_npm_script_removed():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "similarity:multibagger" not in pkg.get("scripts", {}), \
        "similarity:multibagger npm-script points at an archived engine — remove it"
