"""Structural user-route boundary: reviewed DB exceptions must be explicit and justified."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
USER_ROUTES = [
    "app/api/ipo-command/route.ts", "app/api/ipo/index/route.ts",
    "app/api/ipo/journey/route.ts", "app/api/ipo/live-preopen/route.ts",
    "app/api/ipo/cum-volume/route.ts", "app/api/ipo/tick-feed/route.ts",
    "app/api/market/global/route.ts", "app/api/market/snapshot/route.ts",
]
ALLOWLIST = {}  # Any future exception must include a reviewed written justification.
FORBIDDEN = re.compile(r"(?:@neondatabase/serverless|@/lib/db(?:[\"'/])|\bfrom\s+[\"'](?:pg|postgres)[\"'])")


def test_user_route_db_imports_are_reviewed_and_allowlist_is_small():
    violations = []
    for relative in USER_ROUTES:
        source = (ROOT / relative).read_text(encoding="utf-8")
        if FORBIDDEN.search(source) and relative not in ALLOWLIST:
            violations.append(relative)
    assert not violations, f"unreviewed user-route DB imports: {violations}"
    assert all(ALLOWLIST[path].strip() for path in ALLOWLIST)
    assert len(ALLOWLIST) == 0
