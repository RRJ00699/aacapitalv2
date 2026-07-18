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


def run_route(route, calls=2):
    r = subprocess.run(["node", str(HARNESS), route, str(calls)],
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert r.returncode == 0, f"harness failed for {route}: {r.stderr[:300]}"
    return json.loads(r.stdout)


# ---------------- A2 — cache-hit proof ----------------

def test_A2_ipo_command_second_call_zero_queries():
    """The KV cache must actually serve the second call: ZERO Neon queries."""
    d = run_route("app/api/ipo-command/route.ts", 2)
    c1, c2 = d["results"]
    assert c1["queries"] > 0 and c1["xcache"] == "MISS" and c1["kv_puts"] == 1
    assert c2["queries"] == 0, "CACHE BROKEN — second call hit Neon"
    assert c2["xcache"] == "HIT" and c2["kv_puts"] == 0

def test_A2_market_regime_second_call_zero_queries():
    """Ledger #12 FIX flipped: market-regime now caches in KV (keyed per
    threshold, 1h TTL) — second call ZERO Neon queries, x-cache HIT. Was:
    a Cache-Control comment; every call paid the 400-day candle scan."""
    d = run_route("app/api/market-regime/route.ts", 2)
    c1, c2 = d["results"]
    assert c1["queries"] == 2 and c1["xcache"] == "MISS" and c1["kv_puts"] == 1
    assert c2["queries"] == 0, "CACHE BROKEN — second call hit Neon"
    assert c2["xcache"] == "HIT" and c2["kv_puts"] == 0


# ---------------- A1 — query-count ceilings ----------------

# Pinned per-route ceilings (observed current counts). A regression that adds
# an N+1 query pattern fails here. Extend as the harness learns more routes.
QUERY_CEILING = {
    "app/api/ipo-command/route.ts": 6,     # cards/dl/live/levels/post/brlm (miss path)
    "app/api/market-regime/route.ts": 2,   # breadth agg + as-of
}

@pytest.mark.parametrize("route,ceiling", sorted(QUERY_CEILING.items()))
def test_A1_query_ceiling(route, ceiling):
    d = run_route(route, 1)
    q = d["results"][0]["queries"]
    assert q <= ceiling, f"{route} issued {q} queries (> pinned {ceiling}) — N+1 regression?"
    assert q > 0 or d["results"][0]["err"], "zero queries and no error — stub bypassed?"


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
    "ipo/live-preopen", "ipo/intelligence", "market/global",
    "market/snapshot", "ipo", "ipo/journey", "ipo/playbook",
})


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
