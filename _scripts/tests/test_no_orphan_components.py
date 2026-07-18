#!/usr/bin/env python3
"""Guard: no component may sit in the tree unreferenced.

Phase 2 of the IPO-only cleanup archived 10 components that nothing imported.
Dead components are worse than dead routes: they pass typecheck, ship in the
bundle, and rot until someone edits one by mistake.

This test scans every component's EXPORT NAMES (not just its filename — a file
can be imported under a different name) and fails if nothing references them.

ALLOWLIST: entry points and framework-required files that are legitimately
referenced only by Next.js conventions, not by an import statement.
"""
import pathlib
import re
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

SEARCH_DIRS = ["app", "components"]
EXPORT_RE = re.compile(r"export\s+(?:default\s+)?(?:function|const|class)\s+([A-Za-z0-9_]+)")

# Referenced only by Next.js convention or by string, not by import.
ALLOWLIST = {"AppShell", "AppNav", "MarketsSidebar"}


def _sources():
    for d in SEARCH_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in base.rglob("*.tsx"):
            if "node_modules" in f.parts or "_archive" in f.parts:
                continue
            yield f


def _all_text():
    return {f: f.read_text(encoding="utf-8", errors="ignore") for f in _sources()}


def test_every_component_is_referenced():
    texts = _all_text()
    orphans = []
    for f, src in texts.items():
        if "/components/" not in f.as_posix():
            continue
        names = set(EXPORT_RE.findall(src)) - ALLOWLIST
        if not names:
            continue
        referenced = False
        for other, osrc in texts.items():
            if other == f:
                continue
            if any(re.search(rf"\b{re.escape(n)}\b", osrc) for n in names):
                referenced = True
                break
        if not referenced:
            orphans.append(f"{f.relative_to(ROOT)} (exports: {sorted(names)})")
    assert not orphans, (
        "Unreferenced components found — archive them to _archive/components/ "
        f"or wire them up:\n  " + "\n  ".join(orphans)
    )


def test_archived_components_are_preserved():
    """Preserve-not-delete: the archive must still hold the files."""
    arch = ROOT / "_archive" / "components"
    assert arch.exists(), "_archive/components missing"
    files = list(arch.glob("*.tsx"))
    assert len(files) >= 10, f"expected the archived components to persist, found {len(files)}"
    for f in files:
        assert f.stat().st_size > 0, f"{f.name} is empty"


def test_archived_components_not_imported():
    """Nothing in live code may import from _archive/."""
    bad = []
    for f, src in _all_text().items():
        if "_archive" in src and "from" in src:
            for line in src.splitlines():
                if "_archive" in line and ("import" in line or "require" in line):
                    bad.append(f"{f.relative_to(ROOT)}: {line.strip()[:80]}")
    assert not bad, f"live code imports from _archive: {bad}"
