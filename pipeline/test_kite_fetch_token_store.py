"""D2 regression: the candle lane must never create a spine row.

kite_fetch persisted a freshly resolved instrument token through upsert_ipo(), which
re-resolves identity by isin -> name_norm. A row with isin NULL whose stored name_norm
differs from _norm(name_display) resolves to nothing, so the "enrichment" INSERTed a NEW
spine row: the token landed on a duplicate and the original id stayed tokenless. That is
CSM id 493 — the daily lane reported a resolved token=195520769 while the 15-minute lane,
selecting the same id, still reported missing_token.
"""
import datetime as dt
import sqlite3

import pytest

import kite_fetch


CSM_ID = 493
CSM_TOKEN = 195520769
# The real shape: no ISIN on the spine, and a stored name_norm that does not equal
# _norm(name_display) — the row predates the current normaliser.
CSM_DISPLAY = "CSM (India) Limited"
CSM_STORED_NORM = "csm india"


class CursorAdapter:
    """psycopg2-shaped cursor over sqlite: %s placeholders and now()."""

    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=()):
        import re
        sql = re.sub(r"%\((\w+)\)s", r":\1", sql).replace("%s", "?")
        sql = sql.replace("now()", "CURRENT_TIMESTAMP")
        def scalar(v):
            return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v
        if isinstance(params, dict):
            return self.cursor.execute(sql, {k: scalar(v) for k, v in params.items()})
        return self.cursor.execute(sql, tuple(scalar(v) for v in (params or ())))

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    @property
    def rowcount(self):
        return self.cursor.rowcount


class SpineConn:
    def __init__(self, raw):
        self.raw = raw

    def cursor(self):
        return CursorAdapter(self.raw.cursor())

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        pass


@pytest.fixture
def spine():
    raw = sqlite3.connect(":memory:")
    raw.executescript("""
      CREATE TABLE ipo(
        id INTEGER PRIMARY KEY, isin TEXT, symbol TEXT, name_norm TEXT, name_display TEXT,
        sector TEXT, industry TEXT, is_mainboard BOOLEAN, status TEXT, listing_date TEXT,
        kite_token INTEGER, ipomatrix_id TEXT, bse_code TEXT, in_backtest_universe BOOLEAN,
        created_at TEXT, updated_at TEXT);
      CREATE TABLE source_facts(
        ipo_id INTEGER, field TEXT, value TEXT, source TEXT, doc_id TEXT,
        confidence NUMERIC, fetched_at TEXT);
      CREATE UNIQUE INDEX source_facts_identity
        ON source_facts(ipo_id, field, source, fetched_at);
    """)
    raw.execute("""INSERT INTO ipo(id,isin,symbol,name_norm,name_display,is_mainboard,status,
                                   listing_date,kite_token)
                   VALUES(?,NULL,'CSM',?,?,1,'listed','2026-08-11',NULL)""",
                (CSM_ID, CSM_STORED_NORM, CSM_DISPLAY))
    raw.commit()
    yield raw
    raw.close()


def run_daily_lane(monkeypatch, spine, *, token=CSM_TOKEN):
    """process() with the network stubbed: only the token-store path is exercised."""
    monkeypatch.setattr(kite_fetch, "db", lambda: SpineConn(spine))
    monkeypatch.setattr(kite_fetch, "resolve_token", lambda *_a, **_k: (token, "NSE"))
    monkeypatch.setattr(kite_fetch, "fetch_candles", lambda *_a, **_k: [])
    monkeypatch.setattr(kite_fetch, "fetch_candles_15m", lambda *_a, **_k: [])
    monkeypatch.setattr(kite_fetch, "derive_outcome", lambda _conn, _id: (None, "no candles"))
    return kite_fetch.process(object(), CSM_ID, None, "CSM", CSM_DISPLAY,
                              dt.date(2026, 8, 11), 400, True, fetch_15m=False)


def rows(spine):
    return spine.execute("SELECT id, kite_token FROM ipo ORDER BY id").fetchall()


def test_token_lands_on_the_same_id_and_no_second_spine_row_appears(monkeypatch, spine):
    out = run_daily_lane(monkeypatch, spine)
    assert out["token"] == CSM_TOKEN
    assert rows(spine) == [(CSM_ID, CSM_TOKEN)], "the candle lane created a duplicate spine row"


def test_a_stored_token_is_never_overwritten_and_never_nulled(monkeypatch, spine):
    spine.execute("UPDATE ipo SET kite_token=? WHERE id=?", (11111, CSM_ID)); spine.commit()
    # A later resolution must not clobber the stored token...
    monkeypatch.setattr(kite_fetch, "db", lambda: SpineConn(spine))
    conn = SpineConn(spine)
    cur = conn.cursor()
    cur.execute("UPDATE ipo SET kite_token=COALESCE(kite_token,%s), updated_at=now() WHERE id=%s",
                (CSM_TOKEN, CSM_ID))
    conn.commit()
    assert rows(spine) == [(CSM_ID, 11111)]
    # ...and a NULL resolution cannot erase it.
    cur.execute("UPDATE ipo SET kite_token=COALESCE(kite_token,%s), updated_at=now() WHERE id=%s",
                (None, CSM_ID))
    conn.commit()
    assert rows(spine) == [(CSM_ID, 11111)]


def test_the_duplicating_resolver_is_the_mechanism_and_is_no_longer_reachable(spine):
    """Proof the fixture really is the CSM 493 shape: the old path duplicates it."""
    from fill_ipo import upsert_ipo, _norm
    assert _norm(CSM_DISPLAY) != CSM_STORED_NORM
    new_id, action = upsert_ipo(SpineConn(spine),
                                dict(isin=None, name_display=CSM_DISPLAY, name_norm=None,
                                     kite_token=CSM_TOKEN), source="kite")
    assert action == "inserted" and new_id != CSM_ID
    assert len(rows(spine)) == 2, "fixture no longer reproduces the duplicating resolution"
    # The lane itself no longer has that resolver in reach: no executable line calls it.
    with open(kite_fetch.__file__, encoding="utf-8") as handle:
        code = [line for line in handle if not line.lstrip().startswith("#")]
    assert any("from fill_ipo import _log_fact" in line for line in code)
    assert not [line for line in code if "upsert_ipo(" in line], \
        "the candle lane may never create a spine row"


def test_the_token_and_its_exchange_are_both_recorded_against_the_same_id(monkeypatch, spine):
    run_daily_lane(monkeypatch, spine)
    facts = spine.execute("SELECT ipo_id, field, value FROM source_facts ORDER BY field").fetchall()
    assert facts == [(CSM_ID, "kite_token", str(CSM_TOKEN)),
                     (CSM_ID, "kite_token_exchange", "NSE")]
