from unittest.mock import patch
import pipeline.nse_fetch as nse
from pipeline.fill_v2 import upsert_ipo_issue,validate_issue_economics
from pipeline.kite_fetch import derive_outcome


def payload(price):
 return {"issueInfo":{"dataList":[{"title":"Face Value","value":"Rs. 10 per Equity Share"},{"title":"Price Range","value":price},{"title":"Bid Lot","value":"18 Equity Shares"},{"title":"Issue Size","value":"Fresh Issue Rs. 2,000 million. Offer for Sale Rs. 15 million."}]}}

def test_verified_scaled_price_range_keeps_explicit_thousand_unit():
 rec,extras,notes=nse.parse_issue_info(payload("Rs. 0.77 Thousand to Rs. 0.81 Thousand per Equity Share"))
 assert (rec["band_lo"],rec["band_hi"])==(770,810)
 assert rec["face_value"]==10 and rec["lot_size"]==18 and rec["issue_size_cr"]==201.5
 assert extras["official_price_range_raw"].startswith("Rs. 0.77 Thousand") and not notes

def test_ordinary_rupee_range_is_unchanged_and_unknown_unit_fails_closed():
 rec,_,notes=nse.parse_issue_info(payload("Rs. 770 to Rs. 810 per Equity Share"))
 assert (rec["band_lo"],rec["band_hi"])==(770,810) and not notes
 rec,_,notes=nse.parse_issue_info(payload("Rs. 0.77 Mystery to Rs. 0.81 Mystery per Equity Share"))
 assert "band_lo" not in rec and notes==["price_range:unknown_unit:mystery"]

def test_central_validation_inside_outside_order_and_face_scale():
 assert validate_issue_economics({"face_value":10,"band_lo":770,"band_hi":810,"issue_price":800}) is None
 assert "above_band" in validate_issue_economics({"band_lo":770,"band_hi":810,"issue_price":900})
 assert "invalid_ordering" in validate_issue_economics({"band_lo":810,"band_hi":770})
 assert "below_face" in validate_issue_economics({"face_value":10,"band_lo":.77,"band_hi":.81},.1)

class WriterCursor:
 def __init__(self): self.calls=[]
 def execute(self,sql,params=None): self.calls.append((sql,params))
 def fetchone(self): return None
class WriterConn:
 def __init__(self): self.cur=WriterCursor(); self.rollbacks=0; self.commits=0
 def cursor(self): return self.cur
 def rollback(self): self.rollbacks+=1
 def commit(self): self.commits+=1

def test_bad_input_writes_no_issue_or_source_fact():
 conn=WriterConn()
 with patch("pipeline.fill_v2._log_fact") as fact:
  result=upsert_ipo_issue(conn,1100,{"face_value":10,"band_lo":.77,"band_hi":.81},source="nse")
 assert result.startswith("source_invalid_unit:")
 assert conn.rollbacks==1 and conn.commits==0 and len(conn.cur.calls)==2
 fact.assert_not_called()

class OutcomeCursor:
 def __init__(self): self.n=0
 def execute(self,*_): self.n+=1
 def fetchall(self): return [("2026-08-19",770,820,760,800)]
 def fetchone(self): return (None,770,810)
class OutcomeConn:
 def cursor(self): return OutcomeCursor()

def test_null_issue_price_never_uses_band_high_for_outcomes():
 rec,note=derive_outcome(OutcomeConn(),1100)
 assert rec["listing_open"]==770 and rec["d1_close"]==800
 assert {"gap_pct","pool","winner_35"}.isdisjoint(rec)
 assert "issue price" in note

from pipeline.audit_price_band_units import apply_verified
class RepairCursor:
 def __init__(self,rowcount): self.rowcount=rowcount; self.calls=[]
 def execute(self,sql,params): self.calls.append((sql,params))
class RepairConn:
 def __init__(self,rowcount): self.cur=RepairCursor(rowcount); self.commits=0
 def cursor(self): return self.cur
 def commit(self): self.commits+=1

def test_approved_repair_is_exact_identity_provenance_recorded_and_idempotent():
 item={"ipo_id":1100,"isin":None,"symbol":"MOLBIO","face_value":10,"band_lo":.77,"band_hi":.81,"issue_price":None}
 evidence={"status":"verified","raw":"Rs. 0.77 Thousand to Rs. 0.81 Thousand per Equity Share","proposed":{"band_lo":770,"band_hi":810}}
 with patch("fill_ipo._log_fact") as fact:
  conn=RepairConn(1); assert apply_verified(conn,item,evidence) is True
 assert conn.cur.calls[0][1][2:4]==(1100,"MOLBIO") and fact.call_count==3
 with patch("fill_ipo._log_fact") as fact:
  conn=RepairConn(0); assert apply_verified(conn,item,evidence) is False
 fact.assert_not_called()

def test_unknown_price_unit_creates_no_issue_or_source_fact_mutation():
 conn=WriterConn()
 with patch("fill_v2.upsert_ipo_issue") as writer, patch("fill_v2.log_source_fact") as fact, patch("fill_ipo.upsert_ipo") as spine:
  report=nse.apply_to_db(conn,1100,payload("Rs. 0.77 Mystery to Rs. 0.81 Mystery"),apply_subscription=False)
 assert report["issue_fields"]==[] and "source_invalid_unit" in report["notes"]
 writer.assert_not_called(); fact.assert_not_called(); spine.assert_not_called()
