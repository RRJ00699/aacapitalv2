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
