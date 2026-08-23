import hashlib, json, sqlite3
from decimal import Decimal
from pathlib import Path
import pytest

from tools.d1_migration import (decimal_text, fingerprint, inventory, name_norm,
    checkpoint_sql, map_ipomatrix_identity, resolve_identity, survey, transform_neon, validate_issue)
from tools.d1_reconcile import reconcile
from tools.d1_contract import canonical_spine_eligible, concept_state

DDL=Path("d1/migrations/0001_functional_model.sql").read_text()

@pytest.fixture
def db():
    conn=sqlite3.connect(":memory:"); conn.executescript(DDL); yield conn; conn.close()

def test_schema_is_idempotent_for_content_writes(db):
    ipo=resolve_identity(db,isin="INE123456789",name="Example Limited")
    fp=fingerprint(ipo,"1d","2026-01-01",10,11,9,10.5,100)
    sql="INSERT OR IGNORE INTO market_bars VALUES(?,?,?,?,?,?,?,?,?,?)"
    args=(ipo,"1d","2026-01-01",10,11,9,10.5,100,"kite",fp)
    db.execute(sql,args); db.execute(sql,args)
    assert db.execute("select count(*) from market_bars").fetchone()[0]==1

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
    assert all("INSERT OR IGNORE" in x for x in statements)

def test_raw_archive_rejects_update_and_delete(db):
    sha="a"*64; db.execute("insert into raw_objects values(?,?,?,?,?,?)",(sha,"ipomatrix","1",None,2,"{}"))
    with pytest.raises(sqlite3.IntegrityError): db.execute("update raw_objects set payload_json='[]'")
    with pytest.raises(sqlite3.IntegrityError): db.execute("delete from raw_objects")

def test_resume_checkpoint_and_reconciliation(db):
    db.executescript(checkpoint_sql("ipo",10,10));db.executescript(checkpoint_sql("ipo",20,20))
    assert db.execute("select last_key,source_rows,written_rows from migration_checkpoints").fetchone()==("COMPLETE",20,20)
    assert reconcile(db)["critical_checks"]=={"orphan_market_bars":0,"quarantined_rows":0,"duplicate_fingerprints":0}
