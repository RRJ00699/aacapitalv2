#!/usr/bin/env python3
"""Durable data must never live as ALTERed columns on a REBUILT table.

INCIDENT 2026-07-19/20: `backfill_listing_minutes.py` added first_print_price,
vol_first_5m etc. to ipo_consolidated via ALTER. But
`build_ipo_consolidated_v2.py` REBUILDS that table from scratch on every
pipeline run, so all 456 rows of Kite listing tape were wiped three times in two
days — repeat Kite API calls and repeat Neon compute for zero net data.

`ipo_bid_details` survived every rebuild because it is its OWN table. Same
pattern is now used for `ipo_listing_tape`.

RULE: if a table is rebuilt by a build_* script, nothing else may depend on
columns it ALTERs into that table.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_scripts"
COMPATIBILITY_BUILDERS = ROOT / "compatibility" / "consolidated"
pytestmark = pytest.mark.unit

# tables that a build_* script drops/recreates -> anything ALTERed in is transient
REBUILT = ["ipo_consolidated"]


def _rebuilders():
    out = []
    for p in COMPATIBILITY_BUILDERS.rglob("build_*.py"):
        if "_archive" in p.parts:
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        for t in REBUILT:
            if re.search(rf"(DROP TABLE|CREATE TABLE)\s+(IF (EXISTS|NOT EXISTS)\s+)?{t}\b", src, re.I):
                out.append((p.name, t))
    return out


def test_rebuilt_tables_are_actually_rebuilt():
    """Premise check: if nothing rebuilds ipo_consolidated any more, this whole
    test can be retired."""
    assert _rebuilders(), "no build_* script rebuilds ipo_consolidated — revisit"


def test_listing_tape_has_its_own_table():
    s = (SCRIPTS / "backfill_listing_minutes.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS ipo_listing_tape" in s, \
        "listing tape must own its table, not ALTER columns onto a rebuilt one"
    assert "UPDATE ipo_consolidated SET" not in s, \
        "still writing into the rebuilt table — data will be wiped every run"


def test_no_script_alters_durable_columns_onto_a_rebuilt_table():
    offenders = []
    for p in SCRIPTS.rglob("*.py"):
        if "_archive" in p.parts or "tests" in p.parts or p.name.startswith("build_"):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        for t in REBUILT:
            for m in re.finditer(rf"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS (\w+)", src):
                offenders.append(f"{p.name} -> {t}.{m.group(1)}")
    assert not offenders, (
        "these columns are ALTERed onto a table that gets REBUILT — they will be "
        f"silently wiped on the next pipeline run: {offenders}")
