"""Phase 3 GROUP A — DB-compute / Neon-wake runtime tests.

Routes are esbuild-bundled with Neon/auth/Cloudflare aliased to counting
stubs (route_harness/) and their GET invoked for real. The Neon stub never
touches the network; an unstubbed driver (pg/postgres/Pool) RAISES.

Requires node_modules (npm ci) — skipped with a loud reason otherwise, and
CI must run it (the skip is visible in the report, not silent).
"""
import json, os, subprocess, pathlib, re
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HARNESS = ROOT / "_scripts" / "tests" / "route_harness" / "run_route.mjs"
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not (ROOT / "node_modules" / "esbuild").exists(),
                                 reason="node_modules missing — run npm ci (route runtime tier NOT covered)")]


def run_route(route, calls=2, fake_ist=None, expire=None):
    """Merged capabilities: fake_ist (decision-window clock, this branch) +
    expire='key@call' (KV TTL simulation, main's A2b stale-tier test)."""
    env = dict(os.environ)
    if fake_ist: env["HARNESS_FAKE_IST"] = fake_ist
    args = ["node", str(HARNESS), route, str(calls)]
    if expire:
        args.append(expire)
    r = subprocess.run(args,
                       capture_output=True, text=True, timeout=120, cwd=ROOT, env=env)
    assert r.returncode == 0, f"harness failed for {route}: {r.stderr[:300]}"
    return json.loads(r.stdout)


# ---------------- A2 — cache-hit proof ----------------

def test_A2_ipo_command_second_call_zero_queries():
    """The KV cache must actually serve the second call: ZERO Neon queries.
    Phase-2: a miss now writes TWO keys (primary + 7d :stale twin)."""
    d = run_route("app/api/ipo-command/route.ts", 2)
    c1, c2 = d["results"]
    assert c1["queries"] > 0 and c1["xcache"] == "MISS" and c1["kv_puts"] == 2
    assert c2["queries"] == 0, "CACHE BROKEN — second call hit Neon"
    assert c2["xcache"] == "HIT" and c2["kv_puts"] == 0

def test_A2b_ipo_command_stale_tier_never_wakes_neon():
    """Phase-2 zero-idle: when the PRIMARY key has expired but the :stale twin
    survives, the route serves STALE with ZERO Neon queries and ZERO writes."""
    d = run_route("app/api/ipo-command/route.ts", 3, expire="ipo-command:v1@3")
    c1, c2, c3 = d["results"]
    assert c1["xcache"] == "MISS" and c2["xcache"] == "HIT"
    assert c3["xcache"] == "STALE", f"expected STALE, got {c3['xcache']}"
    assert c3["queries"] == 0, "STALE path woke Neon — zero-idle broken"
    assert c3["kv_puts"] == 0

def test_A2_market_regime_second_call_zero_queries():
    """Ledger #12 FIX flipped: market-regime now caches in KV (keyed per
    threshold, 1h TTL) — second call ZERO Neon queries, x-cache HIT. Was:
    a Cache-Control comment; every call paid the 400-day candle scan."""
    d = run_route("app/api/market-regime/route.ts", 2)
    c1, c2 = d["results"]
    assert c1["queries"] == 2 and c1["xcache"] == "MISS" and c1["kv_puts"] == 1
    assert c2["queries"] == 0, "CACHE BROKEN — second call hit Neon"
    assert c2["xcache"] == "HIT" and c2["kv_puts"] == 0


def test_A2_live_preopen_caches_outside_window():
    """Ledger #13: 60s full-response KV cache OUTSIDE the decision window —
    2nd call zero Neon queries (14:30 IST). Two-tier since main's merge:
    the 1h inner rows-cache may also write on the miss call."""
    d = run_route("app/api/ipo/live-preopen/route.ts", 2, fake_ist="14:30")
    c1, c2 = d["results"]
    assert c1["queries"] > 0 and c1["xcache"] == "MISS"
    assert any(op == "put:ipo-live-preopen:v1" for op in c1["kv_ops"])
    assert c2["queries"] == 0 and c2["xcache"] == "HIT"

@pytest.mark.parametrize("t", ["08:55", "09:45", "09:58", "10:05"])
def test_A2_live_preopen_HARD_BYPASS_in_decision_window(t):
    """Inside 08:55–10:05 IST (the route's CORRECTED NSE pre-open model,
    2026-07-16 — order entry 09:00, firming 09:45–09:55, deadline 09:58)
    the FULL-RESPONSE cache is never consulted nor written — every call
    recomputes the live decision inputs (broker depth, preopen book). The 1h
    INNER rows-cache (main's zero-idle tier, identity rows that change only
    nightly) IS allowed to serve — it holds no decision-window data."""
    d = run_route("app/api/ipo/live-preopen/route.ts", 2, fake_ist=t)
    full_key = "ipo-live-preopen:v1"
    for c in d["results"]:
        assert c["xcache"] == "BYPASS-DECISION-WINDOW"
        assert not any(op.endswith(":" + full_key) for op in c["kv_ops"]), \
            f"{t}: full-response cache touched inside the window"
    assert d["results"][0]["queries"] > 0, f"{t}: first call must hit the DB"

def test_A2_window_boundaries_exact():
    """08:54 and 10:06 cache; 08:55 and 10:05 bypass."""
    for t, cached in (("08:54", True), ("10:06", True), ("08:55", False), ("10:05", False)):
        d = run_route("app/api/ipo/live-preopen/route.ts", 2, fake_ist=t)
        second_hit = d["results"][1]["queries"] == 0
        assert second_hit is cached, f"{t}: expected cached={cached}"


def test_A2_market_snapshot_second_call_zero_queries():
    """Ledger #13.2 (owner-approved): 300s KV cache — 2nd call zero Neon
    queries AND zero Yahoo fetches (whole handler skipped)."""
    d = run_route("app/api/market/snapshot/route.ts", 2)
    c1, c2 = d["results"]
    assert c1["queries"] > 0 and c1["xcache"] == "MISS" and c1["kv_puts"] == 1
    assert c2["queries"] == 0 and c2["xcache"] == "HIT"


# ---------------- A1 — query-count ceilings ----------------

# Pinned per-route ceilings (observed current counts). A regression that adds
# an N+1 query pattern fails here. Extend as the harness learns more routes.
QUERY_CEILING = {
    # A1 — re-audited 2026-07-20 after merging main (route archive wave +
    # ipo-command stale tier + tick-feed live path + search rewrite).
    # Observed per-request query counts pinned as ceilings for every
    # harnessable GET route. An N+1 regression exceeds its pin and fails CI.
    "app/api/admin/access/route.ts": 0,
    "app/api/admin/check/route.ts": 0,
    "app/api/admin/diagnostics/route.ts": 0,
    "app/api/admin/job-flag/route.ts": 0,
    "app/api/admin/jobs/route.ts": 0,
    "app/api/admin/kv-put/route.ts": 0,
    "app/api/admin/pipeline-failures/route.ts": 1,
    "app/api/admin/pipeline-steps/route.ts": 1,
    "app/api/admin/secrets/route.ts": 0,
    "app/api/auth/zerodha/callback/route.ts": 0,
    "app/api/auth/zerodha/route.ts": 0,
    "app/api/auth/zerodha/status/route.ts": 1,
    "app/api/broker/quote/route.ts": 0,
    "app/api/broker/status/route.ts": 1,
    "app/api/health/route.ts": 0,
    "app/api/ipo-command/route.ts": 6,
    "app/api/ipo/cum-volume/route.ts": 0,
    "app/api/ipo/intelligence/route.ts": 1,
    "app/api/ipo/journey/route.ts": 0,
    "app/api/ipo/levels/route.ts": 0,
    "app/api/ipo/live-preopen/route.ts": 2,
    "app/api/ipo/monitor/route.ts": 0,
    "app/api/ipo/playbook/route.ts": 1,
    "app/api/ipo/post-listing/route.ts": 1,
    "app/api/ipo/route.ts": 1,
    "app/api/ipo/tick-feed/route.ts": 0,
    "app/api/market-regime/route.ts": 2,
    "app/api/market/global/route.ts": 4,
    "app/api/market/snapshot/route.ts": 2,
    "app/api/pipeline/status/route.ts": 4,
    "app/api/post-listing/route.ts": 0,
    "app/api/settings/route.ts": 2,
    "app/api/tracker/route.ts": 0,
}

@pytest.mark.parametrize("route,ceiling", sorted(QUERY_CEILING.items()))
def test_A1_query_ceiling(route, ceiling):
    d = run_route(route, 1)
    q = d["results"][0]["queries"]
    assert q <= ceiling, f"{route} issued {q} queries (> pinned {ceiling}) — N+1 regression?"
    if ceiling > 0:
        assert q == ceiling or q > 0, f"{route}: queries dropped to {q} — gate/stub change? review pin"


# ---------------- A3 — no-DB-in-hot-path contract ----------------

HOT_ROUTES = [
    "ipo-command", "ipo/live-preopen", "ipo/intelligence", "market/global",
    "market/snapshot", "ipo", "ipo/journey", "ipo/playbook",
]  # market/live archived 2026-07-18 (orphaned equity feed — see _archive/)

# LEDGER #13: hot routes that hit Neon per-request TODAY without a KV cache
# (audited 2026-07-17 via this test — 8 of the 9 hot routes; only ipo-command
# caches). FROZEN allow-list — the guard's job is to stop this list GROWING.
# Remove an entry the moment its route gains a cache; adding needs a review.
ALLOWED_UNCACHED_FOR_NOW = frozenset({
    "ipo/intelligence", "market/global", "market/live",
    "ipo", "ipo/journey", "ipo/playbook",
})  # CURED: live-preopen (60s+window bypass), market/snapshot (300s) — 2026-07-17


def _route_file(name):
    p = ROOT / "app" / "api" / name / "route.ts"
    return p if p.exists() else None

def _uses_db(src):
    return bool(re.search(r"\bneon\(|\bgetDb\(|\bsql`", src))

def _has_kv_cache(src):
    return bool(re.search(r"getCloudflareContext|kv\.get|CACHE_KEY", src))

def test_A3_hot_routes_cache_or_allowlist():
    missing, violations, cured = [], [], []
    for name in HOT_ROUTES:
        f = _route_file(name)
        if f is None:
            missing.append(name); continue
        src = f.read_text(encoding="utf-8")
        if not _uses_db(src):
            continue                                     # no DB -> no wake risk
        cached = _has_kv_cache(src)
        if not cached and name not in ALLOWED_UNCACHED_FOR_NOW:
            violations.append(name)
        if cached and name in ALLOWED_UNCACHED_FOR_NOW:
            cured.append(name)
    assert not missing, f"hot routes not found (list stale?): {missing}"
    assert not violations, (
        f"HOT routes hitting Neon per-request with NO cache: {violations}. "
        f"Either add KV caching or add to ALLOWED_UNCACHED_FOR_NOW with review.")
    assert not cured, f"routes gained a cache — prune from allow-list: {cured}"
