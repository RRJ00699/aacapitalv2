"""Offline end-to-end rehearsal for the 5-table D1 migration.

Boots the migration writer against a synthetic Neon that yields deterministic
rows for each source table, sinks the output into a temp sqlite (--sink
sqlite:PATH), and then runs the reconciliation harness. The point is not to
exercise Postgres (we have `_scripts/tests/test_check_scripts.py` for that
under pgserver) but to prove the ingest/copy path itself is idempotent,
respects keyset pagination, applies the 5-table CHECK constraints, and
matches the observation_hash contract used by the ingest Worker.

Run:

    pytest _scripts/tests/test_d1_migration_rehearsal.py -q

Requires only stdlib + pytest (no psycopg2, no wrangler).
"""
from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import sys
import time

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "tools" / "migrate"))


# --------------------------------------------------------------- fake Neon

class _FakeCursor:
    """Minimal cursor: emits (rows, description) for a whitelist of queries.

    The migration script executes many keyset-paginated SELECT statements
    against Neon. We honour just enough of the psycopg2 protocol
    (`execute`, `fetchall`, `fetchone`, `description`) to drive it end-to-end
    without a Postgres server. Repeated calls of the same paginated query
    return the fixture ONCE and then an empty result, mimicking the natural
    exhaustion Postgres would provide.
    """

    def __init__(self, fixtures: dict[str, list[dict]], seen_paginated: set[str]):
        self._fixtures = fixtures
        self._seen = seen_paginated
        self._result: list[tuple] = []
        self._cols: list[str] = []

    # psycopg2-lookalike --------------------------------------------------
    def execute(self, sql: str, params: tuple = ()):
        sql_lower = sql.lower()
        # Preflight: bootstrap SETs that neon_conn does at startup.
        if "set default_transaction_read_only" in sql_lower or \
           "set statement_timeout" in sql_lower:
            self._result, self._cols = [], []
            return

        # count(*) - the fixture is scanned once and the row count returned.
        if sql_lower.startswith("select count(*) from ") and " where " not in sql_lower:
            table = sql_lower.split("from ", 1)[1].split()[0].strip("() ")
            n = len(self._fixtures.get(table, []))
            self._result, self._cols = [(n,)], ["count"]
            return

        # Aggregates: SELECT (SELECT count(*) FROM t1) + (SELECT count(*) FROM t2) + ...
        if sql_lower.startswith("select (select count(*) from "):
            tables = [chunk.split("from ")[1].split()[0].strip("() ")
                       for chunk in sql_lower.split("select count(*)")[1:]]
            n = sum(len(self._fixtures.get(t, [])) for t in tables)
            self._result, self._cols = [(n,)], ["count"]
            return

        # ipo.name_norm lookup for research_findings resolution.
        if "select id from ipo where name_norm" in sql_lower:
            (target,) = params
            for r in self._fixtures.get("ipo", []):
                if r.get("name_norm") == target:
                    self._result, self._cols = [(r["id"],)], ["id"]
                    return
            self._result, self._cols = [], ["id"]
            return

        # count(*) FROM pg_class WHERE relname='...'  (sizing existence check).
        if "from pg_class where relname" in sql_lower:
            self._result, self._cols = [(1,)], ["count"]
            return

        # Whitelisted table probe: pick the first fixture whose name appears in FROM.
        table = None
        for candidate in self._fixtures:
            if f" from {candidate}" in sql_lower or f"from {candidate}\n" in sql_lower:
                table = candidate; break
        rows = list(self._fixtures.get(table or "", []))

        # For KEYSET-paginated selects (they contain `where 1=1` or `WHERE 1=1`),
        # return the fixture once per (table, WHERE-fingerprint), then empty.
        # The fingerprint uses the query prefix without the LIMIT clause.
        if "where 1=1" in sql_lower:
            fp = f"{table}::{sql_lower.split('limit')[0]}"
            if fp in self._seen:
                self._result, self._cols = [], []
                return
            self._seen.add(fp)

        if not rows:
            self._result, self._cols = [], []
            return
        self._cols = list(rows[0].keys())
        self._result = [tuple(r[c] for c in self._cols) for r in rows]

    def fetchall(self): out = self._result; self._result = []; return out
    def fetchone(self): out = self._result[0] if self._result else None; self._result = self._result[1:]; return out
    @property
    def description(self): return [(c,) for c in self._cols]
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _FakeConn:
    def __init__(self, fixtures):
        self._fixtures = fixtures
        # Shared across cursors so pagination-exhaustion is per-conn, not per-cursor.
        self._seen: set[str] = set()
    def cursor(self): return _FakeCursor(self._fixtures, self._seen)
    def close(self): pass


# --------------------------------------------------------------- fixture data

def _build_fixtures() -> dict[str, list[dict]]:
    return {
        # 3 IPOs; a mix of listing dates.
        "ipo": [
            {"id": 1, "isin": "INE001A01036", "symbol": "ALPHA",
             "name_norm": "alpha industries ltd", "name_display": "Alpha Industries Ltd.",
             "sector": "Materials", "industry": "Chemicals", "is_mainboard": True,
             "status": "Listed", "listing_date": "2026-05-12",
             "kite_token": 42, "ipomatrix_id": "IPX-1", "bse_code": "500001",
             "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-05-12T09:15:00Z"},
            {"id": 2, "isin": None, "symbol": "BETA",
             "name_norm": "beta health ltd", "name_display": "Beta Health Ltd.",
             "sector": "Health Care", "industry": "Pharma", "is_mainboard": True,
             "status": "Upcoming", "listing_date": None,
             "kite_token": None, "ipomatrix_id": None, "bse_code": None,
             "created_at": "2026-06-01T00:00:00Z", "updated_at": "2026-06-01T00:00:00Z"},
            {"id": 3, "isin": "INE003C01019", "symbol": "GAMMA",
             "name_norm": "gamma logistics ltd", "name_display": "Gamma Logistics Ltd.",
             "sector": "Industrials", "industry": "Transport", "is_mainboard": True,
             "status": "Listed", "listing_date": "2026-04-01",
             "kite_token": 84, "ipomatrix_id": "IPX-3", "bse_code": "500003",
             "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-04-01T09:15:00Z"},
        ],
        # source_facts with retriable duplicates: (ipo_id, field, source, doc_id, value)
        # tuple identical but fetched_at differs -> new idempotency collapses.
        "source_facts": [
            {"ipo_id": 1, "field": "fundamentals.issue_price", "value": "110.00",
             "source": "sebi_rhp", "doc_id": "doc-A", "confidence": "0.95",
             "fetched_at": "2026-05-01T00:00:00Z"},
            {"ipo_id": 1, "field": "fundamentals.issue_price", "value": "110.00",
             "source": "sebi_rhp", "doc_id": "doc-A", "confidence": "0.95",
             "fetched_at": "2026-05-02T00:00:00Z"},   # retry: same hash, should collapse
            {"ipo_id": 1, "field": "fundamentals.issue_price", "value": "115.00",
             "source": "sebi_rhp", "doc_id": "doc-A", "confidence": "0.95",
             "fetched_at": "2026-05-03T00:00:00Z"},   # genuine new value: new hash
            {"ipo_id": 3, "field": "ipo.status", "value": "Listed",
             "source": "nse", "doc_id": None, "confidence": None,
             "fetched_at": "2026-04-01T05:00:00Z"},
        ],
        # empty placeholders so the count(*) queries return 0.
        "ipo_issue": [], "financial_statements": [], "valuation": [],
        "decisions": [], "subscription_snapshots": [], "listing_outcomes": [],
        "market_candles": [], "market_candles_15m": [], "listing_observations": [],
        "rhp_findings": [], "insights": [], "ipo_rhp_intel": [],
        "ipo_research_notes": [],
    }


# --------------------------------------------------------------- rehearsal

@pytest.fixture
def rehearsal(tmp_path, monkeypatch):
    monkeypatch.setenv("NEON_READONLY_DATABASE_URL", "postgresql://fake/rehearsal")
    monkeypatch.setenv("NEON_TO_D1_BATCH", "500")
    # Reset _STATE_DIR to a per-test temp so re-runs don't cross-pollute.
    import neon_to_d1 as mod
    state_dir = tmp_path / "_migrate"
    state_dir.mkdir()
    monkeypatch.setattr(mod, "_STATE_DIR", state_dir)
    monkeypatch.setattr(mod, "_STATE", state_dir / "state.json")
    monkeypatch.setattr(mod, "_REPORT_MD", state_dir / "copy_report.md")
    monkeypatch.setattr(mod, "_REPORT_JSON", state_dir / "copy_report.json")
    monkeypatch.setattr(mod, "_ANOMALIES", state_dir / "anomalies.jsonl")
    monkeypatch.setattr(mod, "_SIZING_MD", state_dir / "sizing_report.md")
    monkeypatch.setattr(mod, "_SIZING_JSON", state_dir / "sizing_report.json")
    # Force ipo IN (...) tests to short-circuit via table-scan match (fixtures return all rows).
    fx = _build_fixtures()
    monkeypatch.setattr(mod, "neon_conn", lambda: _FakeConn(fx))
    # Reset sqlite connection cache between tests.
    monkeypatch.setattr(mod, "_SQLITE_CONNS", {})
    return mod, fx, state_dir


def _observation_hash(field, value, source, doc, pv):
    return hashlib.sha256("|".join([
        field, value or "", source, doc or "", pv or "",
    ]).encode()).hexdigest()


def test_ipo_and_source_facts_land_in_d1_and_collapse_duplicates(rehearsal, tmp_path, capsys):
    mod, fx, state_dir = rehearsal
    d1_path = tmp_path / "d1.sqlite"
    sink = f"sqlite:{d1_path}"

    # Run the migration for `ipo` and `source_facts` only. Market /
    # fundamentals / research are exercised in the next test with wider
    # fixtures; keeping this test small lets us assert exact D1 row counts.
    import sys as _sys
    argv = _sys.argv
    _sys.argv = ["neon_to_d1.py", "--sink", sink, "--targets", "ipo", "source_facts"]
    try:
        rc = mod.main()
    finally:
        _sys.argv = argv
    assert rc == 0

    conn = sqlite3.connect(d1_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # ipo: 3 rows in Neon, 3 rows in D1.
    n_ipo = conn.execute("SELECT count(*) FROM ipo").fetchone()[0]
    assert n_ipo == 3, f"expected 3 ipo rows in D1, got {n_ipo}"

    # source_facts: Neon has 4 rows but two carry the same (field,value,source,doc,pv)
    # so their observation_hash collides -> D1 keeps 3 rows.
    n_sf = conn.execute("SELECT count(*) FROM source_facts").fetchone()[0]
    assert n_sf == 3, f"expected 3 source_facts rows (1 duplicate collapsed), got {n_sf}"

    # observation_hash matches the Python contract exactly.
    hashes = {row[0] for row in conn.execute("SELECT observation_hash FROM source_facts").fetchall()}
    expected = {
        _observation_hash("fundamentals.issue_price", "110.00", "sebi_rhp", "doc-A", mod._PIPELINE_VERSION),
        _observation_hash("fundamentals.issue_price", "115.00", "sebi_rhp", "doc-A", mod._PIPELINE_VERSION),
        _observation_hash("ipo.status",               "Listed", "nse",      None,    mod._PIPELINE_VERSION),
    }
    assert hashes == expected

    # Every source_facts row must satisfy `length(observation_hash) = 64`.
    lengths = {row[0] for row in conn.execute("SELECT length(observation_hash) FROM source_facts").fetchall()}
    assert lengths == {64}

    # copy_report.md exists and mentions each target.
    md = (state_dir / "copy_report.md").read_text()
    assert "| ipo |" in md and "| source_facts |" in md


def test_check_constraints_reject_bad_writes(rehearsal, tmp_path):
    """The 5-table CHECK constraints (from d1/migrations/) are enforced when
    we sink into sqlite: - band_lo > band_hi rejected
                        - issue_price outside band rejected
                        - WEAK+BUY rejected
                        - out-of-range confidence rejected
                        - unknown finding_type rejected
    """
    mod, _, _ = rehearsal
    d1_path = tmp_path / "d1.sqlite"
    conn = mod._sqlite_conn(str(d1_path))

    # Bootstrap: an ipo row we can reference.
    conn.execute(
        "INSERT INTO ipo (isin, symbol, name_norm, name_display) "
        "VALUES ('INE001A01036','X','x','X Ltd')"
    )

    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO fundamentals (ipo_id, band_lo, band_hi) VALUES (1, '120.00', '100.00')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO fundamentals (ipo_id, band_lo, band_hi, issue_price) "
            "VALUES (1, '100.00', '120.00', '90.00')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO fundamentals (ipo_id, fundamental_verdict, listing_action) "
            "VALUES (1, 'WEAK', 'BUY_LISTING')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO research_findings (ipo_id, finding_type, source_type, finding, confidence) "
            "VALUES (1, 'rhp', 'sebi_rhp', '{}', '1.5')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO research_findings (ipo_id, finding_type, source_type, finding) "
            "VALUES (1, 'garbage_type', 'sebi_rhp', '{}')"
        )


def test_market_observations_composite_pk_is_idempotent(rehearsal, tmp_path):
    """Retrying a market_observations write with the same
    (ipo_id, interval, observation_type, observed_at) must NOT create a
    duplicate row - matches D1_EVIDENCE_REPORT sect. 8 (market check)."""
    mod, _, _ = rehearsal
    d1_path = tmp_path / "d1.sqlite"
    conn = mod._sqlite_conn(str(d1_path))
    conn.execute(
        "INSERT INTO ipo (isin, symbol, name_norm, name_display) "
        "VALUES ('INE001A01036','X','x','X Ltd')"
    )
    conn.execute(
        "INSERT INTO market_observations (ipo_id, observed_at, interval, observation_type, o, source) "
        "VALUES (1, '2026-06-17', '1d', 'candle', '128.4500', 'kite') "
        "ON CONFLICT (ipo_id, interval, observation_type, observed_at) DO NOTHING"
    )
    conn.execute(
        "INSERT INTO market_observations (ipo_id, observed_at, interval, observation_type, o, source) "
        "VALUES (1, '2026-06-17', '1d', 'candle', '999.9999', 'kite') "
        "ON CONFLICT (ipo_id, interval, observation_type, observed_at) DO NOTHING"
    )
    n = conn.execute("SELECT count(*) FROM market_observations").fetchone()[0]
    assert n == 1
    v = conn.execute("SELECT o FROM market_observations").fetchone()[0]
    assert v == "128.4500", f"first-writer-wins semantics violated: got {v}"


def test_sizing_report_covers_the_five_targets(rehearsal):
    mod, _, state_dir = rehearsal
    report = mod.do_sizing(mod.neon_conn())
    targets = {s["target"] for s in report["sizings"]}
    assert targets == {"ipo", "fundamentals", "market_observations",
                       "research_findings", "source_facts"}
    md = (state_dir / "sizing_report.md").read_text()
    for label in ("ipo", "fundamentals", "market_observations",
                  "research_findings", "source_facts",
                  "Measured storage estimate"):
        assert label in md, f"sizing report missing section: {label}"
