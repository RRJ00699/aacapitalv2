#!/usr/bin/env python3
"""Listing-review derivations EXECUTED (esbuild+node) + news module contracts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
NPX = shutil.which("npx") or shutil.which("npx.cmd")
pytestmark = pytest.mark.skipif(not NPX, reason="needs node toolchain")


def _run(js_body):
    out = os.path.join(tempfile.gettempdir(), "listing_review.cjs")
    subprocess.run([NPX, "esbuild", "lib/listing-review.ts", "--bundle", "--platform=node",
                    f"--outfile={out}", "--format=cjs"], cwd=REPO, check=True, capture_output=True)
    prog = f"const m = require({json.dumps(out)});\n" + js_body
    r = subprocess.run(["node", "-e", prog], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:400]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_review_states_and_observations_executed():
    o = _run("""
const day = (s)=>Date.parse(s+"T10:00:00Z");
const out = {};
out.pre = m.reviewState("2026-07-30", day("2026-07-22"), false, 0);
out.liveDay = m.reviewState("2026-07-22", day("2026-07-22"), true, 0);
out.dayDone = m.reviewState("2026-07-22", day("2026-07-22"), false, 1);
out.week = m.reviewState("2026-07-21", day("2026-07-23"), false, 2);
out.weekDone = m.reviewState("2026-07-14", day("2026-07-22"), false, 5);
const obs = m.observations({issue:574, open:611.55, high:641, close:602, gmpImplied:632, fairValue:654, deliveryPct:41, volume:9e7, offeredShares:2e8});
out.n = obs.length;
out.first = obs[0].observation;
out.firstFacts = obs[0].facts.length >= 3;
out.compress = obs.some(o=>/premium compressed/.test(o.observation));
out.counter = obs.find(o=>/premium compressed/.test(o.observation)).counter.length >= 1;
out.banned = obs.every(o => m.PROHIBITED.every(re => !re.test(o.observation + o.facts.join(" "))));
console.log(JSON.stringify(out));
""")
    assert o["pre"] == "PRE-LISTING" and o["liveDay"] == "LISTING DAY LIVE"
    assert o["dayDone"] == "LISTING DAY COMPLETE" and o["week"] == "LISTING WEEK IN PROGRESS"
    assert o["weekDone"] == "LISTING WEEK COMPLETE"
    assert 1 <= o["n"] <= 5 and o["firstFacts"]
    assert "underperformed grey-market expectations" in o["first"]  # +6.5% open vs GMP 632
    assert o["compress"] and o["counter"], "compression needs a counter-evidence line"
    assert o["banned"], "attribution words must never appear"


def test_news_module_contracts():
    # RETIRED: the street-news feed was DROPPED from the command/live feeds in #282's
    # narrow cut (no maintained V2 news source — owner decision). fetch_ipo_news.py may
    # linger as an unused pipeline script; the routes no longer join ipo_news. Guard the
    # removal rather than the (gone) news contract.
    cc = open(os.path.join(REPO, "lib", "v2", "ipo-command.ts"), encoding="utf-8").read()
    lp = open(os.path.join(REPO, "lib", "v2", "live-preopen.ts"), encoding="utf-8").read()
    assert "ipo_news" not in cc and "ipo_news" not in lp, \
        "news was removed in #282; the feeds must not re-join ipo_news"
