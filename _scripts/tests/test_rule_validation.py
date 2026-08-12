"""Ownership contract for the quarantined rule-validation producer."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_rule_validation_producer_remains_quarantined():
    assert not (ROOT / "_scripts" / "rule_validation.py").exists()
    assert (ROOT / "compatibility" / "scripts" / "rule_validation.py").is_file()


def test_canonical_cron_does_not_execute_quarantined_producer():
    source = (ROOT / "pipeline" / "cron.py").read_text(encoding="utf-8")
    assert "compatibility/scripts/rule_validation.py" not in source
    assert "rule_validation_results production producer is quarantined" in source
