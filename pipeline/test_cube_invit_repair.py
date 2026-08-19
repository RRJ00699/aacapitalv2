from unittest.mock import patch
import pytest
from pipeline.repair_cube_invit_classification import IPO_ID,ISIN,PROVENANCE,REPAIRS,IdentityMismatch,repair,repair_one

class Cursor:
 def __init__(self,row): self.row=row; self.rowcount=0; self.sql=[]
 def execute(self,sql,params):
  self.sql.append((" ".join(sql.split()),params))
  if sql.lstrip().startswith("UPDATE"): self.rowcount=1
 def fetchone(self): return self.row
class Conn:
 def __init__(self,row): self.cur=Cursor(row); self.commits=0
 def cursor(self): return self.cur
 def commit(self): self.commits+=1

def test_exact_identity_owner_repair_excludes_cube_and_records_provenance():
 conn=Conn((IPO_ID,ISIN,"CUBEINVIT",True,False))
 with patch("fill_v2.log_source_fact") as fact: result=repair(conn,write=True)
 assert result["changed"] and conn.commits==1
 assert conn.cur.sql[1][1]==(IPO_ID,ISIN)
 fact.assert_called_once_with(conn,IPO_ID,"canonical_classification","INVIT/excluded",PROVENANCE,commit=False)

def test_repair_rerun_is_noop():
 conn=Conn((IPO_ID,ISIN,"CUBEINVIT",False,False))
 assert repair(conn,write=True)["status"]=="already_repaired" and conn.commits==0

def test_bagmane_reit_uses_exact_id_and_symbol_and_is_idempotent():
 spec=REPAIRS[1]; conn=Conn((746,None,"BAGMANE",True,True))
 with patch("fill_v2.log_source_fact") as fact: result=repair_one(conn,spec,write=True)
 assert result["changed"] and conn.cur.sql[1][1]==(746,"BAGMANE")
 fact.assert_called_once_with(conn,746,"canonical_classification","REIT/excluded",spec["provenance"],commit=False)

def test_absent_or_mismatched_identity_fails_closed():
 with pytest.raises(IdentityMismatch): repair_one(Conn(None),REPAIRS[1],write=False)
 with pytest.raises(IdentityMismatch): repair_one(Conn((746,None,"OTHER",True,True)),REPAIRS[1],write=True)
