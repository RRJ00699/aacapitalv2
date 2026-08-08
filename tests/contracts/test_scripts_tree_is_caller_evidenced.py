"""Ratchets for the mechanically evidenced production scripts tree."""
import csv
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import scripts_caller_graph as graph  # noqa: E402


def _inventory():
    with (ROOT / "docs/repository-inventory.tsv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_every_production_script_is_caller_evidenced_keep():
    result = graph.analyze(ROOT).production()
    assert result.files == result.keep
    assert len(result.keep) == 54
    classifications = {row["path"]: row["classification"] for row in _inventory()}
    assert {path: classifications.get(path) for path in result.files} == {
        path: "KEEP" for path in result.files
    }


def test_inventory_records_every_quarantine_move():
    moved = [row for row in _inventory() if row.get("move_destination") and "/tests/" not in row["old_path"]]
    assert len(moved) == 120
    assert sum(row["move_destination"] == "compatibility/scripts/" for row in moved) == 86
    assert sum(row["move_destination"] == "_archive/scripts/" for row in moved) == 34
    for row in moved:
        assert row["old_path"].startswith("_scripts/")
        assert row["classification"] == row["caller_evidence"] == "UNREACHABLE"
        assert (ROOT / row["path"]).is_file()
        assert not (ROOT / row["old_path"]).exists()


def test_production_does_not_import_or_execute_quarantine_code():
    result = graph.analyze(ROOT).production()
    zones = [ROOT / name for name in ("app", "components", "lib", "pipeline", "workers")]
    paths = [path for zone in zones if zone.exists() for path in zone.rglob("*") if path.is_file()]
    paths += [ROOT / path for path in result.keep]
    hits = []
    for path in paths:
        source = path.read_text(encoding="utf-8", errors="ignore")
        executable_reference = re.compile(
            r"^(?!\s*#).*\b(?:import|from|require|subprocess|os\.system|exec|spawn)\b"
            r"[^\n]*(?:compatibility/|_archive/)", re.MULTILINE,
        )
        if executable_reference.search(source):
            hits.append(path.relative_to(ROOT).as_posix())
    assert not hits
