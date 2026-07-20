"""Dead-API-reference guard (reverse route contract).

test_all_routes_contract.py proves every route's SQL runs. This proves the
OTHER direction: every internal `/api/...` the frontend fetches actually has an
`app/api/**/route.ts` to serve it. A UI that calls a route which was renamed,
never built, or archived fails SILENTLY at runtime (the fetch 404s inside a
`.catch(()=>null)`), so it never shows up in a build. This test turns that
class of bug into a red CI line.

Born from the IPO-focus cleanup: today-screen.tsx / cron-monitor.tsx called
/api/convergence, /api/sector-rotation, /api/system/* — none of which exist.
Removing those calls makes this test pass; a NEW dead fetch fails it.

Matching models Next.js app-router segments: a static segment matches itself,
`[param]` matches any one path segment, `[...param]` matches the remainder.
"""
import re
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

UI_DIRS = ["app", "components"]

# fetch("/api/..."), fetch(`/api/...`), fetch('/api/...') — capture the
# pathname up to the first query (?), template expr, or closing quote/paren.
_FETCH = re.compile(r"""fetch\(\s*[`'"](/api/[^`'"?)]*)""")

# a path segment carrying an unresolved `${...}` client expression
_WILD = "\x00"


def route_segment_lists():
    """Every app/api/**/route.ts as its path segments relative to /api."""
    out = []
    for f in sorted(ROOT.glob("app/api/**/route.ts")):
        segs = list(f.relative_to(ROOT / "app" / "api").parent.parts)
        out.append((str(f.relative_to(ROOT)), segs))
    return out


def ui_api_fetches():
    """(file, pathname) for every internal /api fetch in the UI tree."""
    seen = set()
    for d in UI_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if f.suffix not in (".ts", ".tsx"):
                continue
            src = f.read_text(encoding="utf-8", errors="ignore")
            for m in _FETCH.finditer(src):
                key = (str(f.relative_to(ROOT)), m.group(1))
                if key not in seen:
                    seen.add(key)
                    yield key


def path_segments(path):
    """/api/ipo/journey -> ['ipo','journey']; `${x}` segment -> wildcard."""
    parts = [p for p in path.strip("/").split("/") if p][1:]  # strip 'api'
    return [_WILD if "${" in p else p for p in parts]


def served(path_segs, route_segs):
    """Does a Next route with `route_segs` serve a request for `path_segs`?"""
    i = 0
    for rs in route_segs:
        if rs.startswith("[...") and rs.endswith("]"):
            return True  # catch-all consumes the remainder
        if i >= len(path_segs):
            return False
        ps = path_segs[i]
        if ps == _WILD or (rs.startswith("[") and rs.endswith("]")):
            i += 1  # client-dynamic or route-dynamic: matches one segment
            continue
        if rs != ps:
            return False
        i += 1
    return i == len(path_segs)  # static route must consume the whole path


def test_every_ui_api_fetch_has_a_route():
    routes = route_segment_lists()
    dead = []
    for (f, path) in ui_api_fetches():
        segs = path_segments(path)
        if not any(served(segs, rsegs) for (_rf, rsegs) in routes):
            dead.append(f"{path}   (in {f})")
    assert not dead, (
        "Frontend fetches these /api paths but no app/api/**/route.ts serves "
        "them (dead endpoint -> silent runtime 404):\n  "
        + "\n  ".join(sorted(set(dead)))
    )
