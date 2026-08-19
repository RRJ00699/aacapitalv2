"""Ownership contract for the rule-validation producers.

The V1 producer stays quarantined and cron owns a V2 replacement. Both halves matter:
promoting the V1 file would reintroduce ipo_gold and its `company_name !~* REIT|InvIT`
name gate, and leaving cron with a permanent skip would keep rule_validation_results
unowned.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_v1_rule_validation_producer_remains_quarantined():
    assert not (ROOT / "_scripts" / "rule_validation.py").exists()
    assert (ROOT / "compatibility" / "scripts" / "rule_validation.py").is_file()


def test_canonical_cron_runs_the_v2_producer_and_never_the_quarantined_one():
    source = (ROOT / "pipeline" / "cron.py").read_text(encoding="utf-8")
    assert "compatibility/scripts/rule_validation.py" not in source
    assert "rule_validation_results production producer is quarantined" not in source
    assert 'RULE_VALIDATION_SCRIPT = "pipeline/rule_validation.py"' in source
    assert (ROOT / "pipeline" / "rule_validation.py").is_file()


def test_the_v2_producer_writes_only_behind_the_owner_gate():
    source = (ROOT / "pipeline" / "cron.py").read_text(encoding="utf-8")
    step = source[source.index('run("Database-backed Listing rules layers"'):]
    step = step[:step.index("snapshot_ready")]
    assert 'RULE_VALIDATION_OWNER_APPROVED") != "1"' in step
    assert step.count('["--dry-run"]') == 2 and step.count('["--write"]') == 1
