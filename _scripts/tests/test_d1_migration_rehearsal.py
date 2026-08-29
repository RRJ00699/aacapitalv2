"""Real local rehearsal salvaged into canonical PR #343 (no legacy #342 schema)."""
import hashlib, json, shutil, sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
import tools.d1_migration as migration
import tools.d1_reconcile as reconciliation

REPO=Path(__file__).resolve().parents[2]

@pytest.mark.skipif(shutil.which("npx") is None,reason="npx unavailable")
def test_neon_shape_and_matrix_raw_reach_wrangler_local_without_loss(tmp_path,monkeypatch):
    migrations=tmp_path/"migrations";migrations.mkdir()
    shutil.copy(REPO/"d1/migrations/0001_functional_model.sql",migrations/"0001_functional_model.sql")
    config=tmp_path/"wrangler.jsonc"
    config.write_text(json.dumps({"name":"d1-rehearsal","compatibility_date":"2026-08-23",
      "d1_databases":[{"binding":"DB","database_name":"rehearsal","database_id":"00000000-0000-0000-0000-000000000000","migrations_dir":"migrations"}]}))
    monkeypatch.setattr(migration,"WRANGLER",config);monkeypatch.setattr(reconciliation,"CONFIG",config)
    migration.wrangler(["migrations","apply","DB"])
    ipo={"id":1,"isin":"INE123456789","name_display":"Example Limited","name_norm":"example",
      "symbol":"EXAMPLE","ipomatrix_id":42,"security_kind":"EQUITY","status":"LISTED","created_at":"2026-01-01"}
    issue={"ipo_id":1,"open_date":"2026-01-01","close_date":"2026-01-03","allotment_date":"2026-01-04","listing_date":"2026-01-08",
      "band_lo":Decimal("95.10"),"band_hi":Decimal("100.20"),"issue_price":Decimal("100.20"),"face_value":Decimal("10"),"lot_size":100,
      "issue_size_cr":Decimal("500.30"),"fresh_cr":Decimal("300.10"),"ofs_cr":Decimal("200.20"),"registrar":"R"}
    daily={"ipo_id":1,"d":"2026-01-08","o":Decimal("105"),"h":Decimal("110"),"l":Decimal("102"),"c":Decimal("108"),"v":1000}
    statements=[]
    for dataset,row in (("ipo",ipo),("ipo_issue",issue),("market_daily",daily)):
        statements.extend(migration.transform_neon(dataset,row))
    payload={"reviewed":{"id":42,"name":"Example Limited","isin":"INE123456789","about":"Profile from raw",
      "financials":[{"period":"FY25","basis":"consolidated","income":"100000000","pat":"10000000"}]}}
    raw=json.dumps(payload,separators=(",",":"));sha=hashlib.sha256(raw.encode()).hexdigest()
    statements.append(migration.insert_sql("raw_objects",("sha256","source_name","source_object_id","size_bytes","payload_json"),(sha,"ipomatrix","42",len(raw),raw)))
    mapping={"matrix_id":"$.reviewed.id","name":"$.reviewed.name","isin":"$.reviewed.isin","reviewed":True,
      "company_profile":{"business_description":{"path":"$.reviewed.about"}},
      "financial_statements":{"rows":"$.reviewed.financials","fields":{"period":{"path":"period"},"basis":{"path":"basis"},
        "total_income_cr":{"path":"income","unit":"rs","normalized_unit":"cr"},"pat_cr":{"path":"pat","unit":"rs","normalized_unit":"cr"}}}}
    bootstrap,bootstrap_counts=migration.transform_ipomatrix(payload,sha,mapping);statements.extend(bootstrap)
    migration.apply_local(statements);migration.apply_local(statements)  # real idempotent rerun
    dump=tmp_path/"export.sql";reconciliation.export_local(dump);conn=sqlite3.connect(":memory:");conn.executescript(dump.read_text())
    source={"source_ipo":1,"source_ipo_issue":1,"source_market_daily":1,"source_ipomatrix":1,**bootstrap_counts}
    report=reconciliation.reconcile(conn,source)
    assert report["zero_silent_loss"] is True
    assert {f"ipomatrix_{name}" for name in ("company_profile","ownership","objects_of_issue","reservations","anchor_summary","anchor_allocations","peer_comparisons")} <= report["source_comparisons"].keys()
    assert report["ipo"]["destination_rows"]==1 and report["raw_objects"]["destination_rows"]==1
    assert report["market_1d"]["destination_rows"]==1 and report["critical_checks"]["quarantined_rows"]==0
    assert conn.execute("select business_description from company_profile").fetchone()[0]=="Profile from raw"
    assert conn.execute("select total_income_cr,pat_cr from financial_statements").fetchone()==("10","1")
