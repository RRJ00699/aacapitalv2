import pytest

from pipeline import company_identity
from pipeline import rhp_link
from pipeline import sbi_ingest


class Cursor:
    def __init__(self, rows):
        self.rows = rows
    def execute(self, sql, params):
        self.sql = sql
    def fetchone(self):
        return None
    def fetchall(self):
        return self.rows


def test_preloaded_identity_set_avoids_all_resolution_queries():
    rows = ((1, "ISIN1", "Yatra Online Limited", "yatra online limited"),)
    cursor = Cursor(rows)
    loaded = company_identity.load_company_identity_set(cursor)
    assert cursor.sql == company_identity.IDENTITY_SET_SQL
    cursor.sql = None
    result = company_identity.resolve_company_identity(
        cursor, name_norm="yatra online ltd", company="Yatra Online Ltd",
        identity_rows=loaded)
    assert result.row == rows[0][:3] and result.method == "CANONICAL_NAME"
    assert cursor.sql is None, "preloaded resolution performed another SQL query"


@pytest.mark.parametrize(("a", "b"), [
    ("Yatra Online Ltd", "Yatra Online Limited"),
    ("Zaggle Prepaid Ocean Services Limited", "Zaggle Prepaid Ocean Services Ltd"),
    ("A.B.C.  Technologies, Ltd.", "ABC-Technologies Limited"),
])
def test_approved_canonical_variants(a, b):
    assert company_identity.canon(a) == company_identity.canon(b)


def test_two_canonical_hits_are_ambiguous():
    rows = [(1, "ISIN1", "Yatra Online Ltd", "yatra online ltd"),
            (2, "ISIN2", "Yatra Online Limited", "yatra online limited")]
    result = company_identity.resolve_company_identity(
        Cursor(rows), name_norm="yatra online company", company="Yatra Online Company")
    assert result.row is None and result.method == "AMBIGUOUS"
    assert result.ambiguous_count == 2


@pytest.mark.parametrize("name", ["Yatra", "Yatra Online Travel Ltd"])
def test_substrings_and_similar_names_do_not_match(name):
    rows = [(1, "ISIN1", "Yatra Online Ltd", "yatra online ltd")]
    result = company_identity.resolve_company_identity(
        Cursor(rows), name_norm=name.lower(), company=name)
    assert result.row is None and result.method == "UNRESOLVED"


def test_rhp_and_sbi_share_identity_helper():
    assert rhp_link.canon is company_identity.canon
    assert sbi_ingest.resolve_company_identity is company_identity.resolve_company_identity
