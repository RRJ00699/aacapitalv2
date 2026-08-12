import json,os,subprocess
import psycopg2

DDL="""
CREATE TABLE ipo(id int primary key,isin text,symbol text,name_display text,listing_date date);
CREATE TABLE ipo_issue(ipo_id int,issue_price numeric,band_lo numeric,band_hi numeric,issue_size_cr numeric,fresh_cr numeric,ofs_cr numeric,lot_size numeric,face_value numeric);
CREATE TABLE valuation(ipo_id int,score numeric,score_band text,engine_version text,computed_at timestamptz,pe numeric,pb numeric,peer_median_pe numeric,fair_value_lo numeric,fair_value_hi numeric,inputs_used jsonb,missing_inputs text[],roce numeric);
CREATE TABLE financial_statements(ipo_id int,period text,basis text,pat numeric,total_debt numeric,ebitda numeric,net_worth numeric);
CREATE TABLE source_facts(ipo_id int,field text,value text,fetched_at timestamptz);
CREATE TABLE rhp_findings(ipo_id int,findings jsonb,model text,prompt_version text,confidence numeric,analyzed_at timestamptz,red_flag_count int,junk_signals jsonb);
CREATE TABLE decisions(ipo_id int,fundamental_verdict text,reasons jsonb,evidence_refs jsonb,decided_at timestamptz);
CREATE TABLE listing_outcomes(ipo_id int,listing_open numeric,gap_pct numeric,d1_close numeric,best_close numeric,worst_close numeric,pool text,hold_positive_vs_open boolean,winner_35 boolean,ceiling_20 boolean,computed_at timestamptz,dataset_version text);
CREATE TABLE documents(id int,doc_type text,url text,sha256 text,page_count int);
CREATE TABLE insights(id int,ipo_id int,excerpt text,page_number int,doc_id int,category text,direction text,source_type text,is_current boolean);
"""

def test_seeded_real_details_sql_builds_available_profile_with_latest_fact_and_restated_basis(pg_uri):
    conn=psycopg2.connect(pg_uri);cur=conn.cursor();cur.execute("DROP SCHEMA public CASCADE;CREATE SCHEMA public;"+DDL)
    cur.execute("INSERT INTO ipo VALUES(1,'INE000000001','FIX','Fixture',NULL);INSERT INTO ipo_issue VALUES(1,100,90,100,500,500,0,10,10)")
    cur.execute("INSERT INTO valuation VALUES(1,2,'FAVORABLE','v2-score-2',now(),20,2,15,110,130,%s,'{}',18)",(json.dumps({'rhp_eps':5,'rhp_eps_field':'eps_post','pe_source':'rhp_computed:price/eps_post'}),))
    cur.execute("INSERT INTO financial_statements VALUES(1,'31-Mar-26','Standalone',20,120,40,100),(1,'31-Mar-25','Restated Consolidated',20,100,50,110)")
    cur.execute("INSERT INTO source_facts VALUES(1,'cash_cr','100','2026-01-01'),(1,'cash_cr','80','2026-02-01'),(1,'debt_repayment_cr','50','2026-02-01'),(1,'interest_expense_cr','10','2026-02-01')")
    conn.commit();conn.close()
    env={**os.environ,'DATABASE_URL':pg_uri};result=subprocess.run(['npx','tsx','_scripts/tests/helpers/intelligence_sql_probe.ts'],env=env,text=True,capture_output=True)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    out=json.loads(result.stdout);assert out=={'status':'AVAILABLE','post_issue_shares_cr':4,'cash_cr':80,'financial_basis':'Restated Consolidated'}
