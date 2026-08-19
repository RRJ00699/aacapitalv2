from unittest.mock import patch
from pipeline.repair_cube_invit_classification import IPO_ID, ISIN, PROVENANCE, repair

class Cursor:
    def __init__(self, row): self.row=row; self.rowcount=0; self.sql=[]
    def execute(self, sql, params):
        self.sql.append((" ".join(sql.split()), params))
        if sql.lstrip().startswith("UPDATE"): self.rowcount=1
    def fetchone(self): return self.row
class Conn:
    def __init__(self,row): self.cur=Cursor(row); self.commits=0
    def cursor(self): return self.cur
    def commit(self): self.commits += 1

def test_exact_identity_owner_repair_excludes_cube_and_records_provenance():
    conn=Conn((IPO_ID,ISIN,True,False))
    with patch("fill_v2.log_source_fact") as fact:
        result=repair(conn,write=True)
    assert result["changed"] and conn.commits == 1
    update=conn.cur.sql[1]
    assert "id=%s AND isin=%s" in update[0] and update[1] == (IPO_ID,ISIN)
    assert "is_mainboard=FALSE" in update[0] and "in_backtest_universe=FALSE" in update[0]
    fact.assert_called_once_with(conn,IPO_ID,"canonical_classification","INVIT/excluded",PROVENANCE,commit=False)

def test_repair_rerun_is_noop():
    conn=Conn((IPO_ID,ISIN,False,False))
    assert repair(conn,write=True)["status"] == "already_repaired"
    assert len(conn.cur.sql) == 1 and conn.commits == 0

def test_discovery_and_every_canonical_selector_rely_on_repaired_mainboard_flag():
    from pathlib import Path
    assert "REIT|INVIT" in Path("pipeline/nse_fetch.py").read_text()
    assert "i.is_mainboard=true" in Path("pipeline/build/journey_universe.ts").read_text()
    assert "i.is_mainboard=TRUE" in Path("pipeline/nse_fetch.py").read_text()
    assert "CANONICAL_UNIVERSE_SQL" in Path("pipeline/kite_fetch.py").read_text()
    assert "CANONICAL_UNIVERSE_SQL" in Path("pipeline/kite_fetch_15m.py").read_text()
    assert all("ipo_issue.issue_type" not in candidate.read_text() for candidate in Path("pipeline").glob("*.py") if not candidate.name.startswith("test_"))
