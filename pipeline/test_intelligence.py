import json
from pipeline.intelligence import AI_FIELDS, Page, build_profile, extract_rhp

def test_deterministic_rhp_extraction_and_provenance():
    out=extract_rhp([Page(12,"Name of our Company: Fixture Limited\nTotal debt: 500\nEPS: 12.50\nObjects of the Offer\nRepayment of borrowings")],7)
    assert out["company"]["classification"] == "VERIFIED_FACT"
    assert out["company"]["provenance"]["page"] == 12
    assert out["debt"]["value"] == "500"

def test_ai_cannot_overwrite_verified_fields():
    try: build_profile(ipo_id=1,isin="INE000000001",identity={},documents=[],ai={"debt":0})
    except ValueError as error: assert "deterministic fields" in str(error)
    else: raise AssertionError("AI fact overwrite accepted")

def test_profile_generation_is_idempotent_with_fixed_timestamp():
    kwargs=dict(ipo_id=1,isin="INE000000001",identity={"historical":True},documents=[{"id":7,"sha256":"abc"}],generated_at="2026-08-07T00:00:00Z")
    assert build_profile(**kwargs) == build_profile(**kwargs)
    assert build_profile(**kwargs)["schema_version"] == "ipo-profile:v1"

def test_ai_coverage_is_bounded_to_five_qualitative_fields():
    assert AI_FIELDS == {"qualitative_risk","governance","rhp_verdict","sbi_verdict","business_quality"}
