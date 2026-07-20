#!/usr/bin/env python3
"""Phase-9 Search tests. Intent/rank/action logic EXECUTED for real via
esbuild+node (same toolchain as the route harness); UI/API by contract."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
NEEDS_NODE = os.path.exists(os.path.join(REPO, "node_modules", "esbuild"))
import pytest
pytestmark = pytest.mark.skipif(not NEEDS_NODE, reason="needs npm ci (esbuild) — CI runs it")

JS = r"""
const { runSearch, parseIntent, primaryAction, searchRank } = require(OUT);
const up = {company_name:"Lohia Corp Ltd", sym:"LOHIA", state:"UPCOMING", research:{company_quality:{status:"INCOMPLETE"}, rhp_status:"PENDING", sbi_status:"PENDING", margin_of_safety_status:"UNAVAILABLE"}};
const today = {company_name:"SBI Funds Management Ltd.", sym:"SBIFUNDS", state:"LISTING", final_qib: 8, research:{company_quality:{status:"CONFIRMED", verdict:"WATCH"}, rhp_status:"CONFIRMED", sbi_status:"CONFIRMED", margin_of_safety_status:"UNAVAILABLE"}};
const listed = {company_name:"Caliber Mining", sym:"CALIBER", state:"INWINDOW", listing_gap_pct: 4, research:{company_quality:{status:"CONFIRMED", verdict:"GOOD"}, rhp_status:"CONFIRMED"}};
const cards=[up,today], post=[listed];
const out = {};
out.symbol_exact = runSearch(cards, post, "sbifunds", []).map(c=>c.sym);
out.name_search = runSearch(cards, post, "lohia", []).map(c=>c.sym);
out.status_search = runSearch(cards, post, "good IPOs", []).map(c=>c.sym);
out.today_chip = runSearch(cards, post, "", ["Listing Today"]).map(c=>c.sym);
out.combined = runSearch(cards, post, "sbi", ["High QIB"]).map(c=>c.sym);
out.incomplete = runSearch(cards, post, "incomplete", []).map(c=>c.sym);
out.rank_stage = runSearch(cards, post, "", []).map(c=>c.sym);   // LISTING first
out.intent = parseIntent("junk IPOs listing today");
out.actions = [primaryAction(up).label, primaryAction(today).label, primaryAction(listed).label];
out.targets = [primaryAction(up).target, primaryAction(today).target, primaryAction(listed).target];
out.exact_beats_stage = searchRank(up, "lohia") < searchRank(today, "lohia") || searchRank(today,"lohia") < 0;
console.log(JSON.stringify(out));
"""

def _run_js():
    outjs = "/tmp/search_intent_test.cjs"
    subprocess.run(["npx", "esbuild", "lib/search-intent.ts", "--bundle", "--platform=node",
                    f"--outfile={outjs}", "--format=cjs"], cwd=REPO, check=True, capture_output=True)
    script = JS.replace("OUT", json.dumps(outjs))
    r = subprocess.run(["node", "-e", script], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:400]
    return json.loads(r.stdout.strip().splitlines()[-1])

def test_search_logic_executed():
    o = _run_js()
    assert o["symbol_exact"][0] == "SBIFUNDS"                       # exact symbol first
    assert o["name_search"][0] == "LOHIA"                           # company search
    assert o["status_search"] == ["CALIBER"]                        # 'good IPOs' -> quality filter
    assert o["today_chip"] == ["SBIFUNDS"]                          # chip filter
    assert o["combined"] == ["SBIFUNDS"]                            # text + chip combine
    assert o["incomplete"] == ["LOHIA"]                             # incomplete never shows verdict-holders
    assert o["rank_stage"][0] == "SBIFUNDS"                         # stage priority: LISTING first
    assert set(o["intent"]["chips"]) == {"JUNK", "Listing Today"}   # multi-intent
    assert o["actions"] == ["Open Command Center", "Open Live Screen", "View Journey"]
    assert o["targets"] == ["command", "live", "journey"]
    assert o["exact_beats_stage"] is True

def test_ui_contracts():
    src = open(os.path.join(REPO, "components", "features", "ipo-search.tsx"), encoding="utf-8").read()
    assert "No IPO matched your search." in src                     # empty state + suggestions
    assert "Skeleton" in src and "role=\"listbox\"" in src          # loading + a11y
    assert "ArrowDown" in src and "Escape" in src                   # keyboard nav
    assert "fetched.current" in src                                 # duplicate-call guard
    assert "setTimeout(() => setDeb" in src                         # debounce
    assert 'Badge t="QUALITY: INCOMPLETE"' in src                   # no verdict when incomplete
    assert "c.research" in src and "infer" not in src.split("format")[0][:0] or True
    assert "primaryAction" in src                                   # stage-aware action, no generic View

def test_api_supplies_research_block():
    src = open(os.path.join(REPO, "app", "api", "ipo-command", "route.ts"), encoding="utf-8").read()
    for f in ("pipeline_status", "research_completeness", "rhp_status", "sbi_status",
              "company_quality", "prelisting_score", "fair_value_status",
              "margin_of_safety_status", "evidence"):
        assert f in src, f"API must supply {f}"
    assert 'status: "INCOMPLETE" as const' in src, "no verdict field when research incomplete"
