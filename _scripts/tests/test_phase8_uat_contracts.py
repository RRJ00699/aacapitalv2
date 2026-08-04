#!/usr/bin/env python3
"""Phase-8: UAT / zero-idle / forbidden-inference / doc-integrity contracts."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _read(*p):
    return open(os.path.join(REPO, *p), encoding="utf-8").read()


# ── zero-idle: every live/hot value the user sees on the cards page is KV ──
def test_hot_reads_are_kv_served():
    assert 'SNAPSHOT_KEY = "ipo-command:v6"' in _read("app", "api", "ipo-command", "route.ts")
    assert 'readStrict("ipo-live-preopen:v2")' in _read("app", "api", "ipo", "live-preopen", "route.ts")
    j = _read("app", "api", "ipo", "journey", "route.ts")
    assert "kv-cache" in j
    t = _read("app", "api", "ipo", "tick-feed", "route.ts")
    assert re.search(r"live", t) and "kv" in t.lower(), "listing-day ticks come from KV, not Neon"

def test_stale_twin_survives_neon_sleep():
    src = _read("lib", "kv-cache.ts")
    assert ":stale" in src and 'source: "stale"' in src

def test_loadtest_script_cannot_wake_neon():
    src = _read("_scripts", "loadtest_k6.js")
    assert 'p(95)<200' in src and "rate<0.001" in src
    assert "MISS" in src, "the load test itself must assert KV serving"


# ── forbidden frontend inference (directive list) ──────────────────────────
def test_frontend_never_invents_research():
    card = _read("components", "ipo", "IpoCard.tsx")
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    for banned in ("promoter cash-out, not growth capital",
                   "SBI does not recommend", "SBI recommends"):
        assert banned not in card and banned not in page
    # fair value: no issue-price substitution in the MoS anchor without label. #282 moved
    # the readiness logic into lib/v2/live-preopen.ts (scoreListing) — same contract, and
    # the FV-inputs gap is named there (wording is now "EPS / P·E").
    lp = _read("lib", "v2", "live-preopen.ts")
    assert "fair value inputs (EPS / P·E)" in lp


# ── four-state visibility (API + UI) ───────────────────────────────────────
def test_states_visible_not_nulled():
    lp = _read("lib", "v2", "live-preopen.ts")  # scoreListing (moved from route in #282)
    assert "research_missing" in lp, "gaps are named, not nulled"
    card = _read("components", "ipo", "IpoCard.tsx")
    assert "SBI research note not available or not yet parsed." in card
    assert "pending RHP analysis" in card
    vv = _read("_scripts", "vm_verify.py")
    for s in ("CONFIRMED", "PARTIAL", "PENDING", "FAILED", "NOT VERIFIED"):
        assert s in vv


# ── eligibility: ONE rule text across every feed ───────────────────────────
def test_same_eligibility_rule_everywhere():
    # ONE eligibility rule across the surviving feeds. #282 deleted /api/ipo and moved the
    # rule into lib/v2. The size FLOOR is the primary SME guard; is_mainboard is SECONDARY
    # and UNRELIABLE — fill_ipo.upsert_ipo defaults it to True, so it excludes almost nothing
    # on its own. RULING: the floor is >=150cr THROUGHOUT (matches the locked verdict JUNK
    # line). The >=200 asserted below is the CURRENT code (drift) — the standardisation PR
    # that follows task 1 flips both the code and this assertion to >=150 together.
    size_floor = "issue_size_cr IS NULL OR iss.issue_size_cr >= 200"
    for f in (("lib", "v2", "ipo-command.ts"), ("lib", "v2", "live-preopen.ts")):
        src = _read(*f)
        assert size_floor in src, f"{f} diverges from the eligibility size floor (the real SME guard)"
        assert "is_mainboard = true" in src  # secondary, unreliable (defaults True) — kept for intent


# ── verdict-layer separation ───────────────────────────────────────────────
def test_layers_not_blended():
    lp = _read("lib", "v2", "live-preopen.ts")  # scoreListing (moved from route in #282)
    # live decision inputs include the research gate but the gate never
    # rewrites the pre-listing score, and readiness is its own field
    assert "research_ready" in lp and "rules_static" in lp and "rules_live" in lp
    page = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "WATCH, not BUY" in page, "incomplete research demotes, never upgrades"


# ── docs: no competing authority; stamps present; secrets gone ─────────────
def test_single_authority_and_stamps():
    assert not os.path.exists(os.path.join(REPO, "docs", "AACAPITAL_IPO_OPERATING_CONTRACT.md")), \
        "a second contract must never exist"
    for d in ("UI_EVIDENCE_CONTRACT.md", "CURRENT_PR_IMPLEMENTATION_AUDIT.md",
              "PIPELINE_RUNTIME_AUDIT.md", "VM_CRON_RUNBOOK.md"):
        s = _read("docs", d)
        assert "Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md" in s
    c = _read("docs", "AACAPITAL_PRODUCT_CONTRACT.md")
    for sec in ("## 9. Evidence, provenance", "## 10. Three decision layers", "## 11. Fair-value"):
        assert sec in c

def test_no_leaked_credentials_at_head():
    import subprocess
    needle = "Ash" + "rith"  # split so this test never matches itself
    r = subprocess.run(["git", "grep", "-l", needle], capture_output=True, text=True, cwd=REPO)
    hits = [h for h in r.stdout.strip().splitlines() if "test_phase8" not in h]
    assert hits == [], f"redacted credential resurfaced: {hits}"
