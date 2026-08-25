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
    migration = Path("compatibility/scripts/migrations/20260824_d1_parity_guardrails.sql").read_text()

    assert "issue_price_rs" in preview
    for canonical in ("band_lo_rs", "band_hi_rs", "issue_price_rs"):
        assert canonical in checker
    for stale in ("i.open_date", "i.close_date", "i.listing_date", "b.d"):
        assert stale not in preview
    assert "b.ts" in preview
    assert "CAST(x.issue_price_rs AS REAL)" in preview
    assert "'UPCOMING'" in checker and "'WITHDRAWN'" in checker
    assert "'FPO'" in checker and "'SME'" not in checker
    assert "CREATE TABLE IF NOT EXISTS ipo_listing_band" not in migration
    assert "band_lo NUMERIC" not in migration


def test_real_bulk_d1_export_has_pr343_schema():
    """Real-schema smoke; set this to the one owner-supplied bulk D1 export."""
    export = os.getenv("AACAPITAL_D1_EXPORT")
    if not export:
        pytest.skip("AACAPITAL_D1_EXPORT not supplied; real D1 export required")
    db = sqlite3.connect(f"file:{export}?mode=ro", uri=True)
    for table, expected in PR343_COLUMNS.items():
        actual = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
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
