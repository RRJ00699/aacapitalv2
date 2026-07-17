"""Tests for _scripts/rhp_sonnet.py — the paid extraction path. ZERO API spend:
everything here is pure logic, embedded PG, or a --cap 0 subprocess that must
stop before any call.

Covers guardrail G (spend idempotency): content-hash skip, hard cap, and pins
the locked rate constants so a silent pricing edit fails CI.
"""
import sys, json, pathlib, subprocess, os, io
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest

# rhp_sonnet re-wraps sys.stdout/stderr AT IMPORT (Windows utf-8 shim,
# lines 12-15) — the wrapper closes pytest's capture buffer when GC'd.
# Import under guard: restore the originals and detach the wrappers so the
# captured stream is never closed. (Module-level side effect: bug-ledger.)
_orig_out, _orig_err = sys.stdout, sys.stderr
import rhp_sonnet as R
for _w, _o in ((sys.stdout, _orig_out), (sys.stderr, _orig_err)):
    if _w is not _o and isinstance(_w, io.TextIOWrapper):
        try: _w.detach()
        except Exception: pass
sys.stdout, sys.stderr = _orig_out, _orig_err

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


# ---------- locked spend constants ----------

def test_rate_constants_pinned():
    """Locked numbers: cost math must not drift silently."""
    assert R.MODEL == "claude-sonnet-4-6"
    assert R.IN_RATE == 3.00 / 1_000_000
    assert R.OUT_RATE == 15.00 / 1_000_000

def test_cost_of_typical_call():
    """~60k in / 2k out ≈ $0.21 — the per-RHP budget expectation."""
    assert round(60_000 * R.IN_RATE + 2_000 * R.OUT_RATE, 2) == 0.21


# ---------- _pdf_sha256 ----------

def test_sha256_matches_content_not_name(tmp_path):
    a = tmp_path / "original.pdf"; a.write_bytes(b"%PDF-1.4 fake body")
    b = tmp_path / "renamed_reseeded.pdf"; b.write_bytes(b"%PDF-1.4 fake body")
    c = tmp_path / "different.pdf"; c.write_bytes(b"%PDF-1.4 other body")
    assert R._pdf_sha256(str(a)) == R._pdf_sha256(str(b))     # rename can't re-burn
    assert R._pdf_sha256(str(a)) != R._pdf_sha256(str(c))


# ---------- _already_extracted (guardrail G) ----------

@pytest.mark.db
def test_already_extracted_hits_on_stored_hash(pg_uri):
    import psycopg2
    conn = psycopg2.connect(pg_uri); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_rhp_intel (company_name TEXT, pdf_sha256 TEXT)""")
    cur.execute("INSERT INTO ipo_rhp_intel VALUES ('Done Ltd', 'abc123')")
    assert R._already_extracted(conn, "abc123") is True
    assert R._already_extracted(conn, "neverseen") is False
    conn.close()

def test_already_extracted_none_conn_is_false():
    assert R._already_extracted(None, "abc") is False

@pytest.mark.db
def test_already_extracted_db_error_fails_open(pg_uri):
    """PINNED (bug-ledger candidate): a DB error returns False -> the PDF is
    re-paid. Fail-open protects availability but spends money on outages."""
    import psycopg2
    conn = psycopg2.connect(pg_uri); conn.autocommit = True
    conn.cursor().execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_rhp_intel (company_name TEXT)""")   # no pdf_sha256 col
    assert R._already_extracted(conn, "abc") is False
    conn.close()


# ---------- parse_json recovery ----------

def test_parse_clean_json():
    assert R.parse_json('{"verdict": "clean", "n": 1}') == {"verdict": "clean", "n": 1}

def test_parse_strips_markdown_fence():
    assert R.parse_json('```json\n{"a": 1}\n```') == {"a": 1}

def test_parse_skips_preamble_text():
    assert R.parse_json('Here is the analysis:\n{"a": 1}') == {"a": 1}

def test_parse_recovers_truncated_json():
    """Token-limit truncation: trim to last complete value, close braces."""
    out = R.parse_json('{"verdict": "clean", "risks": ["a", "b"], "partial_key": "cut off he')
    assert out["verdict"] == "clean" and out["risks"] == ["a", "b"]

def test_parse_recovers_truncated_nested():
    out = R.parse_json('{"outer": {"inner": {"k": "v"}, "list": [1, 2')
    assert out["outer"]["inner"] == {"k": "v"}

def test_parse_no_json_returns_empty():
    assert R.parse_json("I cannot analyze this document.") == {}


# ---------- build_prompt contract ----------

def test_build_prompt_contains_company_sections_and_rules():
    p = R.build_prompt("Test Corp Ltd", {"LITIGATION": "Nil", "RISK FACTORS": "..."})
    assert "Test Corp Ltd" in p
    assert "===== SECTION: LITIGATION =====" in p and "Nil" in p
    assert "Negations mean CLEAN" in p                 # the false-positive guard
    assert "NOT a buy/sell call" in p                  # the decision disclaimer
    assert "Return ONLY the JSON" in p


# ---------- hard cap: --cap 0 must stop before ANY call ----------

@pytest.mark.integration
def test_cap_zero_stops_before_any_api_call(tmp_path):
    pytest.importorskip("fitz", reason="pymupdf not installed")
    d = tmp_path / "rhps"; d.mkdir()
    (d / "Dummy Ltd.pdf").write_bytes(b"%PDF-1.4 not a real pdf")
    env = dict(os.environ, ANTHROPIC_API_KEY="sk-ant-FAKE-must-never-be-sent")
    env.pop("DATABASE_URL", None); env.pop("NEON_DATABASE_URL", None)
    for k in [k for k in env if k.startswith(("COV_CORE", "COVERAGE"))]:
        env.pop(k)
    cov = ([sys.executable, "-m", "coverage", "run", "-p", f"--rcfile={ROOT}/.coveragerc", str(ROOT / "_scripts" / "rhp_sonnet.py")]
           if os.environ.get("SUBPROC_COV") else [sys.executable, str(ROOT / "_scripts" / "rhp_sonnet.py")])
    r = subprocess.run([*cov,
                        "--dir", str(d), "--cap", "0", "--out-dir", str(tmp_path / "out")],
                       capture_output=True, text=True, timeout=120, cwd=tmp_path, env=env)
    assert "HARD CAP" in r.stdout, r.stdout + r.stderr
    assert "api_error" not in (r.stdout + r.stderr)    # no call was attempted
