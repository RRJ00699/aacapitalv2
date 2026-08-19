#!/usr/bin/env python3
"""derive_outcome type-conformance + ceiling_20 semantics.

Guards the class of bug that shipped as ceiling_20 (a PRICE written into a BOOLEAN
column, failing every listed IPO's listing_outcomes upsert): assert EVERY field
derive_outcome emits conforms to the real listing_outcomes column type."""
import datetime as dt
import importlib.util
import os
import sys
from decimal import Decimal
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "pipeline"))
def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "..", "..", "pipeline", rel))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
kf = _load("kite_fetch", "kite_fetch.py")

# the REAL listing_outcomes shape for the fields derive_outcome writes (prod types)
DDL = """DROP SCHEMA public CASCADE; CREATE SCHEMA public;
CREATE TABLE market_candles(ipo_id bigint, d date, o numeric, h numeric, l numeric, c numeric, v bigint);
CREATE TABLE ipo_issue(ipo_id bigint, issue_price numeric, band_lo numeric, band_hi numeric);
CREATE TABLE listing_outcomes(ipo_id bigint, listing_open numeric, d1_close numeric,
  gap_pct numeric, pool text, best_close numeric, worst_close numeric,
  ceiling_20 boolean, hold_positive_vs_open boolean, winner_35 boolean);"""


def _conforms(val, coltype):
    if coltype == "boolean": return isinstance(val, bool)
    if coltype == "numeric": return isinstance(val, (int, float, Decimal)) and not isinstance(val, bool)
    if coltype == "text":    return isinstance(val, str)
    return True


def _seed(cur, highs, issue=100, lopen=110):
    cur.execute("INSERT INTO ipo_issue(ipo_id, issue_price) VALUES (1, %s)", (issue,))
    base = dt.date(2026, 1, 1)
    for i, hi in enumerate(highs):
        cur.execute("INSERT INTO market_candles(ipo_id,d,o,h,l,c,v) VALUES (1,%s,%s,%s,%s,%s,1000)",
                    (base + dt.timedelta(days=i), lopen, hi, lopen - 5, lopen + 2))


@pytest.mark.integration
def test_derive_outcome_types_conform_to_columns(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute(DDL)
    _seed(cur, highs=[115]*5 + [135] + [115]*19)     # high hits 135 at session 6
    rec, note = kf.derive_outcome(c, 1)
    assert note is None and rec

    # the specific bug: ceiling_20 must be a BOOL, never a price
    assert isinstance(rec["ceiling_20"], bool), f"ceiling_20 is {type(rec['ceiling_20'])}, must be bool"

    # every emitted field conforms to its actual column type (read from the schema)
    cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                   WHERE table_name='listing_outcomes'""")
    coltypes = dict(cur.fetchall())
    for k, v in rec.items():
        assert k in coltypes, f"derive_outcome emits {k}, not a listing_outcomes column"
        assert _conforms(v, coltypes[k]), f"{k}={v!r} ({type(v).__name__}) violates {coltypes[k]}"
    c.close()


@pytest.mark.integration
def test_ceiling_20_is_plus20pct_high_within_d30(pg_uri):
    """+20% above listing OPEN, on the HIGH, within the first 30 sessions."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    # open 110 -> +20% = 132. TRUE: a 133 high inside D30.
    cur.execute(DDL); _seed(cur, highs=[120]*10 + [133] + [120]*10)
    rec, _ = kf.derive_outcome(c, 1)
    assert rec["ceiling_20"] is True

    # FALSE: never reaches 132 within D30
    cur.execute(DDL); _seed(cur, highs=[131]*25)
    rec, _ = kf.derive_outcome(c, 1)
    assert rec["ceiling_20"] is False

    # window is D30: a 133 high only at session 40 must NOT count
    cur.execute(DDL); _seed(cur, highs=[120]*39 + [133])
    rec, _ = kf.derive_outcome(c, 1)
    assert rec["ceiling_20"] is False, "spike after session 30 must not set ceiling_20"
    c.close()
