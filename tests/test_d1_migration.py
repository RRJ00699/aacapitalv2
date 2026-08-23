import hashlib, json, sqlite3
from pathlib import Path
import pytest

from tools.d1_migration import fingerprint, inventory, resolve_identity, validate_issue
from tools.d1_reconcile import reconcile

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

def test_identity_precedence_and_collision(db):
    one=resolve_identity(db,isin="INE123456789",name="Example Limited")
    assert resolve_identity(db,isin="INE123456789",name="Example Ltd")==one
    resolve_identity(db,isin="INE987654321",name="Other Limited")
    with pytest.raises(ValueError,match="IDENTITY_COLLISION"):
        resolve_identity(db,isin="INE123456789",name="Other Limited")

def test_unit_anomalies_are_not_repaired():
    row={"band_lo_rs":1,"band_hi_rs":120,"issue_price_rs":130,"face_value_rs":10,
         "issue_size_cr":100,"fresh_cr":780000000,"ofs_cr":40}
    assert set(validate_issue(row))=={"BAND_FACE_MAGNITUDE","ISSUE_COMPONENT_MISMATCH","PRICE_OUTSIDE_BAND"}
    assert row["fresh_cr"]==780000000

def test_inventory_preserves_bytes_and_flags_malformed(tmp_path):
    good=tmp_path/"42.json"; raw=b'{"data":{"id":42,"about_company":"x"}}'; good.write_bytes(raw)
    (tmp_path/"bad.json").write_text("{")
    rows=inventory([tmp_path]); assert len(rows)==2
    g=next(x for x in rows if x["valid"])
    assert g["sha256"]==hashlib.sha256(raw).hexdigest() and g["matrix_id"]==42
    assert sum(not x["valid"] for x in rows)==1

def test_raw_archive_rejects_update_and_delete(db):
    sha="a"*64; db.execute("insert into raw_objects values(?,?,?,?,?,?)",(sha,"ipomatrix","1",None,2,"{}"))
    with pytest.raises(sqlite3.IntegrityError): db.execute("update raw_objects set payload_json='[]'")
    with pytest.raises(sqlite3.IntegrityError): db.execute("delete from raw_objects")

def test_resume_checkpoint_and_reconciliation(db):
    db.execute("insert into migration_checkpoints(dataset,last_key,source_rows,written_rows) values('ipo','10',10,10)")
    db.execute("update migration_checkpoints set last_key='20',source_rows=20,written_rows=20 where dataset='ipo'")
    assert db.execute("select last_key from migration_checkpoints").fetchone()[0]=="20"
    assert reconcile(db)["critical_checks"]=={"orphan_market_bars":0,"quarantined_rows":0}
