#!/usr/bin/env python3
"""Fair-value peer-P/E chain (2026-07-21): the SBI-note consumer that never
existed. median executed; fill-empty proven on real Postgres."""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("dpn", os.path.join(ROOT, "derive_peer_pe_from_notes.py"))
dpn = importlib.util.module_from_spec(spec); spec.loader.exec_module(dpn)


def test_median_needs_two_valid_peers_and_sanity_bounds():
    assert dpn.median_pe([{"pe": 20}, {"pe": 30}, {"pe": 40}]) == 30
    assert dpn.median_pe([{"pe": 20}, {"pe": 30}]) == 25
    assert dpn.median_pe([{"pe": 20}]) is None, "single peer too fragile"
    assert dpn.median_pe([{"pe": 0}, {"pe": 20}, {"pe": 9999}]) is None, "junk filtered; 1 valid left"
    assert dpn.median_pe([{"pe": None}, {"pe": "31.5"}, {"pe": 28}]) == 29.75
    assert dpn.median_pe(None) is None and dpn.median_pe([]) is None


def test_fill_empty_only_on_real_postgres(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS ipo_intelligence; DROP TABLE IF EXISTS ipo_research_notes")
    cur.execute("CREATE TABLE ipo_intelligence (id SERIAL PRIMARY KEY, company_name TEXT, nse_symbol TEXT, symbol TEXT, peer_median_pe NUMERIC)")
    cur.execute("CREATE TABLE ipo_research_notes (source TEXT, company TEXT, nse_symbol TEXT, full_json JSONB)")
    cur.execute("INSERT INTO ipo_intelligence (company_name, nse_symbol, peer_median_pe) VALUES ('Lohia Corp Limited','LOHIA',NULL), ('Prefilled Ltd','PREF', 12.0)")
    fj = json.dumps({"peer_comparison": [{"name": "A", "pe": 18}, {"name": "B", "pe": 26}]})
    cur.execute("INSERT INTO ipo_research_notes VALUES ('SBI','Lohia Corp Ltd','LOHIA',%s), ('SBI','Prefilled Limited','PREF',%s)", (fj, fj))
    cur.execute(dpn.WORK_SQL)
    work = cur.fetchall()
    assert [w[1] for w in work] == ["Lohia Corp Limited"], "prefilled row must NOT be work (fill-empty)"
    med = dpn.median_pe(json.loads(fj)["peer_comparison"]) if isinstance(fj, str) else None
    cur.execute("UPDATE ipo_intelligence SET peer_median_pe=%s WHERE id=%s AND peer_median_pe IS NULL", (med, work[0][0]))
    cur.execute("SELECT peer_median_pe FROM ipo_intelligence ORDER BY id")
    vals = [float(r[0]) for r in cur.fetchall()]
    assert vals == [22.0, 12.0], "NULL filled with median; prefilled untouched"
    c.close()


def test_pipeline_order_notes_before_screener_after_haiku():
    import re
    src = open(os.path.join(ROOT, "run_ipo_pipeline_lean.py"), encoding="utf-8").read()
    scripts = re.findall(r'step\("[^"]+",\s*\["([a-z_\.]+\.py)"', src)
    i_haiku = scripts.index("sbi_haiku_extract.py")
    i_notes = scripts.index("derive_peer_pe_from_notes.py")
    i_scr = scripts.index("fetch_peer_pe.py")
    assert i_haiku < i_notes < i_scr, f"step order wrong: {scripts[i_haiku:i_scr+1]}"


def test_ipomatrix_probe_discovers_not_guesses():
    src = open(os.path.join(ROOT, "ipomatrix_ingest.py"), encoding="utf-8").read()
    assert "unmapped kpi keys" in src and "peer/industry top-level keys" in src
    assert "peer_median_pe" not in src, "no peer field is written until the real key name is known"
