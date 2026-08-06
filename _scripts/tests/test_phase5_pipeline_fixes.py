#!/usr/bin/env python3
"""Phase-5 tests (2026-07-21): SEBI matcher tightening, RHP target hygiene,
persist-on-success, empty-dir prune, journal DDL fix, Haiku preflight.
Offline file-contract + executable checks; journal DDL proven on real Postgres.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ── A. RHP target hygiene (junk rows can no longer be permanent targets) ────
def test_targets_require_mainboard_and_real_dates():
    src = _read("fetch_new_rhps.py")
    assert "FROM ipo i" in src
    assert "i.is_mainboard = true" in src
    assert "listing_date IS NULL\n" not in src.split("NOT EXISTS")[0], \
        "NULL-dated junk rows must no longer qualify as targets"
    assert src.count("BETWEEN CURRENT_DATE - INTERVAL") == 3, \
        "each of open/close/listing must be window-bounded"
    assert "(days, days, days)" in src


# ── B. matcher: no 8-char substring; prospectus-typed titles only ──────────
def test_matcher_no_prefix_substring():
    src = _read("fetch_new_rhps.py")
    assert "k[:8] in ntitle" not in src, "the over-match leg must be gone"
    assert re.search(r"red herring\|prospectus", src), "positive doc-type filter missing"
    assert "ntitle == k" in src, "exact-title fallback for bare company titles"


# ── C. DB writes on success only; empty dirs pruned ────────────────────────
def test_rhp_url_persist_only_after_verified_download():
    src = _read("fetch_new_rhps.py")
    body = src[src.index("def _download_matched"):]
    first_persist = body.index("_persist_rhp_url(company, url)")
    first_success = body.index("got += 1")
    assert first_success < first_persist + 60, "persist must sit ON the success lines"
    assert "INSERT INTO ipo_rhp_intel" not in body.split("tried += 1")[0], \
        "no placeholder row before a download attempt"
    assert "_prune_empty_dirs()" in body


def test_prune_removes_only_empty(tmp_path):
    """Run the prune in a subprocess (the module re-wraps sys.stdout on import,
    which is hostile to in-process pytest capture)."""
    import subprocess
    (tmp_path / "empty-junk").mkdir()
    keep = tmp_path / "real-ipo"; keep.mkdir(); (keep / "rhp.pdf").write_bytes(b"%PDF-fake")
    code = (
        "import importlib.util, sys; "
        f"spec=importlib.util.spec_from_file_location('fnr', r'{os.path.join(ROOT, 'fetch_new_rhps.py')}'); "
        "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
        f"m.OUT_DIR=r'{tmp_path}'; m._prune_empty_dirs()"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[:300]
    assert not (tmp_path / "empty-junk").exists()
    assert (keep / "rhp.pdf").exists()


# ── D. journal DDL owned by schema_sync + proven on Postgres ───────────────
def test_schema_sync_owns_journal_outcome_columns():
    src = _read("schema_sync.py")
    for col in ("pnl_pct", "outcome", "thesis"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src, f"trade_journal.{col} unowned"


def test_journal_thesis_update_runs_on_synced_schema(pg_uri):
    """Execute the exact failing statement class against schema_sync's DDL."""
    import psycopg2
    import schema_sync as ss
    ddl = [s for s in ss.DDL if "trade_journal" in s] if hasattr(ss, "DDL") else []
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS trade_journal")
    if ddl:
        for s in ddl:
            cur.execute(s)
    else:  # fall back: run the module's statements by scanning source
        for s in re.findall(r'"""(CREATE TABLE IF NOT EXISTS trade_journal.*?)"""', _read("schema_sync.py"), re.S):
            cur.execute(s)
        for s in re.findall(r'"(ALTER TABLE trade_journal[^"]+)"', _read("schema_sync.py")):
            cur.execute(s)
    cur.execute("UPDATE trade_journal SET pnl_pct=1.0, outcome='win', thesis='t' WHERE false")
    c.close()  # no UndefinedColumn = the nightly crash class is closed


# ── E. Haiku preflight ─────────────────────────────────────────────────────
def test_haiku_preflight_names_the_fix():
    src = _read("sbi_haiku_extract.py")
    assert "ANTHROPIC_API_KEY missing" in src
    assert "anthropic client init failed" in src
    body = src[src.index("def main"):]
    assert body.index("if not todo") < body.index("import anthropic"), \
        "zero-work runs must exit clean BEFORE dep/key checks (no noise failures)"
