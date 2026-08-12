"""Phase 3 A4 — cron idle-window: the every-minute job_runner must not touch
Neon on an empty poll. Deterministic (clock and flag endpoint stubbed; the
flag helper is proven to make ZERO network calls when unkeyed).

Also guards the SOURCE ORDER the throttle depends on: the __main__ idle gate
must sit BEFORE `import psycopg2`, which must sit before any connect — a
refactor that reorders them re-creates the ~6 CU-h/day idle bill silently.
"""
import sys, os, types, datetime, pathlib, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
import job_runner as J

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = (ROOT / "_scripts" / "job_runner.py").read_text(encoding="utf-8")
pytestmark = pytest.mark.unit
JOB_RUNS_DDL = """CREATE TABLE job_runs (
    id BIGSERIAL PRIMARY KEY, job TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued', requested_by TEXT,
    requested_at TIMESTAMPTZ DEFAULT now(), started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ, exit_code INT, error TEXT, log_tail TEXT)"""


# ---------- source-order contract ----------

def test_idle_gate_sits_before_db_import_before_connect():
    gate = SRC.index('if __name__ == "__main__" and _should_exit_idle()')
    imp = SRC.index("import psycopg2")
    conn = SRC.index("psycopg2.connect")
    assert gate < imp < conn, "idle gate / psycopg2 import / connect reordered — idle bill returns"


# ---------- _throttled(): the IST clock windows ----------

def _at(monkeypatch, wd, hour, minute):
    """Fake IST wall-clock: utcnow such that IST = given weekday/hour/minute."""
    base = datetime.datetime(2026, 7, 13)                 # a Monday
    ist = base + datetime.timedelta(days=wd, hours=hour, minutes=minute)
    utc = ist - datetime.timedelta(hours=5, minutes=30)
    class FakeDT(datetime.datetime):
        @classmethod
        def utcnow(cls): return utc
    monkeypatch.setattr(J.datetime, "datetime", FakeDT)

@pytest.mark.parametrize("wd,h,m,throttled", [
    (0, 12, 7, False),    # Mon noon: ACTIVE -> never throttled
    (0, 7, 1, False),     # active window opens 07:00
    (0, 6, 59, True),     # 06:59, minute 59: throttled
    (0, 6, 50, False),    # 06:50: tens-minute poll allowed
    (0, 23, 30, False),   # window closes 23:30 inclusive
    (0, 23, 31, True),    # 23:31: throttled
    (0, 23, 40, False),   # 23:40: tens-minute allowed
    (6, 12, 5, True),     # Sunday midday, minute 5: throttled
    (6, 12, 10, False),   # Sunday, tens-minute: allowed
])
def test_throttle_windows(monkeypatch, wd, h, m, throttled):
    _at(monkeypatch, wd, h, m)
    assert J._throttled() is throttled


# ---------- _flag_pending(): zero network unless keyed ----------

def test_flag_unkeyed_returns_none_zero_network(monkeypatch):
    monkeypatch.delenv("ADMIN_JOB_KEY", raising=False)
    import urllib.request as _ur
    def boom(*a, **k): raise AssertionError("network call without ADMIN_JOB_KEY")
    monkeypatch.setattr(_ur, "urlopen", boom)
    assert J._flag_pending() is None

@pytest.mark.parametrize("body,expected", [
    (b'{"ok": true, "pending": true}', True),
    (b'{"ok": true, "pending": false}', False),
    (b'{"ok": false}', None),
])
def test_flag_keyed_paths(monkeypatch, body, expected):
    monkeypatch.setenv("ADMIN_JOB_KEY", "k")
    import urllib.request as _ur, io
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: io.BytesIO(body))
    assert J._flag_pending() is expected

def test_flag_endpoint_error_returns_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JOB_KEY", "k")
    import urllib.request as _ur
    def boom(*a, **k): raise OSError("down")
    monkeypatch.setattr(_ur, "urlopen", boom)
    assert J._flag_pending() is None


# ---------- the A4 gate matrix ----------

@pytest.mark.parametrize("flag,throttled,exits", [
    (False, False, True),   # flag says empty -> exit, even in active hours
    (False, True,  True),
    (True,  True,  False),  # job queued -> ALWAYS proceed, even at 3am Sunday
    (True,  False, False),
    (None,  True,  True),   # flag down + idle window -> exit
    (None,  False, False),  # flag down + active window -> poll
])
def test_should_exit_idle_matrix(monkeypatch, flag, throttled, exits):
    monkeypatch.setattr(J, "_flag_pending", lambda: flag)
    monkeypatch.setattr(J, "_throttled", lambda: throttled)
    assert J._should_exit_idle() is exits


# ---------- main(): empty poll + whitelist vs embedded PG ----------

@pytest.mark.db
def test_main_empty_queue_single_pass_no_jobs_run(monkeypatch, capsys, pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;" + JOB_RUNS_DDL)
    monkeypatch.setattr(J, "DB", pg_uri)
    ran = []
    monkeypatch.setattr(J, "run_job", lambda job: ran.append(job) or (0, "", None))
    J.main()
    assert ran == []                                      # nothing executed
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM job_runs")          # table ensured, empty
    assert cur.fetchone()[0] == 0
    assert capsys.readouterr().out == ""                  # silent on empty poll
    c.close()

@pytest.mark.db
def test_main_claims_runs_and_records_queued_job(monkeypatch, pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;" + JOB_RUNS_DDL)
    monkeypatch.setattr(J, "DB", pg_uri)
    monkeypatch.setattr(J, "run_job",
                        lambda job: (0, "did the thing", None) if job == "gmp" else (2, "", "boom"))
    import psycopg2 as pg
    c2 = pg.connect(pg_uri); c2.autocommit = True
    J.ensure_table(c2.cursor())
    c2.cursor().execute("INSERT INTO job_runs (job) VALUES ('gmp'), ('badjob')")
    J.main()
    cur = c.cursor()
    cur.execute("SELECT job, status, exit_code, log_tail FROM job_runs ORDER BY job")
    rows = {r[0]: r[1:] for r in cur.fetchall()}
    assert rows["gmp"] == ("done", 0, "did the thing")
    assert rows["badjob"][0] == "failed"
    c.close(); c2.close()

def test_unknown_job_rejected_by_whitelist():
    code, tail, err = J.run_job("rm_-rf_evil")
    assert code == 2 and "not in whitelist" in err
