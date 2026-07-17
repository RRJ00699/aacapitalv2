"""Main-path tests for parse_sbi_notes and rhp_sonnet — the last two big
uncovered mains. ZERO spend, ZERO network: PDFs are generated with fitz,
the Sonnet API is a stub that counts calls, DB is embedded PG.
"""
import sys, os, io, json, types, pathlib, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration
fitz = pytest.importorskip("fitz")


def _make_pdf(path, lines):
    d = fitz.open(); p = d.new_page()
    y = 50
    for ln in lines:
        p.insert_text((50, y), ln); y += 18
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path)); d.close()


NOTE_LINES = ["Kusumgar Ltd IPO", "Price Band Rs 133 - 140 per share",
              "Fresh Issue (Rs Cr) 500.00", "Offer for Sale (Rs Cr) 250.00",
              "We recommend investors to SUBSCRIBE to the issue."]


# ================= parse_sbi_notes main =================

def _run_sbi(uri_or_none, tmp, *args):
    env = dict(os.environ)
    env.pop("NEON_DATABASE_URL", None)
    if uri_or_none: env["DATABASE_URL"] = uri_or_none
    else: env.pop("DATABASE_URL", None)
    for k in [k for k in env if k.startswith(("COV_CORE", "COVERAGE"))]:
        env.pop(k)
    if os.environ.get("SUBPROC_COV"):
        env["COVERAGE_FILE"] = str(ROOT / ".coverage")   # cwd=tmp: data must land in repo
    s = ROOT / "_scripts" / "parse_sbi_notes.py"
    cmd = ([sys.executable, "-m", "coverage", "run", "-p",
            f"--rcfile={ROOT}/.coveragerc", str(s)]
           if os.environ.get("SUBPROC_COV") else [sys.executable, str(s)])
    return subprocess.run([*cmd, *args], capture_output=True, text=True,
                          env=env, timeout=120, cwd=tmp)

def test_sbi_main_no_pdfs_exits_loud(tmp_path):
    r = _run_sbi(None, tmp_path, "--dir", str(tmp_path / "empty"))
    assert r.returncode != 0 and "no PDFs" in (r.stdout + r.stderr)

def test_sbi_main_dry_run_parses_and_stops(tmp_path):
    _make_pdf(tmp_path / "notes" / "Kusumgar Ltd_IPO Note.pdf", NOTE_LINES)
    r = _run_sbi(None, tmp_path, "--dir", str(tmp_path / "notes"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "parsed 1 notes" in r.stdout
    assert "dry-run — add --write-db to persist." in r.stdout

def test_sbi_main_debug_prints_json_first_file_only(tmp_path):
    _make_pdf(tmp_path / "notes" / "Kusumgar Ltd_IPO Note.pdf", NOTE_LINES)
    _make_pdf(tmp_path / "notes" / "Zeta Ltd_IPO Note.pdf", NOTE_LINES)
    r = _run_sbi(None, tmp_path, "--dir", str(tmp_path / "notes"), "--debug")
    assert '"company": "Kusumgar Ltd"' in r.stdout
    assert "Zeta" not in r.stdout                        # debug = first file, then return

@pytest.mark.db
def test_sbi_main_write_db_fuzzy_attach_and_fill_empty(tmp_path, pg_uri):
    """PINNED (ledger #9): symbol attach uses rapidfuzz token_sort >=88 — a
    FUZZY name join feeding peer/sbi fills, in tension with SCHEMA RULE 2.
    Behavior pinned exactly: close name (matches) attaches + fills empties;
    fill is COALESCE-gated; upsert not duplicate."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (company_name TEXT, nse_symbol TEXT,
            sbi_rating TEXT, peer_median_pe NUMERIC)""")
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('Kusumgar Ltd', 'KUSUM', 'PreExisting', NULL),
        ('Kusumgar Limited', 'KUSVAR', NULL, NULL),
        ('Totally Different Co', 'DIFF', NULL, NULL)""")
    _make_pdf(tmp_path / "notes" / "Kusumgar Ltd_IPO Note.pdf", NOTE_LINES)
    r = _run_sbi(pg_uri, tmp_path, "--dir", str(tmp_path / "notes"), "--write-db")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ipo_research_notes: 1 rows" in r.stdout
    cur.execute("SELECT nse_symbol, rating FROM ipo_research_notes")
    nse, rating = cur.fetchone()
    assert nse == "KUSUM"                                # exact-name 100 match attaches
    assert rating == "Subscribe"
    cur.execute("SELECT sbi_rating FROM ipo_intelligence WHERE nse_symbol='KUSUM'")
    assert cur.fetchone()[0] == "PreExisting"            # COALESCE: not clobbered
    # rerun -> upsert, still 1 row
    r2 = _run_sbi(pg_uri, tmp_path, "--dir", str(tmp_path / "notes"), "--write-db")
    cur.execute("SELECT COUNT(*) FROM ipo_research_notes")
    assert cur.fetchone()[0] == 1
    c.close()

@pytest.mark.db
def test_sbi_fuzzy_misses_ltd_vs_limited(tmp_path, pg_uri):
    """PINNED GAP (ledger #9b): 'X Ltd' vs 'X Limited' scores 85.7 — BELOW
    the 88 threshold — so the commonest suffix variant never attaches a
    symbol, and the peer/sbi enrichment silently skips it (the exact
    SCHEMA failure mode the sync step was built to fix)."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (company_name TEXT, nse_symbol TEXT,
            sbi_rating TEXT, peer_median_pe NUMERIC)""")
    cur.execute("INSERT INTO ipo_intelligence VALUES ('Kusumgar Limited','KUSUM',NULL,NULL)")
    _make_pdf(tmp_path / "notes" / "Kusumgar Ltd_IPO Note.pdf", NOTE_LINES)
    _run_sbi(pg_uri, tmp_path, "--dir", str(tmp_path / "notes"), "--write-db")
    cur.execute("SELECT nse_symbol FROM ipo_research_notes")
    assert cur.fetchone()[0] is None                     # did NOT attach
    cur.execute("SELECT sbi_rating FROM ipo_intelligence")
    assert cur.fetchone()[0] is None                     # enrichment skipped
    c.close()


# ================= rhp_sonnet main (in-process, mocked API) =================

@pytest.fixture
def rhp(monkeypatch, tmp_path):
    """Import rhp_sonnet under the stdio guard, stub rhp_sections + API."""
    _o, _e = sys.stdout, sys.stderr
    import rhp_sonnet as R
    for _w, _orig in ((sys.stdout, _o), (sys.stderr, _e)):
        if _w is not _orig and isinstance(_w, io.TextIOWrapper):
            try: _w.detach()
            except Exception: pass
    sys.stdout, sys.stderr = _o, _e
    stub_sections = types.ModuleType("rhp_sections")
    stub_sections.gather_sections = lambda pages: {"RISK FACTORS": "some risks"}
    monkeypatch.setitem(sys.modules, "rhp_sections", stub_sections)
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-FAKE-never-sent")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    calls = []
    def fake_call(system, prompt, key, max_tokens=4000):
        calls.append(prompt)
        return json.dumps({"verdict": "clean", "one_line": "solid business"}), 60_000, 2_000
    monkeypatch.setattr(R, "call_sonnet", fake_call)
    return R, calls, tmp_path

def _rhp_main(R, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["rhp_sonnet.py", *args])
    R.main()

def test_rhp_main_happy_path_writes_summary(rhp, monkeypatch, capsys):
    R, calls, tmp = rhp
    _make_pdf(tmp / "rhps" / "Alpha Corp" / "rhp.pdf", ["RISK FACTORS", "text"])
    _rhp_main(R, monkeypatch, "--dir", str(tmp / "rhps"), "--out-dir", str(tmp / "out"))
    out = capsys.readouterr().out
    assert len(calls) == 1
    assert "✓ Alpha Corp" in out and "$0.21" in out       # 60k in + 2k out
    data = json.load(open(tmp / "out" / "Alpha Corp_summary.json"))
    assert data["verdict"] == "clean" and data["_meta"]["cost_usd"] == 0.21
    assert (tmp / "out" / "Alpha Corp_raw.txt").exists()  # raw persisted before parse

def test_rhp_main_skips_already_done_zero_calls(rhp, monkeypatch, capsys):
    R, calls, tmp = rhp
    _make_pdf(tmp / "rhps" / "Alpha Corp" / "rhp.pdf", ["x"])
    (tmp / "out").mkdir()
    json.dump({"verdict": "clean"}, open(tmp / "out" / "Alpha Corp_summary.json", "w"))
    _rhp_main(R, monkeypatch, "--dir", str(tmp / "rhps"), "--out-dir", str(tmp / "out"))
    assert "⏭" in capsys.readouterr().out
    assert calls == []                                    # not one cent

def test_rhp_main_three_parse_fails_stop_run(rhp, monkeypatch, capsys):
    """3 consecutive unparseable responses must halt — not burn the batch."""
    R, calls, tmp = rhp
    monkeypatch.setattr(R, "parse_json", lambda t: (_ for _ in ()).throw(ValueError("nope")))
    for co in ("A Co", "B Co", "C Co", "D Co"):
        _make_pdf(tmp / "rhps" / co / "rhp.pdf", ["x"])
    _rhp_main(R, monkeypatch, "--dir", str(tmp / "rhps"), "--out-dir", str(tmp / "out"))
    out = capsys.readouterr().out
    assert "3 consecutive parse-fails" in out
    assert len(calls) == 3                                # 4th never called
    assert "_parse_error" in json.load(open(next((tmp / "out").glob("*_summary.json"))))

def test_rhp_main_cap_stops_mid_run(rhp, monkeypatch, capsys):
    """cap $0.20 < first call cost ($0.21) cumulative — second PDF must not be paid."""
    R, calls, tmp = rhp
    _make_pdf(tmp / "rhps" / "A Co" / "rhp.pdf", ["x"])
    _make_pdf(tmp / "rhps" / "B Co" / "rhp.pdf", ["x"])
    _rhp_main(R, monkeypatch, "--dir", str(tmp / "rhps"),
              "--out-dir", str(tmp / "out"), "--cap", "0.2")
    out = capsys.readouterr().out
    assert len(calls) == 1 and "HARD CAP $0.2 reached" in out
    assert "STOPPED at cap" in out

def test_rhp_main_no_sections_skips_without_spend(rhp, monkeypatch, capsys):
    R, calls, tmp = rhp
    sys.modules["rhp_sections"].gather_sections = lambda pages: {}
    _make_pdf(tmp / "rhps" / "A Co" / "rhp.pdf", ["x"])
    _rhp_main(R, monkeypatch, "--dir", str(tmp / "rhps"), "--out-dir", str(tmp / "out"))
    assert "no sections located" in capsys.readouterr().out
    assert calls == []

def test_rhp_main_limit_respected(rhp, monkeypatch, capsys):
    R, calls, tmp = rhp
    for co in ("A Co", "B Co", "C Co"):
        _make_pdf(tmp / "rhps" / co / "rhp.pdf", ["x"])
    _rhp_main(R, monkeypatch, "--dir", str(tmp / "rhps"),
              "--out-dir", str(tmp / "out"), "--limit", "1")
    assert len(calls) == 1

@pytest.mark.db
def test_rhp_main_year_min_flat_file_fallback(rhp, monkeypatch, capsys, pg_uri):
    """The Caliber 2026-07-17 fix: a PDF dropped FLAT in the scan root must
    match by FILENAME (dirname would be the root and silently vanish)."""
    import psycopg2
    R, calls, tmp = rhp
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (company_name TEXT, listing_date DATE);
        INSERT INTO ipo_intelligence VALUES
            ('Caliber Mining Ltd', '2026-07-10'), ('Old Co Ltd', '2019-01-01')""")
    monkeypatch.setenv("DATABASE_URL", pg_uri)
    _make_pdf(tmp / "rhps" / "Caliber-Mining.pdf", ["x"])          # FLAT
    _make_pdf(tmp / "rhps" / "Old Co" / "rhp.pdf", ["x"])          # pre-year-min
    _rhp_main(R, monkeypatch, "--dir", str(tmp / "rhps"),
              "--out-dir", str(tmp / "out"), "--year-min", "2025")
    out = capsys.readouterr().out
    assert "1 RHPs listed 2025+" in out                   # Old Co filtered out
    assert len(calls) == 1                                # Caliber found via filename
    c.close()
