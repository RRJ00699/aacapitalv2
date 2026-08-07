"""Contract for intentional tabular data committed to the repository."""

import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
TRACKED_DATA_SUFFIXES = {".csv", ".tsv", ".xlsx"}

# These are reviewed, intentional repository inputs and inventory artifacts.
ALLOWED_TRACKED_DATA_FILES = {
    "_archive/golden_symbol_review.csv",
    "_archive/missing_financials.csv",
    "_scripts/ipo_data_contract.csv",
    "docs/repository-inventory.tsv",
}

# Fixture data is reviewable test/UAT input. Research notes remain live until
# the SBI/cron lane is migrated; the manifest records that removal blocker.
ALLOWED_TRACKED_DATA_TREES = (
    "tests/fixtures/",
    "uat/fixtures/",
    "data/research_notes/",
)


def test_tracked_tabular_data_is_explicitly_allowed():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    tracked = (path.decode("utf-8") for path in result.stdout.split(b"\0") if path)
    tabular = {
        path
        for path in tracked
        if pathlib.PurePosixPath(path).suffix.lower() in TRACKED_DATA_SUFFIXES
    }
    unexpected = sorted(
        path
        for path in tabular
        if path not in ALLOWED_TRACKED_DATA_FILES
        and not path.startswith(ALLOWED_TRACKED_DATA_TREES)
    )
    assert not unexpected, "unapproved tracked tabular data:\n" + "\n".join(unexpected)
