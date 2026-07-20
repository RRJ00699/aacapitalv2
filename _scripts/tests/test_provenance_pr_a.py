#!/usr/bin/env python3
"""PR-A provenance tests (2026-07-21).

fanout() executed FOR REAL on fixture Sonnet JSON; store_insights() executed
against real Postgres (pgserver) proving supersede-not-delete and rerun
safety. Directive tests covered here:
  * no insight without a source excerpt
  * 100% OFS alone (structured) produces NO RHP insight row — interpretation
    requires the model's detail
  * institutional-OFS wording flows through verbatim (never relabeled
    'promoter exit' by us — the statement IS the model's evidenced words)
  * rerun does not duplicate; changed analysis supersedes (is_current)
  * stale-verdict marker: schema adds pdf_sha256; store persists it
"""
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location("insights_fanout", os.path.join(ROOT, "insights_fanout.py"))
fx = importlib.util.module_from_spec(spec); spec.loader.exec_module(fx)

FIXTURE = {
    "verdict": "some-concerns",
    "structure": {"ofs_heavy": True,
                  "detail": "Entirely an offer for sale by promoter group; company receives no proceeds (p.87: 'the Company will not receive any proceeds from the Offer')."},
    "use_of_proceeds": {"flag": None, "detail": "Not applicable — no fresh issue."},
    "promoter_pledge": {"flag": False, "detail": "No promoter shares are pledged ('Nil' — Capital Structure)."},
    "promoter_skin": {"detail": "Promoter holding falls from 100% to 75% post-issue."},
    "top_3_material_risks": [
        "Customer concentration: top 5 customers = 68% of revenue (Risk Factor 3).",
        {"risk": "Pending tax demand of Rs.412cr", "quote": "aggregate disputed tax demands of Rs.412.3 crore", "section": "Outstanding Litigation"},
    ],
}

INSTITUTIONAL = {
    "structure": {"ofs_heavy": True,
                  "detail": "100% OFS by an institutional shareholder (ABC Fund LP); promoters are not selling."},
}


# ── fanout, executed ────────────────────────────────────────────────────────
def test_every_row_has_excerpt_and_rhp_source():
    rows = fx.fanout(FIXTURE)
    assert rows, "fixture must fan out"
    for r in rows:
        assert r["source_excerpt"].strip(), "provenance rule: no excerpt, no row"
        assert r["source_type"] == "RHP"


def test_ofs_interpretation_requires_detail():
    # bare flag with NO detail = zero rows (the structured ofs_pct fact lives
    # in the STRUCTURED lane, never as an RHP claim)
    assert fx.fanout({"structure": {"ofs_heavy": True}}) == []
    assert fx.fanout({}) == []


def test_ofs_negative_carries_models_words():
    rows = fx.fanout(FIXTURE)
    st = [r for r in rows if r["category"] == "structure"]
    assert len(st) == 1 and st[0]["direction"] == "negative"
    assert "will not receive any proceeds" in st[0]["source_excerpt"]


def test_institutional_ofs_statement_verbatim_not_relabeled():
    rows = fx.fanout(INSTITUTIONAL)
    assert len(rows) == 1
    assert "institutional shareholder" in rows[0]["statement"]
    assert "promoter cash-out" not in rows[0]["statement"].lower()


def test_risks_negative_with_locator_when_given():
    rows = fx.fanout(FIXTURE)
    risks = [r for r in rows if r["category"] == "risk"]
    assert len(risks) == 2 and all(r["direction"] == "negative" for r in risks)
    assert any(r["source_locator"] == "Outstanding Litigation" for r in risks)


def test_clean_pledge_is_neutral_not_negative():
    rows = fx.fanout(FIXTURE)
    gov = [r for r in rows if "No promoter shares are pledged" in r["statement"]]
    assert gov and gov[0]["direction"] == "neutral"


# ── store_insights on real Postgres ────────────────────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS ipo_insights (
  insight_id BIGSERIAL PRIMARY KEY, ipo_id INT NOT NULL, category TEXT NOT NULL,
  statement TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('positive','negative','neutral','incomplete')),
  source_type TEXT NOT NULL, source_name TEXT, source_document_id TEXT,
  source_url TEXT, source_locator TEXT, source_excerpt TEXT,
  extraction_model TEXT, analysis_model TEXT, analysis_run_id TEXT,
  confidence TEXT, created_at TIMESTAMPTZ DEFAULT NOW(),
  source_published_at TIMESTAMPTZ, source_downloaded_at TIMESTAMPTZ,
  is_current BOOLEAN DEFAULT TRUE);
"""


def test_store_supersedes_never_duplicates(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS ipo_insights"); cur.execute(DDL)
    rows = fx.fanout(FIXTURE)
    n1 = fx.store_insights(cur, 7, rows, analysis_run_id="run1", analysis_model="sonnet", pdf_sha256="abc")
    n2 = fx.store_insights(cur, 7, rows, analysis_run_id="run2", analysis_model="sonnet", pdf_sha256="abc")
    assert n1 == n2 == len(rows)
    cur.execute("SELECT COUNT(*) FROM ipo_insights WHERE ipo_id=7 AND is_current")
    assert cur.fetchone()[0] == len(rows), "rerun must supersede, not duplicate current"
    cur.execute("SELECT COUNT(*) FROM ipo_insights WHERE ipo_id=7 AND NOT is_current")
    assert cur.fetchone()[0] == len(rows), "history preserved (never deleted)"
    cur.execute("SELECT DISTINCT analysis_run_id FROM ipo_insights WHERE ipo_id=7 AND is_current")
    assert cur.fetchone()[0] == "run2"
    # another IPO's failure/state never touches this one
    fx.store_insights(cur, 8, fx.fanout(INSTITUTIONAL), analysis_run_id="r", analysis_model="sonnet", pdf_sha256=None)
    cur.execute("SELECT COUNT(*) FROM ipo_insights WHERE ipo_id=7 AND is_current")
    assert cur.fetchone()[0] == len(rows)
    c.close()


# ── wiring contracts ────────────────────────────────────────────────────────
def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_schema_sync_owns_the_ddl():
    src = _read("schema_sync.py")
    assert "CREATE TABLE IF NOT EXISTS ipo_insights" in src
    assert "CREATE TABLE IF NOT EXISTS ipo_stage_state" in src
    assert "ADD COLUMN IF NOT EXISTS pdf_sha256" in src
    assert "'CONFIRMED','PARTIAL','PENDING','FAILED'" in src


def test_store_script_persists_sha_and_fans_out():
    src = _read("rhp_sonnet_store.py")
    assert "pdf_sha256" in src and "from insights_fanout import fanout, store_insights" in src
    assert "LEGACY: no pdf fingerprint" in src


def test_vm_verify_flags_verdicts_without_fingerprint():
    src = _read("vm_verify.py")
    assert "pdf_sha256" in src and "legacy/stale" in src


def test_ofs_false_flag_with_detail_is_neutral_not_negative():
    """Review point 2026-07-21: a structured OFS fact must not auto-negative.
    direction derives from Sonnet's ofs_heavy flag: False -> neutral even
    with detail present; True -> negative; None -> incomplete."""
    rows = fx.fanout({"structure": {"ofs_heavy": False,
        "detail": "Offer is entirely a sale by an early institutional investor; promoters retain 74%."}})
    assert len(rows) == 1 and rows[0]["direction"] == "neutral"
    rows2 = fx.fanout({"structure": {"ofs_heavy": None,
        "detail": "Structure details partially disclosed."}})
    assert rows2[0]["direction"] == "incomplete"
