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
    # U13 (CUBEINVIT): fused symbols have no word boundary — symbol guard too
    assert cc.count("(INVIT|REIT)") == 1 and lp.count("(INVIT|REIT)") == 1


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


def test_u12_details_view_renders_after_the_pills_row():
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert page.index("pills.map") < page.index('{view==="details" && d &&'), \
        "details content must not push the nav to the page bottom"


def test_u10_hero_is_not_sticky():
    """Owner screenshots 2026-07-23: the sticky element was the ENTIRE 600px
    rules card — scrolling buried everything beneath it. Sticky removed."""
    css = _read("app", "globals.css")
    sect = css.split(".aac-sticky-decision")[1][:200]
    assert "position: static" in sect and "position: sticky" not in sect


def test_ci_artifact_upload_yaml_is_valid_block_mapping():
    """Owner CI 2026-07-22: 'Input required and not supplied: path' — the
    upload step mixed a flow mapping with a block scalar. Pin the shape."""
    ci = _read(".github", "workflows", "ci.yml")
    assert "with: { name: uat-report" not in ci
    assert "          path: |\n            uat-report/\n            uat-results/" in ci


def test_news_feeds_reject_placeholder_rows():
    """Owner pasted the manual-insert TEMPLATE verbatim and '<paste exact
    headline>' rendered on the live site. Feeds require a real URL and a
    headline that isn't template text."""
    cc = _read("app", "api", "ipo-command", "route.ts")
    lp = _read("app", "api", "ipo", "live-preopen", "route.ts")
    assert "nw.url ~* '^https?://'" in cc and "nw.headline NOT LIKE '<%'" in cc  # alias nw: smoke maps n->research_notes
    assert "n2.url ~* '^https?://'" in lp and "n2.headline NOT LIKE '<%'" in lp


# ── Golden table (owner architecture, 2026-07-22) ─────────────────────────

def test_golden_table_is_durable_plus_one_object_view():
    """ipo_consolidated is REBUILT each run (wiped-listing-tape incident), so
    golden fields live in DURABLE ipo_golden and the VIEW ipo_gold gives
    the owner's one-object reads. No ALTERs on the rebuilt table."""
    ddl = _read("_scripts", "schema_sync.py")
    assert "CREATE TABLE IF NOT EXISTS ipo_golden" in ddl
    # 2026-07-22: new durable-table fields MUST be ALTERs — CREATE IF NOT
    # EXISTS silently no-ops on the existing prod table
    for col in ("final_qib NUMERIC", "final_total NUMERIC", "industry TEXT", "nse_listing_date DATE"):
        assert f"ALTER TABLE ipo_golden ADD COLUMN IF NOT EXISTS {col}" in ddl, col
    assert "CREATE OR REPLACE VIEW ipo_gold" in ddl
    # prod incident 2026-07-22: ipo_master is a LEGACY v1 TABLE with
    # dependents — the view must never try to take that name
    assert "CREATE OR REPLACE VIEW ipo_master" not in ddl
    for col in ("candles_json JSONB", "rhp_sonnet_json JSONB", "sbi_haiku_json JSONB",
                "lot_size INT", "anchor_lock90_date DATE", "street_url TEXT"):
        assert col in ddl, col
    assert "ALTER TABLE ipo_consolidated ADD COLUMN" not in ddl


def test_consolidation_is_fill_empty_strong_key_and_automated():
    src = _read("_scripts", "consolidate_master.py")
    assert "COALESCE(g.{col}" in src and "WHERE g.{col} IS NULL" in src, "fill-empty-only"
    assert "regexp_replace(lower(" in src and "symbol_final" in src, "strong keys only"
    assert "jsonb_agg(jsonb_build_object('d', p.date" in src, "candles materialize into the golden table"
    assert "jsonb_array_length(g.candles_json), 0) < sub.n" in src, "series grows daily, never shrinks"
    assert "n.headline NOT LIKE '<%%'" in src, "placeholder rows never reach the golden table"
    lean = _read("_scripts", "run_ipo_pipeline_lean.py")
    assert '"consolidate_master.py", "--apply"' in lean, "AUTOMATED: runs every pipeline cycle"
    jr = _read("_scripts", "job_runner.py")
    assert '"consolidate"' in jr


def test_golden_fields_flow_to_command_and_details():
    """Screens read the golden object: cards query LEFT JOINs ipo_golden and
    Complete Details binds the fields (candle sessions, ISIN, locks, Sonnet
    one-line). Contract DBs execute the join, so a bad column fails here
    first — the class that reached prod three times today."""
    cc = _read("app", "api", "ipo-command", "route.ts")
    assert "LEFT JOIN ipo_golden g" in cc
    for f in ("g.isin", "jsonb_array_length(g.candles_json) AS candle_days",
              "g.rhp_sonnet_json->>'one_line'", "g.street_headline"):
        assert f in cc, f
    det = _read("components", "ipo", "CompleteDetails.tsx")
    for f in ("candle_days", "sonnet_one_line", "lock30_date", "ISIN"):
        assert f in det, f


def test_live_serves_listing_day_only():
    """Stale day-old SBIFUNDS card (frozen pre-open book, eternal 'awaiting')
    was served at 03:32 IST via the old 7-day window. Live = IST-today only;
    D1..D5 belong to Listing Review."""
    lp = _read("app", "api", "ipo", "live-preopen", "route.ts")
    assert "listing_date = (NOW() AT TIME ZONE 'Asia/Kolkata')::date" in lp
    assert "INTERVAL '7 days'" not in lp


def test_details_and_review_selectors_are_searchable():
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert page.count("Search IPO by name or symbol") == 2, "hardcoded button rows gained a search filter (owner ask)"


def test_search_card_offers_complete_details_and_default_is_closest_listed():
    search = _read("components", "features", "ipo-search.tsx")
    assert "view=details&ipo=" in search and "Complete Details" in search
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert page.count("closestListed") >= 4, "Details+Review default to the most recently listed IPO"


def test_ingest_maps_discovery_keys():
    """Owner --raw [discovery] evidence 2026-07-23: unmapped kpi keys wired
    (plain-over-_2 fallback) + peer_analysis stored whole with as-of date."""
    ing = _read("_scripts", "ipomatrix_ingest.py")
    for k in ('"ronw"', '"roce"', '"eps_pre"', '"eps_post"', '"ebitda_margin"',
              '"peer_json"', '"kpi_as_of"', 'ronw_2'):
        assert k in ing, k


def test_intraday_panel_retires_after_listing_day_ist():
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "listedIst < istToday" in page and "5.5*3600_000" in page, \
        "owner 2026-07-23: the intraday panel comes down after listing day, IST-clocked"


def test_chittorgarh_steps_removed_from_pipeline():
    """Owner 2026-07-23: Chittorgarh = IPOMatrix's sibling product — one
    vendor, one feed. Both steps removed; NSE discovery + IPOMatrix remain."""
    lean = _read("_scripts", "run_ipo_pipeline_lean.py")
    assert 'step("scrape IPO calendar + details"' not in lean.replace("# step(", "STEP_OFF(")
    assert 'step("anchor + subscription enrich"' not in lean.replace("# step(", "STEP_OFF(")
    assert '"ipomatrix_ingest.py","--only-null"' in lean and '"ipo/fetch_nse_ipos.py"' in lean
    mirror = _read("app", "api", "admin", "pipeline-steps", "route.ts")
    assert "scrape IPO calendar" not in mirror and "anchor + subscription enrich" not in mirror


def test_nse_anchor_backfill_reuses_proven_session_and_lands_durably():
    src = _read("_scripts", "nse_anchor_backfill.py")
    assert 'impersonate="chrome124"' in src and "all-upcoming-issues-ipo" in src, \
        "reuses nse_preopen_capture's proven priming pattern (owner directive)"
    assert "Anchor\\s+investor\\s+portion" in src and "ON CONFLICT (symbol)" in src
    assert "fails >= 3" in src, "NSE throttle discipline"
    # owner run 2026-07-24: 92s NSE hang -> Neon dropped the conn -> the
    # single end-of-run commit lost a whole 700-symbol pass. Never again:
    assert "PER-SYMBOL" in src and "keepalives=1" in src and "liveness probe" in src
    assert "DISTINCT ON (g.nse_symbol)" in src, "dedup + recency sort must be legal SQL together"
    ddl = _read("_scripts", "schema_sync.py")
    assert "CREATE TABLE IF NOT EXISTS nse_issue_info" in ddl


def test_smoke_contract_never_misattributes_news_columns():
    """Prod smoke FAIL 2026-07-25: ipo_news subselect used alias n, which the
    smoke parser maps to ipo_research_notes -> 'company_name does not exist'.
    News aliases must never be bare n in ipo-command."""
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.join(_o.path.dirname(__file__), ".."))
    from smoke_probe import contract_from_route
    found = contract_from_route()
    notes = found.get("ipo_research_notes", set())
    assert "company_name" not in notes and "headline" not in notes, \
        f"news columns misattributed to research_notes: {sorted(notes)}"
