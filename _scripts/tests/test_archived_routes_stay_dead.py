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
    # Phase 3 — 2026-07-20 audit cleanup (zero callers across app/components/
    # _scripts/.github; levels+intelligence never fetched by any UI; pipeline/
    # status queried archived equity tables; db/init verified equity tables).
    ("/api/ipo/levels",           "_archive/routes/api-ipo-levels-route.ts.txt"),
    ("/api/ipo/intelligence",     "_archive/routes/api-ipo-intelligence-route.ts.txt"),
    ("/api/pipeline/status",      "_archive/routes/api-pipeline-status-route.ts.txt"),
    ("/api/db/init",              "_archive/routes/api-db-init-route.ts.txt"),
]

# Explicitly KEPT despite zero UI refs — owner decision 2026-07-18. Guarded so a
# future sweep can't quietly remove them.
# Phase 2 — archived pages (orphaned, equity-era). Same preserve-not-delete rule.
ARCHIVED_PAGES = [
    ("app/today/page.tsx",                    "_archive/pages/app-today-page.tsx.txt"),
    ("components/features/today-screen.tsx",  "_archive/pages/today-screen.tsx.txt"),
    # Phase 3 — 2026-07-20: the pre-cutover command center. /dashboard/ipo was
    # reachable only via non-admin redirects (now pointed at /dashboard/ipo2 per
    # the cutover note in app/ipo/page.tsx); the component chain below existed
    # solely for it. IpoSignalCard also carried the REJECTED 10/30 gap bands.
    ("app/dashboard/ipo/page.tsx",                   "_archive/pages/dashboard-ipo-page.tsx.txt"),
    ("app/dashboard/ipo/IPOCommandCenterClient.tsx", "_archive/pages/IPOCommandCenterClient.tsx.txt"),
    ("components/ipo/IpoSignalCard.tsx",             "_archive/pages/IpoSignalCard.tsx.txt"),
    ("components/ipo/PostListingDashboard.tsx",      "_archive/pages/PostListingDashboard.tsx.txt"),
    ("components/ipo/IpoCommandCenter.tsx",          "_archive/pages/IpoCommandCenter.tsx.txt"),
    ("components/ipo/IpoCapitalProtectionPanel.tsx", "_archive/pages/IpoCapitalProtectionPanel.tsx.txt"),
    ("components/features/ipo_play_selector.py",     "_archive/pages/components-ipo_play_selector.py.txt"),
]

# Phase 3 — 2026-07-20: equity-era lib residue with ZERO importers at HEAD
# (verified per-module: grep across app/components/lib). Preserved as .txt.
ARCHIVED_LIB = [
    ("@/lib/ipoSignal",          "_archive/lib/ipoSignal.ts.txt"),
    ("@/lib/watchlist",          "_archive/lib/watchlist.ts.txt"),
    ("@/lib/workboard-config",   "_archive/lib/workboard-config.ts.txt"),
    ("@/lib/design-tokens",      "_archive/lib/design-tokens.ts.txt"),
    ("@/lib/design/tokens",      "_archive/lib/design-tokens-dir.ts.txt"),
    ("@/lib/scrapers",           "_archive/lib/scrapers-index.ts.txt"),
    ("@/lib/ai",                 "_archive/lib/ai-index.ts.txt"),
    ("@/lib/constants/stocks",   "_archive/lib/constants-stocks.ts.txt"),
    ("@/lib/providers",          "_archive/lib/providers-index.ts.txt"),
    ("@/lib/intelligence/earnings-score",        "_archive/lib/intelligence-earnings-score.ts.txt"),
    ("@/lib/intelligence/amfi-score",            "_archive/lib/intelligence-amfi-score.ts.txt"),
    ("@/lib/intelligence/commentary-score",      "_archive/lib/intelligence-commentary-score.ts.txt"),
    ("@/lib/intelligence/market-quality",        "_archive/lib/intelligence-market-quality.ts.txt"),
    ("@/lib/intelligence/historical-similarity", "_archive/lib/intelligence-historical-similarity.ts.txt"),
    ("@/lib/ipo/tape",           "_archive/lib/ipo-tape.ts.txt"),
    ("@/lib/ipo/anchors",        "_archive/lib/ipo-anchors.ts.txt"),
    ("@/lib/ipo/pipeline",       "_archive/lib/ipo-pipeline.ts.txt"),
    ("@/lib/ipo/gmp-disappointment", "_archive/lib/ipo-gmp-disappointment.ts.txt"),
    ("@/lib/ipo/scoring",        "_archive/lib/ipo-scoring.ts.txt"),
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


@pytest.mark.parametrize("import_path,archived_file", ARCHIVED_LIB)
def test_archived_lib_never_reimported(import_path, archived_file):
    """No live TS file may import an archived lib module."""
    hits = []
    for d in ("app", "components", "lib"):
        base = ROOT / d
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in {".ts", ".tsx"}:
                continue
            if "node_modules" in f.parts or "_archive" in f.parts:
                continue
            try:
                src = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if f'"{import_path}"' in src or f"'{import_path}'" in src:
                hits.append(str(f.relative_to(ROOT)))
    assert not hits, f"{import_path} archived but still imported by: {hits}"


@pytest.mark.parametrize("_i,archived_file", ARCHIVED_LIB)
def test_archived_lib_is_preserved(_i, archived_file):
    p = ROOT / archived_file
    assert p.exists() and p.stat().st_size > 0, \
        f"{archived_file} missing — archive must preserve, never delete"
