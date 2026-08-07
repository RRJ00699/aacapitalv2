from pathlib import Path

from pipeline.intelligence import AI_FIELDS, SCHEMA_PATH, build_profile, canonical_anchor_facts, profile_schema, validate_profile

BASE=dict(ipo_id=1,isin="INE000000001",identity={"name":"Fixture"},company={"name":"Fixture"},issue={"price":100},
          documents=[],financials={"pat":20},kpis={},valuation={"status":"AVAILABLE"},generated_at="2026-08-07T00:00:00Z")

def test_no_parallel_pdf_or_regex_financial_extraction():
    source=Path(__file__).with_name("intelligence.py").read_text()
    assert "fitz" not in source and "extract_rhp" not in source and "extract_sbi" not in source
    assert "EPS" not in source and "MONEY" not in source

def test_anchor_facts_only_from_verified_anchor_documents():
    documents=[{"id":1,"doc_type":"rhp","verified":True},{"id":2,"doc_type":"anchor","verified":True},{"id":3,"doc_type":"anchor","verified":False}]
    facts=[{"document_id":1,"investor":"wrong"},{"document_id":2,"investor":"right"},{"document_id":3,"investor":"unverified"}]
    assert canonical_anchor_facts(documents,facts)==[{"document_id":2,"investor":"right"}]

def test_ai_cannot_overwrite_verified_fields():
    try: build_profile(**BASE,ai={"debt":0})
    except ValueError as error: assert "deterministic fields" in str(error)
    else: raise AssertionError("AI fact overwrite accepted")

def test_shared_schema_is_the_only_contract_and_validates_python_output():
    assert SCHEMA_PATH.name == "ipo-profile.schema.json"
    profile=build_profile(**BASE); validate_profile(profile)
    assert profile["schema_version"]==profile_schema()["properties"]["schema_version"]["const"]

def test_profile_generation_is_idempotent_with_fixed_timestamp():
    assert build_profile(**BASE)==build_profile(**BASE)

def test_ai_coverage_is_bounded_to_five_qualitative_fields():
    assert AI_FIELDS == {"qualitative_risk","governance","rhp_verdict","sbi_verdict","business_quality"}

def test_score_engine_persists_eps_field_provenance():
    source=(Path(__file__).with_name("score_engine.py")).read_text()
    assert 'used["rhp_eps_field"] = eps_field' in source
    assert "basis ILIKE '%consolidat%'" in source
