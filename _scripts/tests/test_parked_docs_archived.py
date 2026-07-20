"""Guard: superseded/parked planning docs stay out of the repo root.

A "PARKED" plan sitting at root invites someone acting on it. These 3 are
superseded (DB_REBUILD_PLAN is marked PARKED; the migration/cloudflare plans are
done or abandoned). Fails on the pre-change tree, passes after.

Scope note: ipo/monitor, drhp, memo, tape and the /today page are intentionally
NOT touched here — #233 (a parallel session) already made calls on those, and its
calls contradict this chat's directive (it KEPT monitor and ARCHIVED drhp/memo/
tape; this chat was told the opposite). That contradiction is for the owner to
reconcile, not for this MR to force.
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

DOCS = ["DB_REBUILD_PLAN.md", "cloudflare_migration_plan.md", "migration_phase0_inventory.md"]


def test_parked_docs_not_at_root():
    live = [d for d in DOCS if (ROOT / d).exists()]
    assert not live, f"parked docs still at repo root (move to _archive/): {live}"


def test_parked_docs_preserved_in_archive():
    missing = [d for d in DOCS if not (ROOT / "_archive" / d).exists()]
    assert not missing, f"parked docs missing from _archive/ (nothing deleted): {missing}"
