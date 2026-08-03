#!/usr/bin/env python3
"""Evidence-model + hard-filter contract tests (2026-07-20). Offline.

A. OFS repair (operating-contract Phase-7):
   * a bare ofs_pct >= 60 must NEVER produce "promoter cash-out" — that
     interpretation requires RHP evidence (structure.ofs_heavy + detail)
   * without evidence the UI shows the neutral fact + explicit PENDING line
   * with confirmed evidence the negative carries the RHP's own words
   * strengths are divided from not-buy reasons (the "Strong ROE under
     'Why NOT buy'" confusion)
B. Hard filters (audit #6, LOCKED <200cr/SME rule): ipo-command, live-preopen
   and /api/ipo exclude SME + confirmed sub-200cr; NULL size stays visible.
C. SBI join (audit #7): first-word ILIKE gone; exact normalized-name key.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _read(*p):
    with open(os.path.join(REPO, *p), encoding="utf-8") as fh:
        return fh.read()


# ── A. OFS evidence model ───────────────────────────────────────────────────
def test_ofs_bare_fact_never_says_cash_out():
    src = _read("components", "ipo", "IpoCard.tsx")
    # the old unsupported line must be gone
    assert "mostly promoter cash-out, not growth capital" not in src
    # the tile label is the backtested STRUCTURE word, not a motive claim
    assert '"OFS-heavy"' in src
    assert re.search(r'ofsPct > 60 \? "promoter cash-out"', src) is None


def test_ofs_pending_state_without_rhp_evidence():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert "offer for sale confirmed" in src
    assert "pending RHP analysis" in src
    # pending lane renders distinctly (not as a confirmed negative)
    assert "pend.push(" in src and "pend.map(" in src


def test_ofs_negative_requires_structure_evidence():
    """PR-B extended the Phase-7 gate into a ladder:
       insight(negative) -> insight(non-negative: silence) -> fj0 evidence -> pending."""
    src = _read("components", "ipo", "IpoCard.tsx")
    assert 'stIns.direction === "negative"' in src, "insight-backed negative gate missing"
    m = re.search(r"else if \(st\?\.ofs_heavy === true && stDetail\)\s*{\s*\n\s*bad\.push\(\{ text: `\$\{ofsPct\}% OFS — RHP: ", src)
    assert m, "fj0 fallback must stay gated on structure.ofs_heavy + detail and quote the RHP"


def test_strengths_divided_from_not_buy_reasons():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert "and in its favour" in src, "strengths need an explicit divider under the NOT-buy heading"


def test_quantitative_ofs_weight_unchanged():
    src = _read("lib", "fair-value.ts")
    assert "sfac -= 0.08" in src, "approved quantitative OFS weight must not change"
    assert "cash-out, weak" not in src, "narrative removed from the weight comment"


# ── B. hard filters ─────────────────────────────────────────────────────────
# PR #282 moved the queries into lib/v2/*.ts and, on the canonical V2 schema, gates on
# is_mainboard (not the V1 is_sme). The size FLOOR is the real SME exclusion; is_mainboard
# is secondary/unreliable (fill_ipo.upsert_ipo defaults it True). RULING: the floor is
# >=150cr THROUGHOUT (matches the locked verdict JUNK line). The >=200 below is the CURRENT
# code (drift); the standardisation PR after task 1 flips code + assertion to >=150 together.
# Do not read 200 as canonical.
FILTER = re.compile(r"is_mainboard\s*=\s*true")
SIZE = re.compile(r"issue_size_cr IS NULL OR (?:iss\.|c\.)?issue_size_cr >= 200")

def test_ipo_command_hard_filter():
    src = _read("lib", "v2", "ipo-command.ts")
    assert FILTER.search(src) and SIZE.search(src)

def test_live_preopen_hard_filter():
    src = _read("lib", "v2", "live-preopen.ts")
    assert FILTER.search(src) and SIZE.search(src)

def test_api_ipo_hard_filter():
    # RETIRED: /api/ipo was DELETED by PR #282 (dead route — no live consumer, only
    # _archive/*.txt referenced it). The hard filter now lives in the routes that
    # survived (covered above). Guard the deletion instead of the filter.
    assert not os.path.exists(os.path.join(REPO, "app", "api", "ipo", "route.ts")), \
        "/api/ipo was deleted in #282 and must not return"

def test_cache_keys_bumped_for_filter_change():
    assert "ipo-command:v5" in _read("app", "api", "ipo-command", "route.ts")     # v4->v5 (#282)
    assert "live-preopen:rows:v3" in _read("app", "api", "ipo", "live-preopen", "route.ts")  # v2->v3 (#282)


# ── C. SBI exact join ───────────────────────────────────────────────────────
def test_sbi_join_is_exact_key_not_fuzzy():
    # RETIRED: SBI extraction/joins were DROPPED — pipeline commit 85678db ("SBI parser
    # dropped") and PR #282 removed the SBI subqueries from ipo-command. The exact-key
    # concern is moot; guard that the fuzzy first-word ILIKE never comes back instead.
    src = _read("lib", "v2", "ipo-command.ts")
    assert "n.source='SBI'" not in src and "sbi_rating" not in src, \
        "SBI joins were removed in #282; they must not return to the command feed"
