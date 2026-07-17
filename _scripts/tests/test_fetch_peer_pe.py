"""Tests for _scripts/fetch_peer_pe.py (stubbed HTTP — NEVER hits screener.in)
and _scripts/compute_quality_score.py main (embedded PG).

fetch_peer_pe golden rule under test: fill-empty-only writes, and no network
call escapes the stub (any real URL raises).
"""
import sys, io, os, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
import fetch_peer_pe as F

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


# ---------- HTTP stub ----------

class _Resp:
    def __init__(self, status=200, text="", url=""):
        self.status_code, self.text, self.url = status, text, url

class StubSession:
    """Maps url-substring -> _Resp. Any unmapped URL FAILS the test — proof
    that nothing real is contacted."""
    def __init__(self, routes): self.routes, self.headers = routes, {}
    def get(self, url, **kw):
        for frag, resp in self.routes.items():
            if frag in url:
                resp.url = resp.url or url
                return resp
        raise AssertionError(f"unexpected network call: {url}")

PEERS_HTML = """<table><tr><th>Name</th><th>P/E</th></tr>
<tr><td>Subject Co</td><td>45.0</td></tr>
<tr><td>Peer A</td><td>30.0</td></tr>
<tr><td>Peer B</td><td>40.0</td></tr>
<tr><td>Median</td><td>35.5</td></tr></table>"""

PEERS_HTML_NO_MEDIAN = """<table><tr><th>Name</th><th>P/E</th></tr>
<tr><td>Subject Co</td><td>45.0</td></tr>
<tr><td>Peer A</td><td>30.0</td></tr>
<tr><td>Peer B</td><td>40.0</td></tr></table>"""


# ---------- get_company_id ----------

@pytest.mark.parametrize("html", [
    '<a href="/company/source/quarters/12345/">q</a>',
    '<div data-company-id="12345">x</div>',
    'fetch("/api/company/12345/")',
])
def test_company_id_each_pattern(html):
    s = StubSession({"/company/TEST/": _Resp(text=html)})
    cid, err = F.get_company_id(s, "TEST")
    assert cid == "12345" and err is None

def test_company_id_login_wall_detected():
    s = StubSession({"/company/TEST/": _Resp(text="<h1>Login</h1>", url="https://x/login")})
    cid, err = F.get_company_id(s, "TEST")
    assert cid is None and "login wall" in err

def test_company_id_http_error():
    s = StubSession({"/company/TEST/": _Resp(status=404)})
    cid, err = F.get_company_id(s, "TEST")
    assert cid is None and "HTTP 404" in err


# ---------- get_peer_median_pe ----------

def test_peer_pe_prefers_median_row():
    s = StubSession({"/peers/": _Resp(text=PEERS_HTML)})
    pe, n, note = F.get_peer_median_pe(s, "12345", "TEST")
    assert (pe, note) == (35.5, "median-row") and n == 2

def test_peer_pe_computes_when_no_median_row():
    s = StubSession({"/peers/": _Resp(text=PEERS_HTML_NO_MEDIAN)})
    pe, n, note = F.get_peer_median_pe(s, "12345", "TEST")
    assert note == "computed-median" and pe == 40.0     # median(45,30,40)

def test_peer_pe_endpoint_fallback_order():
    """First endpoint 404s -> second one answers -> still resolves."""
    s = StubSession({"/api/company/12345/peers/": _Resp(status=404),
                     "/company/12345/peers/": _Resp(text=PEERS_HTML)})
    pe, _, note = F.get_peer_median_pe(s, "12345", "TEST")
    assert pe == 35.5

def test_peer_pe_all_endpoints_fail():
    s = StubSession({"peers": _Resp(status=404)})
    pe, n, note = F.get_peer_median_pe(s, "12345", "TEST")
    assert pe is None and "endpoints failed" in note

def test_peer_pe_no_pe_column():
    s = StubSession({"/peers/": _Resp(text="<table><tr><th>Name</th><th>MCap</th></tr>"
                                           "<tr><td>A</td><td>1</td></tr></table>")})
    pe, n, note = F.get_peer_median_pe(s, "12345", "TEST")
    assert pe is None and "no P/E column" in note


# ---------- main: dry-run + GOLDEN RULE apply (embedded PG) ----------

def _routes_for(sym):
    return {f"/company/{sym}/": _Resp(text='data-company-id="777"'),
            "/peers/": _Resp(text=PEERS_HTML)}

def test_main_symbols_dry_run_no_db_needed(monkeypatch, capsys):
    monkeypatch.setattr(F, "make_session", lambda: StubSession(_routes_for("ABC")))
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["fetch_peer_pe", "--symbols", "ABC", "--dry-run"])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    F.main()
    out = capsys.readouterr().out
    assert "35.50" in out and "resolved peer_median_pe for 1/1" in out
    assert "dry-run — nothing written" in out

@pytest.mark.db
def test_main_apply_golden_rule_fill_empty_only(monkeypatch, capsys, pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (nse_symbol TEXT, peer_median_pe NUMERIC,
                                       listing_date DATE)""")
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('EMPTY', NULL, '2026-06-01'), ('FILLED', 99.9, '2026-06-02')""")
    monkeypatch.setattr(F, "make_session",
        lambda: StubSession({"/peers/": _Resp(text=PEERS_HTML),
                             "/company/EMPTY/": _Resp(text='data-company-id="777"')}))
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    monkeypatch.setenv("DATABASE_URL", pg_uri)
    monkeypatch.setenv("SCREENER_COOKIE", "stub=1")
    monkeypatch.setattr(sys, "argv", ["fetch_peer_pe", "--apply"])
    F.main()
    out = capsys.readouterr().out
    assert "wrote 1 new peer_median_pe" in out            # only EMPTY was in worklist
    cur.execute("SELECT nse_symbol, peer_median_pe FROM ipo_intelligence ORDER BY 1")
    rows = dict(cur.fetchall())
    assert float(rows["EMPTY"]) == 35.5
    assert float(rows["FILLED"]) == 99.9                  # GOLDEN RULE: untouched
    c.close()

def test_main_symbol_error_path_continues(monkeypatch, capsys):
    monkeypatch.setattr(F, "make_session",
        lambda: StubSession({"/company/BAD/": _Resp(status=404),
                             "/company/GOOD/": _Resp(text='data-company-id="777"'),
                             "/peers/": _Resp(text=PEERS_HTML)}))
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["fetch_peer_pe", "--symbols", "BAD", "GOOD", "--dry-run"])
    F.main()
    out = capsys.readouterr().out
    assert "✗ page HTTP 404" in out and "resolved peer_median_pe for 1/2" in out


# ---------- compute_quality_score main ----------

@pytest.mark.db
def test_quality_score_preview_and_apply(monkeypatch, capsys, pg_uri):
    import psycopg2, subprocess
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (id SERIAL PRIMARY KEY, company_name TEXT,
            promoter_pledge_pct NUMERIC, ofs_cr NUMERIC, fresh_issue_cr NUMERIC,
            ipo_pe NUMERIC, peer_median_pe NUMERIC, roe NUMERIC,
            revenue_cagr_3y NUMERIC, debt_equity NUMERIC, sbi_rating TEXT,
            brlm_names TEXT);
        CREATE TABLE ipo_rhp_intel (company_name TEXT, full_json TEXT);
        CREATE TABLE ipo_verdicts (company_name TEXT, quality_promoter BOOLEAN);""")
    cur.execute("""INSERT INTO ipo_intelligence
        (company_name, promoter_pledge_pct, ofs_cr, fresh_issue_cr, ipo_pe,
         peer_median_pe, roe, revenue_cagr_3y, debt_equity, sbi_rating)
        VALUES ('Rich Data Ltd', 0, 100, 400, 20, 25, 18, 22, 0.4, 'Subscribe'),
               ('No Data Ltd', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)""")

    def run(*args):
        env = dict(os.environ, DATABASE_URL=pg_uri)
        env.pop("NEON_DATABASE_URL", None)
        for k in [k for k in env if k.startswith(("COV_CORE", "COVERAGE"))]:
            env.pop(k)
        s = ROOT / "_scripts" / "compute_quality_score.py"
        cmd = ([sys.executable, "-m", "coverage", "run", "-p",
                f"--rcfile={ROOT}/.coveragerc", str(s)]
               if os.environ.get("SUBPROC_COV") else [sys.executable, str(s)])
        return subprocess.run([*cmd, *args], capture_output=True, text=True,
                              env=env, timeout=60, cwd=ROOT)

    r = run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "preview: would score" in r.stdout
    # preview ROLLS BACK everything incl. the ALTERs — zero trace is the contract
    cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_name='ipo_intelligence' AND column_name='quality_score'""")
    assert cur.fetchone()[0] == 0

    r2 = run("--apply")
    assert "COMMITTED" in r2.stdout
    cur.execute("""SELECT quality_score, quality_conf FROM ipo_intelligence
                   WHERE company_name='Rich Data Ltd'""")
    score, conf = cur.fetchone()
    assert score is not None and 0 <= score <= 100 and conf >= 25
    cur.execute("SELECT quality_score FROM ipo_intelligence WHERE company_name='No Data Ltd'")
    assert cur.fetchone()[0] is None                      # conf<25 -> never claims
    c.close()
