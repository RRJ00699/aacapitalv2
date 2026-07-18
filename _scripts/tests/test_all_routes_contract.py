"""Phase 3 B5 — ALL-routes SQL contract.

Every sql`...` block in every app/api/**/route.ts is extracted VERBATIM,
JS-template-cooked, and executed against the seeded contract schema. A renamed
column, broken alias, or failed join in ANY route fails here — the class that
caused the all-awaiting-cards incident.

Frozen-failure pattern (same as A3): blocks that CANNOT run against the
contract schema today (their tables aren't declared yet) are FROZEN as
KNOWN_GAPS = LEDGER #14. A NEW failure fails CI; a cured gap must be pruned
(the list only shrinks). Contract tables get added gap by gap.
"""
import re, pathlib, datetime
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration

# ---------- extraction (shared semantics with test_api_contract) ----------

_VALID = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "`": "`", "$": "$", "'": "'", '"': '"'}

def _cook(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(_VALID.get(s[i + 1], s[i + 1])); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)

def all_blocks():
    for f in sorted(ROOT.glob("app/api/**/route.ts")):
        src = f.read_text(encoding="utf-8")
        for i, block in enumerate(re.findall(r"sql`([^`]+)`", src)):
            yield str(f.relative_to(ROOT)), i, _cook(block)

def _bind(q):
    """${expr} -> %s with a type-guessed dummy: ANY( -> list, LIMIT/OFFSET ->
    int, date-ish -> date, else text '1' (valid int-in-text for numeric casts)."""
    params = []
    def sub(m):
        after = q[m.end():m.end() + 8]
        before = q[:m.start()].rstrip().upper()
        if after.startswith("::date"):
            params.append(datetime.date.today()); return "%s"
        if before.endswith("ANY("):
            params.append(["X"])
        elif before.endswith(("LIMIT", "OFFSET")):
            params.append(1)
        elif before.endswith(("DATE", ">=", "<=")) and "DATE" in before[-30:]:
            params.append(datetime.date.today())
        else:
            params.append("1")
        return "%s"
    q2 = re.sub(r"\$\{[^}]*\}", sub, q)
    return q2, params


# ---------- contract schema (superset: api_db tables + route tables) ----------

from contract_schema import CONTRACT_DDL  # prod-truth (triage 2026-07-17)


@pytest.fixture(scope="module")
def contract_db(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute(CONTRACT_DDL)
    yield c
    c.close()


# ---------- LEDGER #14: blocks the contract schema can't run YET ----------
# (file, block_index) -> short reason. FROZEN 2026-07-17 first audit.
# The list may only SHRINK: declare the table/columns in CONTRACT_DDL, run,
# prune the entry. A NEW entry appearing = a route broke the contract = CI red.
KNOWN_GAPS = {
    # ══ KIND 2 — PROD-VERIFIED DEAD REFS (triage 2026-07-17): these routes
    # are broken against the live schema TODAY. Fix = edit the ROUTE (owner
    # approval per route, preview-first). Prune on fix. ══
    ("app/api/ipo/playbook/route.ts", 0):     "KIND2 REDIAGNOSED: queries ipo_intelligence which has NO day1_qib "
                                              "(consolidated-only) — needs JOIN or NULL-degrade, owner call",
    ("app/api/ipo/route.ts", 0):              "KIND2: return_day30 — routes use it as POINT-IN-TIME latest return; "
                                              "max_upside_30d is peak; return_cmp matches intent — owner call",
    ("app/api/ipo/post-listing/route.ts", 0): "KIND2: return_day30 point-in-time — see ipo/route entry",
    ("app/api/ipo/intelligence/route.ts", 0): "KIND2: return_day30 point-in-time — see ipo/route entry",
    # ══ HARNESS-LIMIT — dynamic SQL fragment (raw `'${date}'::date` string
    # built in JS), not parameterizable by extraction. Not a route bug. ══
    ("app/api/ipo/gmp/route.ts", 3):          "HARNESS: dynamic SQL fragment interpolation",
}


def test_B5_every_route_sql_block_runs_or_is_known_gap(contract_db):
    new_failures, cured = {}, []
    blocks = list(all_blocks())
    assert len(blocks) >= 40, f"extractor regressed: only {len(blocks)} sql blocks found"
    cur = contract_db.cursor()
    for f, i, q in blocks:
        q2, params = _bind(q)
        try:
            try:
                cur.execute(q2, params or None)
            except Exception as e1:
                # retry ladder: date-typed params for InvalidDatetimeFormat class
                if "input syntax for type date" in str(e1) or "timestamp" in str(e1):
                    import datetime as _dt
                    cur.execute(q2, [(_dt.date.today() if isinstance(x, str) else x)
                                     for x in params] or None)
                else:
                    raise
            try: cur.fetchall()
            except Exception: pass
            if (f, i) in KNOWN_GAPS:
                cured.append((f, i))
        except Exception as e:
            contract_db.rollback() if not contract_db.autocommit else None
            key = (f, i)
            reason = f"{type(e).__name__}: {str(e).splitlines()[0][:90]}"
            if key not in KNOWN_GAPS:
                new_failures[key] = reason
    assert not new_failures, (
        "NEW route-SQL contract failures (renamed column / broken join / new "
        "table not declared):\n" +
        "\n".join(f"  {f}[{i}]: {r}" for (f, i), r in sorted(new_failures.items())))
    assert not cured, f"gaps cured — prune from KNOWN_GAPS: {sorted(cured)}"
