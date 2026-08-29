import os
import sqlite3
from pathlib import Path

import pytest

from kite_fetch import derive_outcome


PR343_COLUMNS = {
    "ipo": {"id", "isin", "name", "name_norm", "nse_symbol", "bse_symbol",
            "ipo_matrix_id", "security_kind", "status", "discovered_at", "created_at"},
    "ipo_issue": {"ipo_id", "open_date", "close_date", "allotment_date", "listing_date",
                  "lock30_date", "lock90_date", "band_lo_rs", "band_hi_rs",
                  "issue_price_rs", "face_value_rs", "lot_size_shares", "issue_size_cr",
                  "fresh_cr", "ofs_cr", "market_cap_cr", "registrar_name", "brlm_json"},
    "market_bars": {"ipo_id", "interval", "ts", "open_rs", "high_rs", "low_rs",
                    "close_rs", "volume_shares", "source_name", "content_fingerprint"},
}

# d1/migrations/0001_functional_model.sql from #343 also defines these provenance
# and issue-mechanism fields on ipo_issue.
PR343_COLUMNS["ipo_issue"].update({"is_book_built", "source_name", "source_observed_at"})


def test_derive_outcome_rejects_implausible_gap(v2_db):
    cur = v2_db.cursor()
    cur.execute("INSERT INTO ipo(id,isin,name_display,name_norm) VALUES(99,'INE000000099','Bad units','bad units')")
    cur.execute("INSERT INTO ipo_issue(ipo_id,issue_price) VALUES(99,10)")
    cur.execute("INSERT INTO market_candles(ipo_id,d,o,h,l,c,v) VALUES(99,'2026-01-01',1000,1000,1000,1000,1)")
    v2_db.commit()
    with pytest.raises(ValueError, match=r"abs\(gap_pct\) <= 300"):
        derive_outcome(v2_db, 99)


def test_d1_sql_uses_pr343_canonical_contract():
    preview = Path("compatibility/scripts/d1_parity_select_previews.sql").read_text()
    checker = Path("tools/d1_spine_check.py").read_text()

    assert "issue_price_rs" in preview
    for canonical in ("band_lo_rs", "band_hi_rs", "issue_price_rs"):
        assert canonical in checker
    for stale in ("i.open_date", "i.close_date", "i.listing_date", "b.d"):
        assert stale not in preview
    assert "b.ts" in preview
    assert "CAST(x.issue_price_rs AS REAL)" in preview
    assert "'UPCOMING'" in checker and "'WITHDRAWN'" in checker
    assert "'FPO'" in checker and "'SME'" not in checker


def test_real_bulk_d1_export_has_pr343_schema():
    """Real-schema smoke; set this to the one owner-supplied bulk D1 export."""
    export = os.getenv("AACAPITAL_D1_EXPORT")
    if not export:
        pytest.skip("AACAPITAL_D1_EXPORT not supplied; real D1 export required")
    db = sqlite3.connect(f"file:{export}?mode=ro", uri=True)
    for table, expected in PR343_COLUMNS.items():
        actual = {row[1] for row in db.execute(f'PRAGMA table_xinfo("{table}")')}
        assert actual == expected, f"{table}: missing={expected-actual}, extra={actual-expected}"


@pytest.mark.parametrize(
    ("issue_size", "fresh", "ofs", "should_fail"),
    [(500, 300, 200.5, False), (500, 300, 215, True),
     (20, 10, 10.8, False), (20, 10, 12, True)],
)
def test_fresh_ofs_reconciliation_uses_two_percent_with_one_crore_floor(
        issue_size, fresh, ofs, should_fail):
    from tools.d1_spine_check import FRESH_OFS_SQL

    db = sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE ipo_issue(
        ipo_id INTEGER, fresh_cr TEXT, ofs_cr TEXT, issue_size_cr TEXT)""")
    db.execute("INSERT INTO ipo_issue VALUES(1,?,?,?)", (str(fresh), str(ofs), str(issue_size)))
    assert db.execute("SELECT MAX(1.0, ABS(CAST(? AS REAL))*0.02)",
                      (str(issue_size),)).fetchone()[0] == max(1.0, abs(issue_size) * 0.02)
    assert bool(db.execute(FRESH_OFS_SQL).fetchall()) is should_fail


def test_schema_parity_separates_recorded_missing_from_never_deployed(tmp_path):
    from tools.d1_schema_parity import compare

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_core.sql").write_text(
        "CREATE TABLE core(id INTEGER PRIMARY KEY, value TEXT);"
        "CREATE TABLE drifted(id INTEGER PRIMARY KEY, value TEXT);"
        "CREATE INDEX core_value_idx ON core(value);")
    (migrations / "0002_guard.sql").write_text(
        "CREATE TRIGGER core_guard BEFORE DELETE ON core BEGIN SELECT RAISE(ABORT,'no'); END;")
    (migrations / "0003_stage.sql").write_text(
        "CREATE TABLE ipomatrix_raw_stage(id INTEGER PRIMARY KEY, body TEXT);")
    (migrations / "0004_chunks.sql").write_text(
        "ALTER TABLE ipomatrix_raw_stage ADD COLUMN body_len INTEGER GENERATED ALWAYS AS (length(body)) VIRTUAL;"
        "CREATE TABLE ipomatrix_raw_stage_chunks(id INTEGER, chunk_no INTEGER);")
    (migrations / "0005_outcomes.sql").write_text(
        "CREATE TABLE listing_outcomes(ipo_id INTEGER PRIMARY KEY, gap_pct REAL);")

    actual_path = tmp_path / "actual.sqlite"
    actual = sqlite3.connect(actual_path)
    actual.executescript("""CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT);
        INSERT INTO d1_migrations(name) VALUES
          ('0001_core.sql'),('0002_guard.sql'),('0003_stage.sql'),('0004_chunks.sql');
        CREATE TABLE core(id INTEGER PRIMARY KEY,value TEXT);
        CREATE TABLE drifted(id INTEGER PRIMARY KEY,value INTEGER);
        CREATE INDEX core_value_idx ON core(value);
        CREATE TRIGGER core_guard BEFORE DELETE ON core BEGIN SELECT RAISE(ABORT,'no'); END;
        CREATE TABLE extra_actual(id INTEGER);""")
    actual.commit()
    actual.close()

    matrix = {(row["kind"], row["name"]): row
              for row in compare(actual_path, migrations)["matrix"]}
    assert matrix[("table", "core")]["state"] == "PRESENT_MATCH"
    assert matrix[("table", "drifted")]["state"] == "PRESENT_DRIFT"
    assert matrix[("table", "ipomatrix_raw_stage")]["deployment_state"] == "ALREADY_RECORDED_BUT_MISSING"
    assert matrix[("table", "ipomatrix_raw_stage_chunks")]["deployment_state"] == "ALREADY_RECORDED_BUT_MISSING"
    assert matrix[("table", "listing_outcomes")]["deployment_state"] == "NEVER_DEPLOYED"
    assert matrix[("table", "extra_actual")]["state"] == "EXTRA_ACTUAL"
    assert matrix[("table", "extra_actual")]["actual_rows"] == 0


def test_schema_parity_uses_table_xinfo_for_generated_columns(tmp_path):
    from tools.d1_schema_parity import compare

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    sql = """CREATE TABLE issue(
        listing_date TEXT,
        lock30_date TEXT GENERATED ALWAYS AS (date(listing_date,'+30 days')) VIRTUAL,
        lock90_date TEXT GENERATED ALWAYS AS (date(listing_date,'+90 days')) VIRTUAL);"""
    (migrations / "0001_generated.sql").write_text(sql)
    actual_path = tmp_path / "actual.sqlite"
    actual = sqlite3.connect(actual_path)
    actual.executescript(sql)
    actual.close()
    matrix = compare(actual_path, migrations)["matrix"]
    assert next(row for row in matrix if row["name"] == "issue")["state"] == "PRESENT_MATCH"


def test_schema_parity_missing_canonical_migrations_fails_loudly(tmp_path):
    from tools.d1_schema_parity import compare

    actual_path = tmp_path / "actual.sqlite"
    sqlite3.connect(actual_path).close()
    with pytest.raises(RuntimeError, match="canonical #343 migration tree must be supplied"):
        compare(actual_path, tmp_path / "missing-migrations")
