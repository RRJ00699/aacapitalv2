#!/usr/bin/env python3
"""Guard: archived routes must not be referenced anywhere in live code.

Phase 1 of the IPO-only cleanup archived routes that had ZERO callers of any
kind — not UI, not VM scripts, not workflows. This test fails if any of them is
referenced again, or if the archived file is deleted rather than preserved.

Rule from the cleanup handover: nothing is deleted, everything moves to
_archive/ and stays one `git revert` away.
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

# (archived api path, preserved file) — archived because no caller existed
ARCHIVED = [
    # Phase 1 — provably dead (self-declared retired / unfinished stub)
    ("/api/cron/premarket-brief", "_archive/routes/api-cron-premarket-brief-route.ts.txt"),
    ("/api/ipo/tape",             "_archive/routes/api-ipo-tape-route.ts.txt"),
    # Phase 1b — owner-approved 2026-07-18 (zero callers across app/components/
    # _scripts/.github/docs). listing-day superseded by live-preopen; memo+drhp
    # superseded by the rhp_sonnet pipeline; gmp/scrape/upload/subscription were
    # browser-era admin fallbacks the pipeline now covers.
    ("/api/ipo/listing-day",      "_archive/routes/api-ipo-listing-day-route.ts.txt"),
    ("/api/ipo/memo",             "_archive/routes/api-ipo-memo-route.ts.txt"),
    ("/api/ipo/drhp",             "_archive/routes/api-ipo-drhp-route.ts.txt"),
    ("/api/ipo/gmp-refresh",      "_archive/routes/api-ipo-gmp-refresh-route.ts.txt"),
    ("/api/ipo/gmp",              "_archive/routes/api-ipo-gmp-route.ts.txt"),
    ("/api/ipo/scrape",           "_archive/routes/api-ipo-scrape-route.ts.txt"),
    ("/api/ipo/upload",           "_archive/routes/api-ipo-upload-route.ts.txt"),
    ("/api/ipo/subscription",     "_archive/routes/api-ipo-subscription-route.ts.txt"),
]

# Explicitly KEPT despite zero UI refs — owner decision 2026-07-18. Guarded so a
# future sweep can't quietly remove them.
# Phase 2 — archived pages (orphaned, equity-era). Same preserve-not-delete rule.
ARCHIVED_PAGES = [
    ("app/today/page.tsx",                    "_archive/pages/app-today-page.tsx.txt"),
    ("components/features/today-screen.tsx",  "_archive/pages/today-screen.tsx.txt"),
]

KEPT_DESPITE_NO_UI_REF = [
    "app/api/ipo/monitor/route.ts",      # "listed weak BUT strong quality" — owner: keep
    "app/dashboard/tracker/page.tsx",    # interruption log — owner: keep, wired into Admin
    "app/api/tracker/route.ts",          # its backend (distraction_log)
    "app/api/market-regime/route.ts",    # required per IPO_BUSINESS_REQUIREMENTS 2C.10
    "app/api/admin/job-flag/route.ts",   # VM job_runner polls this every minute
    "app/api/health/route.ts",           # DB-free liveness probe
]
LIVE_DIRS = ["app", "components", "_scripts", ".github"]


@pytest.mark.parametrize("api_path,archived_file", ARCHIVED)
def test_archived_route_has_no_live_reference(api_path, archived_file):
    hits = []
    for d in LIVE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in {".ts", ".tsx", ".py", ".yml", ".yaml"}:
                continue
            if "node_modules" in f.parts or "_archive" in f.parts:
                continue
            if f.name == pathlib.Path(__file__).name:   # this test lists the paths itself
                continue
            try:
                if api_path in f.read_text(encoding="utf-8", errors="ignore"):
                    hits.append(str(f.relative_to(ROOT)))
            except Exception:
                pass
    assert not hits, f"{api_path} was archived but is still referenced in: {hits}"


@pytest.mark.parametrize("api_path,archived_file", ARCHIVED)
def test_archived_route_is_preserved_not_deleted(api_path, archived_file):
    p = ROOT / archived_file
    assert p.exists(), f"{archived_file} missing — archive must preserve, never delete"
    assert p.stat().st_size > 0, f"{archived_file} is empty"


@pytest.mark.parametrize("api_path,_f", ARCHIVED)
def test_archived_route_no_longer_served(api_path, _f):
    """The route.ts must be gone from app/api or Next will still serve it."""
    route = ROOT / "app" / (api_path.lstrip("/") ) / "route.ts"
    assert not route.exists(), f"{api_path} still has a live route.ts at {route}"


@pytest.mark.parametrize("path", KEPT_DESPITE_NO_UI_REF)
def test_kept_routes_still_exist(path):
    """These have no UI reference but ARE alive (VM/cron callers, or an explicit
    owner decision). A future cleanup must not remove them."""
    assert (ROOT / path).exists(), f"{path} was removed — it is explicitly KEPT"


@pytest.mark.parametrize("live_path,archived_file", ARCHIVED_PAGES)
def test_archived_page_removed_and_preserved(live_path, archived_file):
    """/today was the equity-era dashboard: its nav entry was commented out and
    its only fetches were to routes that never existed (removed in #232)."""
    assert not (ROOT / live_path).exists(), f"{live_path} still live"
    p = ROOT / archived_file
    assert p.exists() and p.stat().st_size > 0, f"{archived_file} not preserved"


def test_no_dangling_today_references():
    """No live file may reference the archived Today screen — including a
    commented-out nav entry, which is how it lingered unnoticed."""
    hits = []
    for d in ("app", "components"):
        base = ROOT / d
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in {".ts", ".tsx"}:
                continue
            if "node_modules" in f.parts or "_archive" in f.parts:
                continue
            t = f.read_text(encoding="utf-8", errors="ignore")
            if "TodayScreen" in t or "today-screen" in t:
                hits.append(str(f.relative_to(ROOT)))
    assert not hits, f"dangling Today references: {hits}"
