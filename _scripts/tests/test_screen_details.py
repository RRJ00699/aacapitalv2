"""Complete Details route — KV-ONLY contract.

The hard constraint is that user reads NEVER wake Neon: the route serves the
warm_kv-built payload from KV (live -> 7d stale twin) and never queries the DB.
A brand-new IPO before its first warm cycle gets an honest degraded state, not a
DB read and not a 500."""
import os
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTE = os.path.join(HERE, "..", "..", "app", "api", "ipo", "[id]", "details", "route.ts")


def _src():
    with open(ROUTE, encoding="utf-8") as f:
        return f.read()


def test_route_exists():
    assert os.path.exists(ROUTE), "details route missing"


def test_reads_kv_live_then_stale_twin():
    s = _src()
    assert "kvStore" in s
    assert "ipo:${ipoId}:details" in s            # the warm_kv key
    assert "${key}:stale" in s                    # falls back to the 7d twin
    assert '"x-cache"' in s                        # HIT/STALE/MISS disclosed
    assert '"STALE"' in s and '"HIT"' in s


def test_never_queries_neon():
    """HARD CONSTRAINT — no DB import or query may appear in the route."""
    s = _src()
    for forbidden in ("fixtureAwareNeon", "@/lib/db", "neon(", "getDb(", "sql`", "@/lib/v2/sql"):
        assert forbidden not in s, f"route must not touch Neon — found {forbidden!r}"


def test_miss_is_degraded_200_not_error():
    s = _src()
    assert "available: false" in s
    assert '"MISS"' in s
    assert "status: 500" not in s                  # a miss is degraded, never a 500


def test_id_is_validated():
    s = _src()
    assert "invalid id" in s and "status: 400" in s
