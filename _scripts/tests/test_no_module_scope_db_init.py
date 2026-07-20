"""Guard: no route/lib initializes the DB client at MODULE SCOPE.

The production deploy (deploy.yml -> opennextjs-cloudflare build -> next build)
runs WITHOUT DATABASE_URL at build time. A module-scope `const sql = neon(...)`
(or a module-scope throw in lib/db.ts) is evaluated during Next's "Collecting
page data" step and throws, killing the deploy — while ci.yml passed because it
injects a dummy DATABASE_URL. This test reproduces that class of bug statically.

FAILS on the pre-fix tree (7 routes + lib/db.ts init at module scope), passes
after they were made lazy (resolve on first query — identical runtime behavior).
"""
import pathlib
import re
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

# module-scope (indent 0) `const x = neon(` — evaluated at import, so it throws
# during `next build` when DATABASE_URL is absent.
_MODULE_NEON = re.compile(r"(?m)^(export\s+)?const\s+\w+\s*=\s*neon\s*\(")


def _route_files():
    return sorted((ROOT / "app").rglob("route.ts"))


def test_no_route_inits_neon_at_module_scope():
    offenders = []
    for f in _route_files():
        if _MODULE_NEON.search(f.read_text(encoding="utf-8")):
            offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, (
        "These routes create the neon() client at module scope — `next build` "
        "(deploy.yml, no DATABASE_URL) throws during page-data collection. Make "
        "the client lazy (resolve on first query):\n  " + "\n  ".join(offenders))


def test_lib_db_does_not_init_or_throw_at_module_scope():
    src = (ROOT / "lib" / "db.ts").read_text(encoding="utf-8")
    assert not _MODULE_NEON.search(src), "lib/db.ts creates the neon client at module scope — make it lazy"
    # a module-scope `throw` (indent 0) also fails the build at import
    assert not re.search(r"(?m)^throw\b", src), "lib/db.ts throws at module scope — move it into the lazy getter"
