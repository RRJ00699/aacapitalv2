"""Regression coverage for the authoritative _scripts caller resolver."""
from pathlib import Path
import re

from tools.scripts_caller_graph import analyze

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scripts_caller_graph"
ROOT = Path(__file__).resolve().parents[2]


def test_relative_step_subprocess_explicit_path_and_transitive_wrapper_are_reachable():
    result = analyze(FIXTURE)
    assert result.keep == {
        "_scripts/root.py", "_scripts/foo.py", "_scripts/bar.py",
        "_scripts/wrapper.py", "_scripts/final.py",
    }


def test_relative_step_argument_has_a_regression_edge():
    result = analyze(FIXTURE)
    edges = {(edge.caller, edge.callee, edge.kind) for edge in result.edges}
    assert ("_scripts/root.py", "_scripts/foo.py", "relative script argument") in edges
    assert ("_scripts/foo.py", "_scripts/bar.py", "relative script argument") in edges


def test_documented_production_totals_match_real_repository_analysis():
    production = analyze(ROOT).production()
    document = (ROOT / "docs/decisions/SCRIPTS_CALLER_GRAPH.md").read_text(encoding="utf-8")

    def documented(label: str) -> int:
        match = re.search(rf"^\| {re.escape(label)} \| (\d+) \|$", document, re.MULTILINE)
        assert match, f"missing documented production total: {label}"
        return int(match.group(1))

    assert documented("TOTAL") == len(production.files)
    assert documented("KEEP") == len(production.keep)
    assert documented("UNREACHABLE") == len(production.files - production.keep)
