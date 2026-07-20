#!/usr/bin/env python3
"""Phase-7 (PR-C+PR-D+SBI-UI) tests."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)


def _read(*p):
    return open(os.path.join(REPO, *p), encoding="utf-8").read()


# ── stage_state executed on real Postgres ──────────────────────────────────
def test_record_upserts_attempts_and_backoff(pg_uri):
    import psycopg2
    spec = importlib.util.spec_from_file_location("st", os.path.join(ROOT, "lib", "stage_state.py"))
    st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
    c = psycopg2.connect(pg_uri); c.autocommit = False; cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS ipo_stage_state; DROP TABLE IF EXISTS ipo_intelligence")
    cur.execute("CREATE TABLE ipo_intelligence (id SERIAL PRIMARY KEY, company_name TEXT)")
    cur.execute("""CREATE TABLE ipo_stage_state (ipo_id INT, stage TEXT, status TEXT,
        attempt_count INT DEFAULT 0, started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
        last_error TEXT, next_retry_at TIMESTAMPTZ, input_fingerprint TEXT,
        output_fingerprint TEXT, pipeline_version TEXT, PRIMARY KEY (ipo_id, stage))""")
    cur.execute("INSERT INTO ipo_intelligence (company_name) VALUES ('Alpha Beta Limited')")
    c.commit()
    assert st.record(c, "Alpha Beta Ltd", "RHP_DOWNLOADED", "FAILED", error="boom", retry_minutes=360)
    assert st.record(c, "ALPHA BETA LIMITED", "RHP_DOWNLOADED", "FAILED", error="boom2", retry_minutes=360)
    cur.execute("SELECT attempt_count, next_retry_at > NOW(), last_error FROM ipo_stage_state")
    n, future, err = cur.fetchone()
    assert n == 2 and future is True and err == "boom2"
    assert st.record(c, "Alpha Beta Ltd", "RHP_DOWNLOADED", "CONFIRMED")
    cur.execute("SELECT status, completed_at IS NOT NULL, next_retry_at FROM ipo_stage_state")
    stt, done, retry = cur.fetchone()
    assert stt == "CONFIRMED" and done is True and retry is None
    assert st.record(c, "No Such Company", "RHP_DOWNLOADED", "FAILED") is False
    c.close()


def test_record_never_raises_without_table(pg_uri):
    import psycopg2
    spec = importlib.util.spec_from_file_location("st2", os.path.join(ROOT, "lib", "stage_state.py"))
    st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
    c = psycopg2.connect(pg_uri); cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS ipo_stage_state"); c.commit()
    assert st.record(c, "X", "RHP_DOWNLOADED", "FAILED") is False  # swallowed
    c.close()


# ── wiring contracts ────────────────────────────────────────────────────────
def test_fetch_honors_backoff_and_records_all_outcomes():
    src = _read("_scripts", "fetch_new_rhps.py")
    assert "st.next_retry_at > NOW()" in src and "st.stage = 'RHP_DOWNLOADED'" in src
    assert src.count('_stage(company, "FAILED"') >= 3, "every failure path records FAILED"
    assert src.count('_stage(company, "CONFIRMED")') == 2, "both success paths record CONFIRMED"


def test_sonnet_and_haiku_record_stages():
    assert '"SONNET_COMPLETE", "CONFIRMED", input_fp=pdf_sha' in _read("_scripts", "rhp_sonnet_store.py")
    assert '"SBI_EXTRACTED", "CONFIRMED"' in _read("_scripts", "sbi_haiku_extract.py")


def test_haiku_windows_path_fallback_repairs_source():
    src = _read("_scripts", "sbi_haiku_extract.py")
    assert 'os.path.basename(pdf_path.replace("\\\\", "/"))' in src
    assert "UPDATE ipo_research_notes SET pdf_path=%s WHERE id=%s" in src


# ── PR-D: readiness is server-attested; UI names the gaps ──────────────────
def test_live_preopen_attests_readiness():
    src = _read("app", "api", "ipo", "live-preopen", "route.ts")
    assert "research_ready: researchReady" in src
    assert "research_missing: researchMissing" in src
    assert '"RHP & SBI research both unread"' in src
    assert '"fair value inputs (EPS/peer P/E)"' in src, \
        "missing EPS/peer P/E must block readiness (fair value UNAVAILABLE rule)"


def test_live_ui_shows_incomplete_never_silent():
    src = _read("app", "dashboard", "ipo2", "page.tsx")
    assert "research_ready === false" in src
    assert "Research incomplete" in src and "WATCH, not BUY" in src


# ── SBI UI ─────────────────────────────────────────────────────────────────
def test_sbi_section_renders_parse_and_pending_language():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert "SBI SECURITIES RESEARCH" in src
    assert "SBI research note not available or not yet parsed." in src, "the directive's exact pending sentence"
    assert "peer_comparison" in src and "valuation_comment" in src
    assert "their call, not ours" in src


def test_rhp_evidence_list_quotes_the_document():
    src = _read("components", "ipo", "IpoCard.tsx")
    assert "the document&apos;s own words" in src  # lint-escaped apostrophe (Phase-8)
    assert "insights" in src and "excerpt" in src
