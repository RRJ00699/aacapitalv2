import datetime as dt
import importlib
import os
import json
import sys
from pathlib import Path
import types
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

class Cursor:
    def __init__(self, rows): self.rows=rows; self.executed=[]; self.rowcount=0
    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if sql.lstrip().upper().startswith("INSERT"):
            self.rowcount = 1
    def fetchall(self): return self.rows
    def close(self): pass

class Conn:
    def __init__(self, cursor): self.cursor_obj=cursor; self.committed=False
    def cursor(self): return self.cursor_obj
    def commit(self): self.committed=True
    def close(self): pass

class Kite:
    def __init__(self): self.calls=[]
    def quote(self, symbols):
        self.calls.append(symbols)
        return {symbols[0]: {"last_price": 101, "buy_quantity": 10, "sell_quantity": 4, "ohlc": {"open": 100}, "depth": {}}}

class CapturePreopenTest(unittest.TestCase):
    def load_module(self, rows):
        cur = Cursor(rows)
        conn = Conn(cur)
        psycopg2 = types.SimpleNamespace(connect=lambda _url: conn)
        kite = Kite()
        kite_mod = types.SimpleNamespace(get_kite=lambda: kite)
        os.environ["DATABASE_URL"] = "postgresql://test"
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        sys.modules["psycopg2"] = psycopg2
        sys.modules["_scripts.kite_connect"] = kite_mod
        sys.modules.pop("capture_preopen", None)
        mod = importlib.import_module("capture_preopen")
        return mod, cur, conn, kite

    def test_outside_window_exit_before_db_or_kite(self):
        mod, cur, _conn, kite = self.load_module([])
        count = mod.capture(now=dt.datetime(2026,8,4,8,54,tzinfo=ZoneInfo("Asia/Kolkata")), dry_run=False)
        self.assertEqual(count, 0)
        self.assertEqual(cur.executed, [])
        self.assertEqual(kite.calls, [])

    def test_no_listing_fast_exit_before_kite_or_write(self):
        mod, cur, _conn, kite = self.load_module([])
        count = mod.capture(now=dt.datetime(2026,8,4,8,55,tzinfo=ZoneInfo("Asia/Kolkata")), dry_run=False)
        self.assertEqual(count, 0)
        self.assertEqual(len(cur.executed), 1)
        self.assertEqual(kite.calls, [])

    def test_maximum_count_is_five(self):
        rows=[(i, f"IPO{i}", f"INE00000000{i}", f"SYM{i}", dt.date(2026,8,4), "reason", 100+i) for i in range(1,8)]
        mod, cur, _conn, _kite = self.load_module(rows)
        with patch("builtins.print") as pr:
            mod.capture(now=dt.datetime(2026,8,4,9,0,tzinfo=ZoneInfo("Asia/Kolkata")), limit=5, dry_run=True)
        payload = json.loads(pr.call_args_list[-1].args[0])
        self.assertEqual(len(payload["selected"]), 5)
        self.assertEqual(payload["limit"], 5)

    def test_dry_run_makes_no_kite_call_or_write(self):
        rows=[(1,"IPO","INE000000001","SYM",dt.date(2026,8,4),"reason",200)]
        mod, cur, _conn, kite = self.load_module(rows)
        mod.capture(now=dt.datetime(2026,8,4,9,0,tzinfo=ZoneInfo("Asia/Kolkata")), dry_run=True)
        self.assertEqual(kite.calls, [])
        self.assertFalse(any(sql.lstrip().upper().startswith("INSERT") for sql,_ in cur.executed))

    def test_six_to_fifteen_eligible_are_captured(self):
        rows=[(i, f"IPO{i}", f"INE000000{i:03d}", f"SYM{i}", dt.date(2026,8,4), "reason", 200+i) for i in range(1,13)]
        mod, _cur, _conn, kite = self.load_module(rows)
        count=mod.capture(now=dt.datetime(2026,8,4,9,0,tzinfo=ZoneInfo("Asia/Kolkata")), limit=15, dry_run=False, retries=0)
        self.assertEqual(count, 12)
        self.assertEqual(len(kite.calls), 12)

    def test_more_than_fifteen_is_bounded(self):
        rows=[(i, f"IPO{i}", f"INE000000{i:03d}", f"SYM{i}", dt.date(2026,8,4), "reason", 200+i) for i in range(1,21)]
        mod, _cur, _conn, kite = self.load_module(rows)
        count=mod.capture(now=dt.datetime(2026,8,4,9,0,tzinfo=ZoneInfo("Asia/Kolkata")), limit=99, dry_run=False, retries=0)
        self.assertEqual(count, 15)
        self.assertEqual(len(kite.calls), 15)

    def test_mainboard_150cr_priority_is_in_selection_sql(self):
        mod, cur, _conn, _kite = self.load_module([])
        mod.capture(now=dt.datetime(2026,8,4,9,0,tzinfo=ZoneInfo("Asia/Kolkata")), dry_run=True)
        sql = cur.executed[0][0]
        self.assertIn("MAX(issue_size_cr) AS issue_size_cr", sql)
        self.assertIn("GROUP BY ipo_id", sql)
        self.assertIn("COALESCE(issue.issue_size_cr,0) >= 150", sql)
        self.assertIn("issue.issue_size_cr DESC NULLS LAST", sql)
        self.assertIn("i.isin IS NOT NULL", sql)
        self.assertIn("i.id", sql)

    def test_idempotent_write_contract(self):
        rows=[(1,"IPO","INE000000001","SYM",dt.date(2026,8,4),"reason",200)]
        mod, cur, conn, kite = self.load_module(rows)
        count=mod.capture(now=dt.datetime(2026,8,4,9,0,tzinfo=ZoneInfo("Asia/Kolkata")), dry_run=False, retries=0)
        inserts=[x for x in cur.executed if x[0].lstrip().upper().startswith("INSERT")]
        self.assertEqual(count, 1)
        self.assertTrue(conn.committed)
        self.assertEqual(kite.calls, [["NSE:SYM"]])
        self.assertIn("ON CONFLICT (ipo_id,obs_type,observed_at) DO NOTHING", inserts[0][0])
        self.assertIn("'preopen'", inserts[0][0])
        self.assertEqual(json.loads(inserts[0][1][-1])["isin"], "INE000000001")

if __name__ == "__main__":
    unittest.main()
