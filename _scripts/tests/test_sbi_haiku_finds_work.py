#!/usr/bin/env python3
"""RULE 1 tests: prove the SBI Haiku extractor FINDS WORK on the REAL schema.

History (2026-07-18): the extractor ran nightly since launch and processed ZERO of
244 notes — $0.000 spent, 0 attempts logged. Cause: `ipo_research_notes` has no
`id` column, so `SELECT n.id ...` threw on every run and the script died before
logging anything. Secondary: a 2-day window excluded 6 of 9 eligible notes.

These tests build ipo_research_notes EXACTLY as production has it (no id column)
and rely on schema_sync to supply what's missing — an earlier draft of this file
created the id column in the fixture and therefore tested a schema production
does not have, masking the very bug it was meant to catch.
"""
import importlib.util, os
import psycopg2
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "..", path))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sbi = _load("sbi", "sbi_haiku_extract.py")

# Real production shape (information_schema, 2026-07-18) — note: NO id column.
PROD_NOTES_DDL = """
DROP TABLE IF EXISTS ipo_research_notes;
CREATE TABLE ipo_research_notes (
  company TEXT, source TEXT, rating TEXT, pdf_path TEXT, parsed_at TIMESTAMPTZ,
  nse_symbol TEXT, full_json JSONB, one_line TEXT, ai_model TEXT)"""

def _prod_db(uri):
    c = psycopg2.connect(uri); c.autocommit = True; cur = c.cursor()
    cur.execute(PROD_NOTES_DDL)
    return c, cur

def _apply_schema_sync(cur):
    sync = _load("sync", "schema_sync.py")
    for stmt in sync.DDL:
        # 2026-07-21: was ipo_research_notes-only; the Haiku work query now
        # also reads ipo_intelligence eligibility columns (spend gate), so
        # apply that table's column DDL too — same as production schema runs.
        if "ipo_research_notes" in stmt or "ipo_intelligence ADD COLUMN" in stmt:
            try:
                cur.execute(stmt)
            except Exception:
                pass  # unrelated column on the minimal fixture table
    cur.connection.commit()

def test_query_fails_on_production_schema(clean_db):
    """REGRESSION: on the raw production shape the query MUST raise — this is the
    exact failure that silently killed the extractor for its entire life."""
    c, cur = _prod_db(clean_db)
    cur.execute("INSERT INTO ipo_intelligence (company_name, listing_date) VALUES ('Alpine Texworld Ltd.', CURRENT_DATE + 7)")
    cur.execute("INSERT INTO ipo_research_notes (company, source, pdf_path) VALUES ('Alpine Texworld Ltd.','SBI','rhps/a.pdf')")
    with pytest.raises(psycopg2.Error):
        cur.execute(sbi.TODO_SQL)
    c.close()

def test_finds_work_after_schema_sync(clean_db, require_pg_tz):
    """THE FIX: with schema_sync applied, an upcoming IPO's note is found."""
    c, cur = _prod_db(clean_db); _apply_schema_sync(cur)
    cur.execute("INSERT INTO ipo_intelligence (company_name, listing_date) VALUES ('Alpine Texworld Ltd.', CURRENT_DATE + 7)")
    cur.execute("INSERT INTO ipo_research_notes (company, source, pdf_path) VALUES ('Alpine Texworld Ltd.','SBI','rhps/a.pdf')")
    cur.execute(sbi.TODO_SQL)
    assert len(cur.fetchall()) == 1
    c.close()

def test_window_includes_recent_listings(clean_db, require_pg_tz):
    """WINDOW FIX: an IPO that listed 10 days ago is still current (Command Center
    shows 30d). The old 2-day window excluded 6 of the 9 eligible notes."""
    c, cur = _prod_db(clean_db); _apply_schema_sync(cur)
    cur.execute("INSERT INTO ipo_intelligence (company_name, listing_date) VALUES ('Kusumgar Ltd', CURRENT_DATE - 10)")
    cur.execute("INSERT INTO ipo_research_notes (company, source, pdf_path) VALUES ('Kusumgar Ltd','SBI','rhps/k.pdf')")
    cur.execute(sbi.TODO_SQL)
    assert len(cur.fetchall()) == 1, "10-day-old listing excluded — old 2-day window"
    c.close()

def test_canon_join_handles_name_variants(clean_db, require_pg_tz):
    """'&' vs 'and', trailing 'Ltd.' — the existing canon join already handles it
    (208/244 notes matched in production); this locks that behaviour."""
    c, cur = _prod_db(clean_db); _apply_schema_sync(cur)
    cur.execute("INSERT INTO ipo_intelligence (company_name, listing_date) VALUES ('Caliber Mining & Logistics Ltd.', CURRENT_DATE + 6)")
    cur.execute("INSERT INTO ipo_research_notes (company, source, pdf_path) VALUES ('Caliber Mining and Logistics Ltd','SBI','rhps/c.pdf')")
    cur.execute(sbi.TODO_SQL)
    assert len(cur.fetchall()) == 1
    c.close()

def test_skips_already_extracted(clean_db, require_pg_tz):
    """Idempotency — a note with full_json is never re-billed."""
    c, cur = _prod_db(clean_db); _apply_schema_sync(cur)
    cur.execute("INSERT INTO ipo_intelligence (company_name, listing_date) VALUES ('Done Co Ltd', CURRENT_DATE + 3)")
    cur.execute("""INSERT INTO ipo_research_notes (company, source, pdf_path, full_json)
                   VALUES ('Done Co Ltd','SBI','rhps/d.pdf','{"rating":"Subscribe"}')""")
    cur.execute(sbi.TODO_SQL)
    assert len(cur.fetchall()) == 0
    c.close()

def test_skips_ancient_ipo(clean_db, require_pg_tz):
    """Cost control — a 2023 listing is outside the window."""
    c, cur = _prod_db(clean_db); _apply_schema_sync(cur)
    cur.execute("INSERT INTO ipo_intelligence (company_name, listing_date) VALUES ('Old Co Ltd', DATE '2023-05-01')")
    cur.execute("INSERT INTO ipo_research_notes (company, source, pdf_path) VALUES ('Old Co Ltd','SBI','rhps/o.pdf')")
    cur.execute(sbi.TODO_SQL)
    assert len(cur.fetchall()) == 0
    c.close()
