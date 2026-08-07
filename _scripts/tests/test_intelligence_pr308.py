from pathlib import Path

ROOT=Path(__file__).parents[2]
def read(path): return (ROOT/path).read_text()

def test_complete_details_renders_valuation_fields_without_raw_json():
    src=read("components/ipo/CompleteDetails.tsx")
    for label in ["Reported PAT","Pro-forma PAT","Reported EPS","Pro-forma EPS","Reported P/E","Pro-forma P/E","Net debt","Fair value","Margin of safety","Status / evidence class"]: assert label in src
    assert "JSON.stringify(p.valuation" not in src

def test_command_center_card_renders_compact_intelligence_summary():
    src=read("components/ipo/IpoCard.tsx")
    assert 'data-testid="command-intelligence-summary"' in src
    for label in ["Reported","Pro-forma","Transformations","Fair value / MoS","Verdict / red flags"]: assert label in src

def test_ci_runs_bounded_pipeline_tests():
    assert "python -m pytest pipeline -q" in read(".github/workflows/ci.yml")

def test_details_sql_does_not_hide_null_isin():
    assert "isin IS NOT NULL" not in read("lib/v2/ipo-details.ts")

def test_command_and_details_share_canonical_input_builder_and_do_not_infer_transformations():
    command=read("lib/v2/ipo-command.ts");details=read("lib/v2/ipo-details.ts")
    assert "buildCanonicalProFormaInputs" in command and "buildCanonicalProFormaInputs" in details
    assert 'Number(c.debt_repayment_cr)>0' not in command
    assert "known_transformations:[]" in command
