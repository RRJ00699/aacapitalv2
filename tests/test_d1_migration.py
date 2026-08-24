import hashlib, json, sqlite3
from decimal import Decimal
from pathlib import Path
import pytest
import tools.d1_migration as d1m

from tools.d1_migration import (decimal_text, fingerprint, inventory, name_norm,
    NEON_QUERIES, checkpoint_sql, datasets_for_scope, derive_security_kind, derived_source_fact_sql, insert_sql, map_ipomatrix_identity, normalize_legacy_status, resolve_identity, survey, transform_ipomatrix,
    transform_neon, validate_issue)
from tools.d1_reconcile import reconcile
from tools.d1_contract import canonical_spine_eligible, concept_state

DDL=Path("d1/migrations/0001_functional_model.sql").read_text()

@pytest.fixture
def db():
    conn=sqlite3.connect(":memory:"); conn.executescript(DDL); yield conn; conn.close()

def test_schema_is_idempotent_for_content_writes(db):
    ipo=resolve_identity(db,isin="INE123456789",name="Example Limited")
    fp=fingerprint(ipo,"1d","2026-01-01",10,11,9,10.5,100)
    sql="INSERT INTO market_bars VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(content_fingerprint) DO NOTHING"
    args=(ipo,"1d","2026-01-01",10,11,9,10.5,100,"kite",fp)
    db.execute(sql,args); db.execute(sql,args)
    assert db.execute("select count(*) from market_bars").fetchone()[0]==1

def test_insert_strategy_never_globally_ignores_constraints(db):
    assert "OR IGNORE" not in Path("tools/d1_migration.py").read_text()
    db.executescript(insert_sql("ipo",("id","name","name_norm"),(1,"One","one")))
    db.executescript(insert_sql("ipo",("id","name","name_norm"),(1,"One","one")))
    assert db.execute("select count(*) from ipo").fetchone()[0]==1
    assert "SELECT CASE WHEN EXISTS" not in insert_sql("ipo",("id","name","name_norm"),(1,"One","one"))
    with pytest.raises(sqlite3.OperationalError,match="overflow"):
        db.executescript(insert_sql("ipo",("id","name","name_norm"),(1,"Different","different")))
    with pytest.raises(sqlite3.IntegrityError):
        db.executescript(insert_sql("ipo_issue",("ipo_id","band_lo_rs","band_hi_rs"),(1,"120","100")))
    with pytest.raises(sqlite3.IntegrityError):
        db.executescript(insert_sql("objects_of_issue",("ipo_id","row_order","document_sha256"),(1,1,"a"*64)))
    db.executescript(insert_sql("ipo",("name","name_norm","nse_symbol"),("Two","two","SAME")))
    with pytest.raises(sqlite3.IntegrityError):
        db.executescript(insert_sql("ipo",("name","name_norm","nse_symbol"),("Three","three","SAME")))

def test_bulk_writer_is_fk_ordered_bounded_and_has_no_row_selects(monkeypatch):
    seen=[]
    def fake(args):
        text=Path(args[args.index("--file")+1]).read_text(encoding="utf-8");seen.append(text)
    monkeypatch.setattr(d1m,"wrangler",fake)
    lines=[insert_sql("raw_objects",("sha256","source_name","size_bytes","payload_json"),("a"*64,"ipomatrix",2,"{}")),
      insert_sql("company_profile",("ipo_id","business_description"),(1,"x")),
      insert_sql("ipo",("id","name","name_norm"),(1,"One","one"))]
    stats=d1m.apply_sql(lines,max_statements=10)
    combined="\n".join(seen)
    assert combined.index("INSERT INTO ipo(") < combined.index("company_profile") < combined.index("raw_objects")
    assert all("SELECT CASE WHEN EXISTS" not in sql for sql in seen)
    assert stats["raw_objects"]=={"source_rows":1,"multirow_statements":1,"sql_files":1}

def test_high_volume_rows_are_multirow_batched_and_rerun_safe(db):
    db.execute("INSERT INTO ipo(id,name,name_norm) VALUES(1,'One','one')")
    rows=[]
    for day in range(1,1102):
        values=(1,"1d",f"2020-01-{day:04d}","1","2","1","2",100,"neon",f"fp-{day}")
        rows.append(insert_sql("market_bars",("ipo_id","interval","ts","open_rs","high_rs","low_rs","close_rs","volume_shares","source_name","content_fingerprint"),values))
    batches=d1m._bulk_statements("market_bars",rows,500,750_000)
    assert [count for _,count in batches]==[500,500,101]
    assert all(sql.count("INSERT INTO market_bars")==1 and sql.count("),(")>=100 for sql,_ in batches)
    for sql,_ in batches:db.executescript(sql)
    for sql,_ in batches:db.executescript(sql)
    assert db.execute("SELECT count(*) FROM market_bars").fetchone()[0]==1101

def test_bulk_statement_byte_ceiling_is_enforced():
    row=insert_sql("raw_objects",("sha256","source_name","size_bytes","payload_json"),("a"*64,"ipomatrix",200,"x"*200))
    with pytest.raises(ValueError,match="max-sql-bytes"):
        d1m._bulk_statements("raw_objects",[row],500,100)

def test_wrangler_uses_windows_npx_cmd_and_utf8(monkeypatch):
    captured={}
    monkeypatch.setattr(d1m.platform,"system",lambda:"Windows")
    monkeypatch.setattr(d1m.subprocess,"run",lambda cmd,**kwargs:captured.update(cmd=cmd,kwargs=kwargs))
    d1m.wrangler(["execute","DB","--file","x.sql"])
    assert captured["cmd"][0]=="npx.cmd" and captured["kwargs"]["encoding"]=="utf-8"

def test_canonical_decimal_columns_never_use_real():
    assert " REAL" not in DDL.upper()
    for column in ("band_lo_rs TEXT","issue_size_cr TEXT","open_rs TEXT","pe_x TEXT","confidence TEXT"):
        assert column in DDL

def test_decimal_text_never_roundtrips_through_float():
    assert decimal_text(Decimal("11961618350.2900"))=="11961618350.29"
    assert decimal_text("0.10000000000000000001")=="0.10000000000000000001"

def test_identity_precedence_and_collision(db):
    one=resolve_identity(db,isin="INE123456789",name="Example Limited")
    assert resolve_identity(db,isin="INE123456789",name="Example Ltd")==one
    resolve_identity(db,isin="INE987654321",name="Other Limited")
    with pytest.raises(ValueError,match="IDENTITY_COLLISION"):
        resolve_identity(db,isin="INE123456789",name="Other Limited")

def test_identity_reuses_repository_canonicalizer_and_does_not_strip_inside_words(db):
    assert name_norm("Chipotle Brands Ltd") == "chipotlebrands"
    assert name_norm("M & B Switchgears Limited") == name_norm("M And B Switchgears Ltd. IPO")
    one=resolve_identity(db,isin=None,name="M & B Switchgears Limited")
    assert resolve_identity(db,isin=None,name="M And B Switchgears Ltd. IPO")==one
    db.execute("insert into ipo(isin,name,name_norm) values(?,?,?)",("INE999999999","Chipotle Other",name_norm("Chipotle Other")))
    with pytest.raises(ValueError,match="IDENTITY_COLLISION"):
        resolve_identity(db,isin="INE999999999",name="M & B Switchgears Ltd")

def test_ipomatrix_identity_collision_is_quarantinable_not_ignored():
    sql,reason=map_ipomatrix_identity(isin="INE000000001",name="Other Limited",matrix_id=42,
      by_isin={"INE000000001":1},by_name={name_norm("Other Limited"):2},by_matrix={})
    assert sql==[] and reason=="IDENTITY_COLLISION"
    sql,reason=map_ipomatrix_identity(isin="INE000000001",name="First Ltd",matrix_id=42,
      by_isin={"INE000000001":1},by_name={name_norm("First Ltd"):1},by_matrix={})
    assert reason is None and sql[0].startswith("UPDATE ipo SET ipo_matrix_id=COALESCE")

def test_unit_anomalies_are_not_repaired():
    row={"band_lo_rs":1,"band_hi_rs":120,"issue_price_rs":130,"face_value_rs":10,
         "issue_size_cr":100,"fresh_cr":780000000,"ofs_cr":40}
    assert set(validate_issue(row))=={"BAND_BELOW_FACE_VALUE","ISSUE_COMPONENT_MISMATCH","PRICE_OUTSIDE_BAND"}
    assert row["fresh_cr"]==780000000

@pytest.mark.parametrize("row,code",[
 ({"band_lo_rs":"110","band_hi_rs":"100"},"BAND_REVERSED"),
 ({"band_lo_rs":"100","band_hi_rs":"120","issue_price_rs":"99"},"PRICE_OUTSIDE_BAND"),
 ({"band_lo_rs":"100","band_hi_rs":"120","issue_price_rs":"121"},"PRICE_OUTSIDE_BAND"),
 ({"band_lo_rs":"1","band_hi_rs":"10","face_value_rs":"10","is_book_built":True},"BAND_BELOW_FACE_VALUE"),
])
def test_molbio_class_values_quarantine_before_insert(row,code):
    assert code in validate_issue(row)

def test_database_rejects_molbio_and_price_outside_band(db):
    db.execute("insert into ipo(id,name,name_norm) values(1,'One','one')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into ipo_issue(ipo_id,band_lo_rs,band_hi_rs,face_value_rs) values(1,'1','10','10')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into ipo_issue(ipo_id,band_lo_rs,band_hi_rs,issue_price_rs) values(1,'100','120','99')")

def test_security_kind_lifecycle_symbol_and_locks_are_structural(db):
    db.execute("insert into ipo(id,name,name_norm,status) values(1,'One','one','ALLOTTED')")
    assert db.execute("select security_kind,status from ipo").fetchone()==("EQUITY","ALLOTTED")
    with pytest.raises(sqlite3.IntegrityError):db.execute("insert into ipo(id,name,name_norm,security_kind) values(2,'Bad','bad','BOND')")
    db.execute("insert into ipo(id,name,name_norm,nse_symbol) values(3,'Two','two','SAME')")
    with pytest.raises(sqlite3.IntegrityError):db.execute("insert into ipo(id,name,name_norm,nse_symbol) values(4,'Three','three','SAME')")
    db.execute("insert into ipo_issue(ipo_id,listing_date) values(1,'2026-01-01')")
    assert db.execute("select lock30_date,lock90_date from ipo_issue").fetchone()==("2026-01-31","2026-04-01")
    assert canonical_spine_eligible(True,"ALLOTTED","EQUITY")
    assert not canonical_spine_eligible(True,"LISTED","REIT")
    assert not canonical_spine_eligible(True,"LISTED","INVIT")

def test_neon_security_kind_uses_provenance_not_a_nonexistent_ipo_column():
    assert "i.security_kind" not in NEON_QUERIES["ipo"]
    assert "sf.field='security_kind'" in NEON_QUERIES["ipo"]
    assert derive_security_kind("REIT")==("REIT",None)
    assert derive_security_kind(None)==("EQUITY",None)
    assert derive_security_kind("EQUITY,REIT")==("EQUITY","AMBIGUOUS_SECURITY_KIND")
    assert normalize_legacy_status("ARCHIVED","2020-01-01")==("LISTED","ARCHIVED")
    assert normalize_legacy_status("ARCHIVED",None)==("ANNOUNCED","ARCHIVED")

def test_migration_derived_facts_have_no_document_fk(db):
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("INSERT INTO ipo(id,name,name_norm) VALUES(1,'One','one')")
    statements=(
      derived_source_fact_sql(1,"status","ARCHIVED","LISTED","neon_legacy_normalization","2020-01-01"),
      derived_source_fact_sql(1,"security_kind",None,"EQUITY","migration_default","2020-01-01"),
    )
    for statement in statements:db.executescript(statement)
    rows=db.execute("SELECT target_field,document_sha256 FROM source_facts ORDER BY target_field").fetchall()
    assert rows==[("security_kind",None),("status",None)]

def test_core_scope_never_selects_market_datasets():
    core=datasets_for_scope("core");market=datasets_for_scope("market")
    assert core==("ipo","ipo_issue","financial_statements","subscription_snapshots","documents","source_facts")
    assert market==("market_daily","market_15m","listing_observations")
    assert set(core).isdisjoint(market)
    assert "raw_objects" not in d1m.CORE_SCOPE_TABLES
    assert d1m.ARCHIVE_SCOPE_TABLES==("raw_objects",)

def test_core_reconciliation_marks_market_and_derived_tables_deferred(db):
    db.execute("INSERT INTO ipo(id,name,name_norm) VALUES(1,'One','one')")
    source={"scope":"core","source_ipo":1}
    report=reconcile(db,source,scope="core")
    assert report["zero_silent_loss"] is True
    for table in ("raw_objects","market_bars","listing_observations","gmp_observations","valuation_runs","decision_history"):
        assert report[table]=={"status":"DEFERRED"}
        assert table not in report["source_comparisons"]

def test_future_market_reconciliation_does_not_assess_core(db):
    db.execute("INSERT INTO ipo(id,name,name_norm) VALUES(1,'One','one')")
    source={"scope":"market","source_market_daily":0,"source_market_15m":0,"source_listing_observations":0}
    report=reconcile(db,source,scope="market")
    assert report["zero_silent_loss"] is True
    assert report["ipo"]=={"status":"DEFERRED"}

def test_not_due_is_not_missing_failed_or_zero(db):
    assert concept_state("ANNOUNCED","market")=="NOT_DUE"
    assert concept_state("LISTED","market")=="MISSING"
    assert concept_state("LISTED","market",failed=True)=="FAILED"
    assert concept_state("LISTED","market",value=0)=="PRESENT"
    db.execute("insert into ipo(id,name,name_norm,status) values(1,'One','one','ANNOUNCED')")
    assert db.execute("select market_due from ipo_lifecycle_due where ipo_id=1").fetchone()[0]==0

def test_decision_history_is_append_only(db):
    db.execute("insert into ipo(id,name,name_norm) values(1,'One','one')")
    db.execute("insert into decision_history(ipo_id,layer,decided_at,decision,engine_version,inputs_json,run_fingerprint) values(1,'company_quality','2026-01-01','WATCH','v1','{}','fp')")
    with pytest.raises(sqlite3.IntegrityError):db.execute("update decision_history set decision='GOOD'")
    with pytest.raises(sqlite3.IntegrityError):db.execute("delete from decision_history")

def test_inventory_preserves_bytes_and_flags_malformed(tmp_path):
    good=tmp_path/"42.json"; raw=b'{"data":{"id":42,"about_company":"x"}}'; good.write_bytes(raw)
    (tmp_path/"bad.json").write_text("{")
    rows=inventory([tmp_path]); assert len(rows)==2
    g=next(x for x in rows if x["valid"])
    assert g["sha256"]==hashlib.sha256(raw).hexdigest()
    assert sum(not x["valid"] for x in rows)==1

def test_field_survey_reports_paths_counts_samples_types_but_no_units(tmp_path):
    (tmp_path/"one.json").write_text(json.dumps({"data":{"id":1,"money":"10.00","rows":[{"name":"A"},{"name":"B"}]}}))
    (tmp_path/"two.json").write_text(json.dumps({"data":{"id":2,"money":12,"rows":[]}}))
    report=survey(inventory([tmp_path])); paths={x["json_path"]:x for x in report["paths"]}
    assert paths["$.data.id"]["occurrence_count"]==2
    assert paths["$.data.money"]["primitive_types"]=={"integer":1,"string":1}
    assert paths["$.data.rows[].name"]["occurrence_count"]==1
    assert paths["$.data.money"]["null_frequency"]==0
    assert paths["$.data.money"]["representative_values"]
    assert "unit" not in json.dumps(report).lower()

def test_neon_transforms_exact_decimals_and_category_snapshots(db):
    issue={"ipo_id":1,"open_date":None,"close_date":None,"allotment_date":None,"listing_date":None,
      "band_lo":Decimal("95.10"),"band_hi":Decimal("100.20"),"issue_price":Decimal("100.20"),
      "face_value":Decimal("10"),"lot_size":100,"issue_size_cr":Decimal("500.30"),
      "fresh_cr":Decimal("300.10"),"ofs_cr":Decimal("200.20"),"registrar":"R"}
    sql=transform_neon("ipo_issue",issue); assert "'95.1'" in sql[0] and "'500.3'" in sql[0]
    sub={"ipo_id":1,"captured_at":"2026-01-01T00:00:00Z","is_final":True,
      "qib_x":Decimal("2.50"),"nii_x":None,"bnii_x":None,"snii_x":None,"retail_x":Decimal("1.1"),"total_x":Decimal("1.9")}
    statements=transform_neon("subscription_snapshots",sub); assert len(statements)==3
    assert all("INSERT OR IGNORE" not in x and "ON CONFLICT(observation_fingerprint) DO UPDATE" in x for x in statements)

def test_reviewed_ipomatrix_map_populates_normalized_history_without_unit_guessing(db):
    doc="d"*64;payload={"id":42,"issue":{"lo":"95.10","hi":"100","price":"100","face":"10","open":"2026-01-01"},
      "profile":{"about":"Business","sector":"Power"},"ownership":[{"category":"promoter","pre":"80","post":"60"}],
      "objects":[{"order":1,"purpose":"capex","amount":"50","sha":doc,"page":10}],
      "financials":[{"period":"FY25","basis":"consolidated","income":"100000000","pat":"10000000"}],
      "reservations":[{"category":"QIB","shares":1000,"pct":"50"}],
      "subscriptions":[{"at":"2026-01-03T10:00:00Z","category":"QIB","x":"2.5","final":True}],
      "anchor":{"amount":"20","count":2},"allocations":[{"row":1,"name":"Investor Raw","shares":100,"price":"100","amount":"0.01","sha":doc,"page":2}],
      "peers":[{"name":"Peer","pe":"20","pb":"3","sha":doc}],"kpi":{"roe":"12.5"},
      "documents":[{"sha":doc,"type":"RHP","url":"https://example.invalid/rhp.pdf"}]}
    m={"matrix_id":"$.id","ipo_issue":{"open_date":{"path":"$.issue.open"},"band_lo_rs":{"path":"$.issue.lo","unit":"rs"},"band_hi_rs":{"path":"$.issue.hi","unit":"rs"},"issue_price_rs":{"path":"$.issue.price","unit":"rs"},"face_value_rs":{"path":"$.issue.face","unit":"rs"}},
      "company_profile":{"business_description":{"path":"$.profile.about"},"sector":{"path":"$.profile.sector"}},
      "ownership":{"rows":"$.ownership","fields":{"holder_category":{"path":"category"},"pre_pct":{"path":"pre","unit":"pct"},"post_pct":{"path":"post","unit":"pct"}}},
      "objects_of_issue":{"rows":"$.objects","fields":{"row_order":{"path":"order"},"purpose_raw":{"path":"purpose"},"amount_cr":{"path":"amount","unit":"cr"},"document_sha256":{"path":"sha"},"page":{"path":"page"}}},
      "financial_statements":{"rows":"$.financials","fields":{"period":{"path":"period"},"basis":{"path":"basis"},"total_income_cr":{"path":"income","unit":"rs","normalized_unit":"cr"},"pat_cr":{"path":"pat","unit":"rs","normalized_unit":"cr"}}},
      "reservations":{"rows":"$.reservations","fields":{"category":{"path":"category"},"shares_reserved":{"path":"shares"},"reservation_pct":{"path":"pct","unit":"pct"}}},
      "subscription_snapshots":{"rows":"$.subscriptions","fields":{"captured_at":{"path":"at"},"category":{"path":"category"},"subscription_x":{"path":"x","unit":"x"},"is_final":{"path":"final"}}},
      "anchor_summary":{"amount_cr":{"path":"$.anchor.amount","unit":"cr"},"investor_count":{"path":"$.anchor.count"}},
      "anchor_allocations":{"rows":"$.allocations","fields":{"allocation_row":{"path":"row"},"investor_name_raw":{"path":"name"},"shares":{"path":"shares"},"price_rs":{"path":"price","unit":"rs"},"amount_cr":{"path":"amount","unit":"cr"},"document_sha256":{"path":"sha"},"page":{"path":"page"}}},
      "peer_comparisons":{"rows":"$.peers","fields":{"peer_name_raw":{"path":"name"},"pe_x":{"path":"pe","unit":"x"},"pb_x":{"path":"pb","unit":"x"},"document_sha256":{"path":"sha"}}},
      "sourced_kpis":{"ROE":{"path":"$.kpi.roe","unit":"pct"}},
      "documents":{"rows":"$.documents","fields":{"sha256":{"path":"sha"},"doc_type":{"path":"type"},"source_url":{"path":"url"}}}}
    statements,counts=transform_ipomatrix(payload,"a"*64,m)
    for table in ("ipo_issue","company_profile","ownership","objects_of_issue","financial_statements","reservations","subscription_snapshots","anchor_summary","anchor_allocations","peer_comparisons","source_facts","documents"):
        assert any(f"INTO {table}" in sql for sql in statements),table
    assert "'10'" in next(x for x in statements if "INTO financial_statements" in x)  # ₹100m -> ₹10cr
    assert any("INTO source_facts" in sql and "'"+("a"*64)+"'" in sql for sql in statements)
    with pytest.raises(ValueError,match="UNAPPROVED_UNIT"):
        transform_ipomatrix(payload,"a"*64,{**m,"sourced_kpis":{"ROE":{"path":"$.kpi.roe","unit":"mystery","normalized_unit":"pct"}}})

def test_raw_archive_rejects_update_and_delete(db):
    sha="a"*64; db.execute("insert into raw_objects values(?,?,?,?,?,?)",(sha,"ipomatrix","1",None,2,"{}"))
    with pytest.raises(sqlite3.IntegrityError): db.execute("update raw_objects set payload_json='[]'")
    with pytest.raises(sqlite3.IntegrityError): db.execute("delete from raw_objects")

def test_resume_checkpoint_and_reconciliation(db):
    db.executescript(checkpoint_sql("ipo",10,10));db.executescript(checkpoint_sql("ipo",20,20))
    assert db.execute("select last_key,source_rows,written_rows from migration_checkpoints").fetchone()==("COMPLETE",20,20)
    report=reconcile(db);assert report["critical_checks"]=={"orphan_market_bars":0,"quarantined_rows":0,"duplicate_fingerprints":0}
    assert report["local_d1_logical_size_bytes"]>0
