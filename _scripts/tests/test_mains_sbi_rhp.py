"""Main-path tests for rhp_sonnet. The legacy SBI regex main is archived. ZERO spend, ZERO network: PDFs are generated with fitz,
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
