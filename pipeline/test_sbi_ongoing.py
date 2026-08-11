import unittest
from unittest.mock import patch

from sbi_ongoing import (_safe_cleanup, pending_documents, run_sbi_lane,
                         validate_evidence)


PAGES = [{"page_number": 1, "text": "Rating: Subscribe. A material customer risk exists."}]


class Cursor:
    def __init__(self, rows=()): self.rows=list(rows); self.sql=[]
    def execute(self, sql, params=()): self.sql.append((sql, params))
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows.pop(0)
    def close(self): pass


class Conn:
    closed = False
    def __init__(self, rows=()): self.cur=Cursor(rows); self.commits=0
    def cursor(self): return self.cur
    def commit(self): self.commits += 1


class SBIReadinessTest(unittest.TestCase):
    def test_one_bad_item_drops_and_valid_evidence_survives(self):
        extraction={"claims":[
            {"page_number":1,"excerpt":"material customer risk exists","statement":"risk"},
            {"page_number":1,"excerpt":"invented words","statement":"bad"}],
            "scalar_facts":[]}
        valid, dropped=validate_evidence(extraction, PAGES)
        self.assertEqual([x["statement"] for x in valid["claims"]], ["risk"])
        self.assertEqual(dropped[0]["reason"], "exact_normalized_excerpt_mismatch")

    def test_all_invalid_is_empty_and_fail_closed(self):
        valid, dropped=validate_evidence({"claims":[{"page_number":2,
            "excerpt":"no","statement":"bad"}],"scalar_facts":[]}, PAGES)
        self.assertEqual(valid, {"claims":[],"scalar_facts":[]})
        self.assertEqual(len(dropped), 1)

    def test_closed_cleanup_does_nothing(self):
        class Closed:
            closed=True
            def cursor(self): raise AssertionError("must not mask original exception")
        _safe_cleanup(Closed())

    def test_pending_query_is_fresh_first_and_bounded(self):
        conn=Conn([]); pending_documents(conn, 10)
        sql, params=conn.cur.sql[0]
        self.assertIn("ORDER BY d.fetched_at DESC NULLS LAST,d.id DESC", sql)
        self.assertIn("LIMIT %s", sql); self.assertEqual(params, (10,))

    def test_ingest_runs_without_sonnet_approval(self):
        conn=Conn()
        with patch("sbi_ongoing.pathlib.Path.glob", return_value=["note.pdf"]), \
             patch("sbi_ongoing.ingest_file", return_value={"status":"LEDGERED"}) as ingest:
            report=run_sbi_lane(conn, "/tmp/notes", env={}, store=object())
        self.assertEqual(report["ingest"][0]["status"], "LEDGERED")
        self.assertFalse(report["sonnet_approved"]); ingest.assert_called_once()


if __name__ == "__main__": unittest.main()
