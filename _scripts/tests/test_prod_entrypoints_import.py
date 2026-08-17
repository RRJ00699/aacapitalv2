"""Guard: the npm prod:* entrypoints must import on a CLEAN checkout.

Regression for the archived-import break found by PR #338's quarantine audit.
`_scripts/prod/kite_sync_and_predict.py` does `from env_utils import ...` at module
scope. The Phase 4B quarantine moved `env_utils.py` into `_archive/scripts/prod/`
as UNREACHABLE, which it never was — the caller-graph resolver could not see bare
sibling imports below the top level. Nothing failed locally because a stale, tracked
`_scripts/prod/__pycache__/env_utils.cpython-312.pyc` sat next to the caller. On a
fresh clone every one of `npm run prod:market`, `prod:ipo`, and `prod:all` died with
`ModuleNotFoundError: No module named 'env_utils'`.

These tests run the entrypoint in a SUBPROCESS with `-B` and a scrubbed environment
so no bytecode cache, no inherited `PYTHONPATH`, and no already-imported module can
hide a missing file — importing in-process would not reproduce the bug.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

# Every _scripts entrypoint reachable from a package.json script.
ENTRYPOINTS = ["_scripts/prod/kite_sync_and_predict.py"]


def _clean_env():
    """Environment with nothing that could satisfy an import by accident."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        # Present but deliberately unusable: the import must not be gated on it,
        # and the script must not connect while merely being imported.
        "DATABASE_URL": "postgresql://import-test-never-connect",
    }
    return {k: v for k, v in env.items() if v}


def test_package_json_prod_scripts_point_at_files_that_exist():
    scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    prod = {name: cmd for name, cmd in scripts.items() if name.startswith("prod:")}
    assert prod, "package.json lost its prod:* scripts"
    missing = []
    for name, command in prod.items():
        for token in command.split():
            if token.endswith(".py") and not (ROOT / token).is_file():
                missing.append(f"{name}: {token}")
    assert not missing, "package.json prod script points at a missing file: " + ", ".join(missing)


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_prod_entrypoint_imports_with_no_bytecode_cache(entrypoint):
    """Fails on the pre-fix tree with ModuleNotFoundError; passes after."""
    assert (ROOT / entrypoint).is_file(), f"{entrypoint} does not exist"
    completed = subprocess.run(
        [sys.executable, "-B", "-c",
         "import importlib.util, sys, pathlib\n"
         f"path = pathlib.Path({str(ROOT)!r}) / {entrypoint!r}\n"
         # Reproduce how Python actually runs it: the script's own directory is
         # sys.path[0]. Anything the module needs must resolve from there or the
         # repo root, never from _archive/ or a stale __pycache__.
         "sys.path.insert(0, str(path.parent))\n"
         "sys.argv = [str(path)]\n"
         "spec = importlib.util.spec_from_file_location('prod_entrypoint_under_test', path)\n"
         "module = importlib.util.module_from_spec(spec)\n"
         "spec.loader.exec_module(module)\n",
         ],
        cwd=ROOT, capture_output=True, text=True, env=_clean_env(), timeout=120,
    )
    assert completed.returncode == 0, (
        f"{entrypoint} does not import on a clean path — this is what a fresh clone sees.\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def test_no_bytecode_or_pycache_is_tracked():
    """The stale .pyc that masked the break must never come back."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
    )
    tracked = [p.decode("utf-8") for p in completed.stdout.split(b"\0") if p]
    offenders = sorted(
        path for path in tracked
        if path.endswith((".pyc", ".pyo")) or "__pycache__/" in path
    )
    assert not offenders, "compiled bytecode is tracked in git:\n" + "\n".join(offenders)


def test_no_production_script_imports_from_the_archive_or_quarantine():
    """A production module must never be reachable only from a quarantine tree."""
    sys.path.insert(0, str(ROOT / "tools"))
    import scripts_caller_graph as graph

    keep = graph.analyze(ROOT).production().keep
    orphans = []
    for rel in sorted(keep):
        source = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if ("_archive/" in stripped or "compatibility/" in stripped) and (
                stripped.startswith(("import ", "from ")) or "sys.path" in stripped
            ):
                orphans.append(f"{rel}: {stripped}")
    assert not orphans, "production code reaches into a quarantine tree:\n" + "\n".join(orphans)
