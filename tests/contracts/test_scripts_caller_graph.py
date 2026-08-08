"""Regression coverage for the authoritative _scripts caller resolver."""
from pathlib import Path

from tools.scripts_caller_graph import analyze

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scripts_caller_graph"


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
