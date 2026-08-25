import sqlite3

import pytest

from kite_fetch import derive_outcome


def test_derive_outcome_rejects_implausible_gap(v2_db):
    cur = v2_db.cursor()
    cur.execute("INSERT INTO ipo(id,isin,name_display,name_norm) VALUES(99,'INE000000099','Bad units','bad units')")
    cur.execute("INSERT INTO ipo_issue(ipo_id,issue_price) VALUES(99,10)")
    cur.execute("INSERT INTO market_candles(ipo_id,d,o,h,l,c,v) VALUES(99,'2026-01-01',1000,1000,1000,1000,1)")
    v2_db.commit()
    with pytest.raises(ValueError, match=r"abs\(gap_pct\) <= 300"):
        derive_outcome(v2_db, 99)


def test_d1_gap_triggers_reject_bad_values(tmp_path):
    db = sqlite3.connect(tmp_path / "guard.db")
    db.executescript("CREATE TABLE ipo(id INTEGER PRIMARY KEY,nse_symbol TEXT); CREATE TABLE listing_outcomes(ipo_id INTEGER PRIMARY KEY,gap_pct NUMERIC);")
    migration = open("compatibility/scripts/migrations/20260824_d1_parity_guardrails.sql", encoding="utf-8").read()
    # The listing-band table has an FK to ipo and is valid in this minimal D1 schema.
    db.executescript(migration)
    with pytest.raises(sqlite3.IntegrityError, match="ABS"):
        db.execute("INSERT INTO listing_outcomes VALUES(1,301)")
