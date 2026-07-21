#!/usr/bin/env python3
"""feat/ux-premium UAT contracts: token system, primitives, states,
shortcuts, a11y, responsiveness — pinned so the system can't drift."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _read(*p):
    return open(os.path.join(REPO, *p), encoding="utf-8").read()


def test_semantic_tokens_defined_once():
    css = _read("app", "globals.css")
    for tok in ("--s-good:", "--s-watch:", "--s-junk:", "--m-fast:", "--focus-ring:", "--sp-4:"):
        assert css.count(tok) == 1, f"{tok} must be defined exactly once"
    assert ":focus-visible" in css and "prefers-reduced-motion" in css
    assert ".aac-skeleton" in css and ".aac-sticky-decision" in css and ".aac-tiles" in css


def test_theme_exports_tone_system():
    th = _read("lib", "theme.ts")
    for exp in ("export const VARS", "export const TONE", "export const toneFor", "export const MOTION"):
        assert exp in th
    # one meaning per word: GOOD/CONFIRMED/BUY are good; JUNK/FAILED/SKIP are junk
    assert '"GOOD", "CONFIRMED", "BUY"' in th and '"JUNK", "FAILED", "SKIP"' in th


def test_primitives_exist_and_consume_tokens_only():
    src = _read("components", "ui", "primitives.tsx")
    for comp in ("function Badge", "function Card", "function Stat", "function SectionHeader",
                 "function ActionButton", "function Skeleton", "function EmptyState",
                 "function ErrorState", "function Expander"):
        assert comp in src, f"missing primitive: {comp}"
    hexes = [h for h in re.findall(r"#[0-9A-Fa-f]{3,8}\b", src) if h.lower() != "#fff"]
    assert hexes == [], f"primitives must consume tokens, found raw hex: {hexes}"


def test_search_is_token_converged():
    src = _read("components", "features", "ipo-search.tsx")
    assert 'from "@/lib/theme"' in src
    body = src.split("import", 1)[1]
    hexes = re.findall(r'"#[0-9A-Fa-f]{6}"', body)
    assert hexes == [], f"search must not hardcode palette hexes: {hexes}"
    assert "aac-skeleton" in src


def test_dashboard_states_upgraded():
    src = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "ErrorState" in src and "onRetry" in src, "degraded mode must offer retry"
    assert "<Skeleton" in src, "loading must show skeletons, not blank"
    assert "EmptyState" in src and "Show all" in src, "empty filter needs a way back"
    assert 'className="aac-sticky-decision"' in src, "Live decision hero must be sticky"


def test_keyboard_shortcuts_and_help():
    shell = _read("components", "app-shell", "AppShell.tsx")
    assert 'e.key === "/"' in shell and 'e.key === "g"' in shell and 'e.key === "?"' in shell
    assert 'role="dialog"' in shell and "Keyboard" in shell
    assert 'el.tagName === "INPUT"' in shell, "shortcuts must not fire while typing"
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "aac:set-view" in page and "aac:pending-view" in page


def test_reduced_motion_and_touch_targets():
    css = _read("app", "globals.css")
    assert "pointer: coarse" in css and "min-height: 44px" in css, "WCAG touch targets"
    assert "150ms" in css and "250ms" in css, "motion inside the 150-250ms band"


def test_no_behavior_regressions_in_pinned_strings():
    """UX pass must not touch evidence-first copy (the moat)."""
    card = _read("components", "ipo", "IpoCard.tsx")
    assert "SBI research note not available or not yet parsed." in card
    assert "pending RHP analysis" in card
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "WATCH, not BUY" in page


def test_p4_transitions_and_responsive_grids():
    css = _read("app", "globals.css")
    assert ".aac-cols-4" in css and ".aac-view" in css
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert 'className="aac-cols-4"' in page, "4-col stat grid must collapse on phones"
    assert 'key={view} className="aac-view"' in page, "view switches must animate (motion tokens)"


def test_p4_interactive_spans_are_keyboard_operable():
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert page.count('role="button"') >= 2, "view pills + verdict chips need button semantics"
    assert 'aria-pressed={view===k}' in page and 'aria-pressed={vFilter===k}' in page
    assert page.count('e.key==="Enter"||e.key===" "') >= 2, "Enter/Space must activate"


def test_p4_loading_states_use_shared_skeleton():
    st = _read("app", "dashboard", "settings", "page.tsx")
    assert "<Skeleton" in st and "loading…</div>" not in st
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "ErrorState" in page and page.count("onRetry") >= 2, "both error banners offer retry"


# ── UAT round 1 (SBIFUNDS listing 2026-07-21) — guards so bugs stay dead ──

def test_u1_confidence_scales_with_rule_coverage():
    src = _read("app", "api", "ipo", "live-preopen", "route.ts")
    assert "0.5 + 0.5 * (passed.length / scoreable)" in src, \
        "confidence must blend pass-quality WITH coverage — 2/9 elite passes must not outrank 4/9"


def test_u4_point_changes_never_wear_percent_suffix():
    src = _read("components", "ipo", "MarketsSidebar.tsx")
    assert 'isPct?"%":""' in src.replace(" ", "") or 'isPct ? "%" : ""' in src
    assert "const pct = first(row.changePct, row.change_pct);" in src, "percent fields must be preferred"


def test_u5_mobile_appbar_wraps_and_search_is_tappable():
    css = _read("app", "globals.css")
    assert ".aac-appbar" in css and "flex-wrap: wrap" in css
    assert "font-size: 16px" in css, "16px input font prevents iOS zoom-on-focus"
    nav = _read("components", "app-shell", "AppNav.tsx")
    assert 'className="aac-appbar"' in nav


def test_u6_upcoming_drops_already_listed():
    src = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "SBIFUNDS stayed on Upcoming AFTER listing" in src
    assert src.count("Date.UTC(ld.getUTCFullYear()") >= 2, "UTC-parts comparison (same rule as the phase fix)"


def test_uat_tracker_is_the_single_registry():
    doc = _read("docs", "UAT_TRACKER.md")
    for item in ("U1", "U8", "F2", "no more zombies"):
        assert item in doc


# ── UAT framework contracts ───────────────────────────────────────────────

def test_uat_framework_files_exist():
    for p in (("playwright.config.ts",), ("uat", "serve.mjs"), ("uat", "smoke.mjs"),
              ("uat", "fixtures", "seed.json"), ("uat", "tests", "_base.ts"),
              ("uat", "tests", "journeys.spec.ts"), ("uat", "tests", "a11y.spec.ts"),
              ("uat", "tests", "smoke.spec.ts"), ("docs", "UAT_FRAMEWORK.md")):
        assert os.path.exists(os.path.join(REPO, *p)), f"missing {'/'.join(p)}"
    import json
    pkg = json.load(open(os.path.join(REPO, "package.json")))
    assert "uat:all" in pkg["scripts"] and "uat:smoke" in pkg["scripts"]
    assert "playwright test" in pkg["scripts"]["uat:all"]


def test_fixture_mode_is_the_only_auth_bypass_and_never_production():
    guard = _read("lib", "api-guard.ts")
    assert "process.env.UAT_FIXTURE_JSON" in guard
    layout = _read("app", "dashboard", "layout.tsx")
    assert "process.env.UAT_FIXTURE_JSON" in layout, \
        "CI 2026-07-22: journeys all landed on /login — the PAGE gate must open in fixture mode too"
    assert 'redirect("/login")' in layout, "the real gate stays for production"
    db = _read("lib", "db.ts")
    assert "UAT_FIXTURE_JSON" in db and "fixtureAwareNeon" in db, \
        "the same env replaces the DB — the bypass can never reach real data"
    serve = _read("uat", "serve.mjs")
    assert "fixture.invalid" in serve


def test_smoke_is_read_only():
    smoke = _read("uat", "tests", "smoke.spec.ts")
    assert "request.get" in smoke
    for verb in ("request.post", "request.put", "request.delete", "request.patch"):
        assert verb not in smoke


def test_ci_blocks_on_uat():
    ci = _read(".github", "workflows", "ci.yml")
    assert "npm run uat:all" in ci and "playwright install" in ci


# ── UAT round 2 (owner DB evidence, 2026-07-22) ───────────────────────────

def test_u7_reit_invit_excluded_from_both_feeds():
    """Owner evidence: 'Bagmane Prime Office REIT' (size NULL, is_sme=false)
    leaked through the eligibility rule. REIT/InvIT units are not IPO
    equities — excluded at ipo-command AND live-preopen, with the LOCKED
    eligibility rule text left byte-identical."""
    cc = _read("app", "api", "ipo-command", "route.ts")
    lp = _read("app", "api", "ipo", "live-preopen", "route.ts")
    assert "AND (c.issue_size_cr IS NULL OR c.issue_size_cr >= 200)" in cc  # locked rule untouched
    assert cc.count("REIT|InvIT") == 1 and lp.count("REIT|InvIT") == 1


def test_u8_ticker_falls_back_to_consolidated_strong_key():
    """Owner evidence: SBIFUNDS listing morning — intelligence symbol columns
    blank until the evening enrich, launcher tracked 5 names and missed the
    one listing. Discovery now unions ipo_consolidated's strong key for the
    same window."""
    src = _read("_scripts", "ipo", "kite_ticker_ipo.py")
    assert "FROM ipo_consolidated" in src
    assert "COALESCE(NULLIF(btrim(symbol_final),''), NULLIF(btrim(nse_symbol),''), btrim(symbol))" in src
    assert "consolidated fallback unavailable" in src, "fallback must degrade gracefully"


# ── Phase 10 slice 1: data foundation scripts ─────────────────────────────

def test_phase10_backfill_is_fill_empty_only_and_gated():
    src = _read("_scripts", "backfill_listing_window_candles.py")
    assert "ON CONFLICT (symbol, date) DO NOTHING" in src, "fill-empty-only: never overwrite"
    assert "h >= max(o, cl) and lo <= min(o, cl)" in src, "OHLC sanity gate before write"
    assert "REIT|InvIT" in src and "issue_size_cr >= 200" in src, "eligible universe only"
    assert "anchor_lock30_date" in src, "window ends at the anchor lock-in"
    assert "time.sleep" in src, "rate-limited"
    assert "--dry-run" in src and "--apply" in src


def test_phase10_audit_is_read_only():
    src = _read("_scripts", "data_quality_audit.py")
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "CREATE TABLE"):
        assert verb not in src, f"audit must be read-only, found {verb}"
    assert "99.9" in src and "blank BOTH symbol columns" in src


def test_ci_uat_job_has_full_python_deps():
    ci = _read(".github", "workflows", "ci.yml")
    # regression: uat job installed only pytest+pg, import of fetch_peer_pe
    # (requests) INTERNALERROR'd collection. Both jobs now share the dep set.
    assert ci.count("requests pandas lxml") >= 2, "uat job needs the same deps as the test job"


def test_fetch_peer_pe_is_import_safe():
    src = _read("_scripts", "fetch_peer_pe.py")
    assert 'sys.exit("pip install requests' not in src.split("def ")[0], \
        "no sys.exit at import time — it aborts pytest collection"


# ── UAT CI round 2 (owner's Actions log, 2026-07-22) ──────────────────────

def test_playwright_projects_all_run_on_chromium():
    """CI installs chromium only; iPad/iPhone device descriptors default to
    webkit — tablet+mobile died with 'Executable doesn't exist'. Every
    project pins browserName chromium (device viewport/UA still emulated)."""
    cfg = _read("playwright.config.ts")
    assert cfg.count('browserName: "chromium"') >= 2
    assert 'outputDir: "uat-results"' in cfg, "artifacts must not nest inside the html reporter folder"


def test_audit_is_information_schema_driven_two_table():
    src = _read("_scripts", "data_quality_audit.py")
    assert "information_schema.columns" in src, "never assume a column exists (final_qib crash)"
    assert '("ipo_consolidated", "final_qib"' in src and '("ipo_intelligence", "nse_symbol"' in src
    assert "serving table" in src, "owner design: consolidated serves, intelligence sources"


def test_backfill_clamps_window_and_reads_aliases():
    src = _read("_scripts", "backfill_listing_window_candles.py")
    assert "INTERVAL '45 days'" in src, "one dirty lock date (FUSION) must not break a fetch"
    assert "symbol_aliases" in src and 'aliases.get(sym, "")' in src
    ddl = _read("_scripts", "schema_sync.py")
    assert "CREATE TABLE IF NOT EXISTS symbol_aliases" in ddl
