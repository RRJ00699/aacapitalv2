"""Phase 3 B7 — auth-gating: every admin/* route must return 401/403 WITHOUT
a session, and must issue ZERO Neon queries before the gate (no unauthenticated
work). Regression here leaks the secret vault (kite_session, ipomatrix cookie,
stderr tails).

Mechanism: the harness guard stubs honor HARNESS_AUTH=deny (simulated
no-session); routes with their own header-token auth (job-flag) 401 natively
because the harness request carries no auth header. A route missing its guard
returns 200 with queries>0 and fails here — which is exactly how ledger #15
(diagnostics/pipeline-failures/pipeline-steps shipped UNGUARDED) was caught.
"""
import json, os, subprocess, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HARNESS = ROOT / "_scripts" / "tests" / "route_harness" / "run_route.mjs"
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not (ROOT / "node_modules" / "esbuild").exists(),
                                 reason="node_modules missing — run npm ci (auth-gating tier NOT covered)")]

ADMIN_ROUTES = sorted(str(p.relative_to(ROOT))
                      for p in ROOT.glob("app/api/admin/*/route.ts"))


def run_unauth(route):
    env = dict(os.environ, HARNESS_AUTH="deny")
    r = subprocess.run(["node", str(HARNESS), route, "1"],
                       capture_output=True, text=True, timeout=120, cwd=ROOT, env=env)
    assert r.returncode == 0, f"harness failed for {route}: {r.stderr[:300]}"
    return json.loads(r.stdout)["results"][0]


def test_admin_route_list_is_current():
    """The parametrized set below must cover every admin route on disk —
    a new admin route is auto-included, never silently untested."""
    assert len(ADMIN_ROUTES) >= 8, ADMIN_ROUTES


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_B7_admin_route_401_and_zero_queries_without_session(route):
    res = run_unauth(route)
    assert res["err"] is None, f"{route} crashed unauth: {res['err']}"
    assert res["status"] in (401, 403), \
        f"{route} served {res['status']} to an unauthenticated request — GUARD MISSING"
    assert res["queries"] == 0, \
        f"{route} ran {res['queries']} Neon queries BEFORE auth — work leaks pre-gate"
