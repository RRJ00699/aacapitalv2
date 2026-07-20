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
FILTER = re.compile(r"COALESCE\((?:c\.)?is_sme, false\) = false")
SIZE = re.compile(r"issue_size_cr IS NULL OR (?:c\.)?issue_size_cr >= 200")

def test_ipo_command_hard_filter():
    src = _read("app", "api", "ipo-command", "route.ts")
    assert FILTER.search(src) and SIZE.search(src)

def test_live_preopen_hard_filter():
    src = _read("app", "api", "ipo", "live-preopen", "route.ts")
    assert FILTER.search(src) and SIZE.search(src)

def test_api_ipo_hard_filter():
    src = _read("app", "api", "ipo", "route.ts")
    assert FILTER.search(src) and SIZE.search(src)

def test_cache_keys_bumped_for_filter_change():
    assert "ipo-command:v2" in _read("app", "api", "ipo-command", "route.ts")
    assert "live-preopen:rows:v2" in _read("app", "api", "ipo", "live-preopen", "route.ts")


# ── C. SBI exact join ───────────────────────────────────────────────────────
def test_sbi_join_is_exact_key_not_fuzzy():
    src = _read("app", "api", "ipo-command", "route.ts")
    assert "split_part" not in src, "first-word fuzzy ILIKE join must be gone"
    assert src.count("regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')") >= 6, \
        "all six SBI subqueries must use the exact normalized-name key"
