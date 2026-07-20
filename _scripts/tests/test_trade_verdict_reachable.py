#!/usr/bin/env python3
"""The TRADE verdict must be REACHABLE.

2026-07-18 finding: `why_trade` was populated on 2 of 761 verdicts. Both TRADE
strategies gate on `bull is True`:
    STRATEGY 1: gap 0-15% + bull  -> 62% win
    STRATEGY 2: quality promoter + bull -> 71% win

`bull` is read from `regime_bull`, which came from `regime_sql`. That SQL
selected a column named `regime`, but market_regimes actually writes
`active_regime` — so it crashed, and PR #193 "fixed" the crash by hardcoding
`regime_sql = "NULL"`. From then on `bull` was ALWAYS None and TRADE could never
fire. The 2 surviving rows are pre-deprecation legacy.

Fixed by reading the real column, guarded on existence AND freshness.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CV = ROOT / "_scripts" / "compute_verdicts.py"
pytestmark = pytest.mark.unit


def _src():
    return CV.read_text(encoding="utf-8")


def test_regime_sql_is_not_hardcoded_null():
    """REGRESSION: `regime_sql = "NULL"` makes TRADE unreachable forever."""
    s = _src()
    assert not re.search(r'^\s*regime_sql\s*=\s*"NULL"\s*$', s, re.M), \
        "regime_sql is hardcoded NULL — bull can never be True, TRADE is dead"


def test_regime_reads_the_column_that_actually_exists():
    """market_regimes writes `active_regime`; selecting `regime` crashes."""
    s = _src()
    assert "active_regime" in s, "regime query must use active_regime"
    body = s[s.index("regime_sql"):s.index("regime_sql") + 1200]
    assert not re.search(r"SELECT\s+regime\b", body), \
        "selecting bare `regime` — that column does not exist"


def test_stale_regime_reads_as_unknown_not_bull():
    """A stale regime row must yield NULL, never a false bull signal."""
    s = _src()
    assert "evaluation_date >= CURRENT_DATE -" in s, \
        "no freshness bound — a 3-week-old regime could still drive a TRADE"


def test_trade_strategies_still_require_bull():
    """Guard the premise: if TRADE stops depending on bull, this test's
    reasoning changes and should be revisited."""
    s = _src()
    assert "bull is True" in s, "TRADE no longer gates on bull — revisit this test"


def test_regime_is_guarded_on_table_and_column_existing():
    s = _src()
    assert "to_regclass('market_regimes')" in s and "information_schema.columns" in s, \
        "regime read must degrade to NULL if the table/column is absent"
