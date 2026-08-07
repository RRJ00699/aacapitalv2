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
# NOTE (#282 fallout, fixed in the CI-fix PR): this harness stubs Neon with a
# COUNTER (never a real DB), so unlike test_api_contract it needs NO schema
# rework. #282 only (a) deleted 5 routes it referenced — market-regime,
# post-listing, ipo/post-listing, /api/ipo, ipo/playbook (removed from
# QUERY_CEILING / HOT_ROUTES / the market-regime cache test below) and (b)
# renamed two cache keys (ipo-command v4->v5, live-preopen full-response
# v1->v2). Both updated in place; the execute coverage stays LIVE.


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

def test_A2_snapshot_consumers_cold_miss_never_query_or_write():
    """Architecture-change classification: cache-on-miss assertions are replaced.
    A consumer can only read a pipeline snapshot; a cold KV never self-builds."""
    for route in ("app/api/ipo-command/route.ts", "app/api/ipo/index/route.ts",
                  "app/api/ipo/journey/route.ts", "app/api/ipo/live-preopen/route.ts"):
        d = run_route(route, 2)
        for call in d["results"]:
            assert call["queries"] == 0, f"{route} woke Neon"
            assert call["kv_puts"] == 0, f"{route} became a second producer"
            # Harness does not supply Journey's required ?sym; its 400 still proves
            # validation happens before any DB/cache producer work.
            if "journey" not in route:
                assert call["xcache"] == "MISS"


def test_A2_live_preopen_window_never_wakes_neon():
    """The old DB bypass is intentionally gone. Freshness is Worker->Kite and the
    static decision snapshot remains KV-only at every boundary."""
    for t in ("08:54", "08:55", "09:45", "09:58", "10:05", "10:06"):
        d = run_route("app/api/ipo/live-preopen/route.ts", 1, fake_ist=t)
        assert d["results"][0]["queries"] == 0
        assert d["results"][0]["kv_puts"] == 0


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
    "app/api/broker/status/route.ts": 0,  # Worker token comes from KV; no Neon fallback
    "app/api/health/route.ts": 0,
    # levels / intelligence / pipeline-status pruned 2026-07-20: archived
    # #282 pruned 5 more (removed below): market-regime, post-listing,
    # ipo/post-listing, /api/ipo, ipo/playbook — dead routes, no UI callers.
    "app/api/ipo-command/route.ts": 0,  # buildCommand() in lib/v2; ceiling kept as an N+1 upper bound (self-heal DDL dropped in #282)
    "app/api/ipo/cum-volume/route.ts": 0,
    "app/api/ipo/journey/route.ts": 0,
    "app/api/ipo/live-preopen/route.ts": 0,
    "app/api/ipo/monitor/route.ts": 0,
    "app/api/ipo/tick-feed/route.ts": 0,
    "app/api/market/global/route.ts": 5,  # +1: india_breadth read (U16, 2026-07-22)
    "app/api/market/snapshot/route.ts": 2,
    "app/api/settings/route.ts": 2,
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
    "ipo-command", "ipo/live-preopen", "market/global",
    "market/snapshot", "ipo/journey",
]  # market/live archived 2026-07-18; ipo/intelligence archived 2026-07-20 (zero callers);
   # #282 deleted "ipo" (/api/ipo) and "ipo/playbook" — removed here too

# LEDGER #13: hot routes that hit Neon per-request TODAY without a KV cache
# (audited 2026-07-17 via this test — 8 of the 9 hot routes; only ipo-command
# caches). FROZEN allow-list — the guard's job is to stop this list GROWING.
# Remove an entry the moment its route gains a cache; adding needs a review.
# 2026-07-20 shrink: ipo/live-preopen + ipo/journey CURED (Phase-2 KV caches);
# ipo/intelligence archived. Remaining three are the next zero-idle targets.
ALLOWED_UNCACHED_FOR_NOW = frozenset({
    "market/global",
})  # CURED 07-17: live-preopen, market/snapshot (#261 caches) · CURED 07-20:
    # ipo/journey (Phase-2 KV day-cache) · archived: ipo/intelligence, market/live ·
    # #282 DELETED: "ipo" (/api/ipo), "ipo/playbook" — dropped from HOT_ROUTES and here


def _route_file(name):
    p = ROOT / "app" / "api" / name / "route.ts"
    return p if p.exists() else None

def _uses_db(src):
    return bool(re.search(r"\bneon\(|\bgetDb\(|\bsql`", src))

def _has_kv_cache(src):
    # Phase-2 routes cache via the shared helper import rather than inline KV
    return bool(re.search(r"getCloudflareContext|kv\.get|CACHE_KEY|from \"@/lib/kv-cache\"", src))

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
