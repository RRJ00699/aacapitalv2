from run_ledger import record_step


class Cursor:
    def __init__(self, columns): self.columns, self.calls = columns, []
    def execute(self, query, params=None): self.calls.append((query, params))
    def fetchall(self): return [(c,) for c in self.columns]


class Conn:
    def __init__(self, columns): self.cur, self.commits = Cursor(columns), 0
    def cursor(self): return self.cur
    def commit(self): self.commits += 1


def test_dry_run_records_nothing():
    conn = Conn({"run_id", "status"})
    assert record_step(conn, {"run_id": "r", "status": "ok"}, dry_run=True) is False
    assert conn.cur.calls == [] and conn.commits == 0


def test_only_real_columns_are_inserted():
    conn = Conn({"run_id", "step_name", "status"})
    assert record_step(conn, {"run_id": "r", "step_name": "nse", "status": "ok", "actual_cost": 0})
    query, params = conn.cur.calls[-1]
    assert "actual_cost" not in query
    assert set(query.split("(", 1)[1].split(")", 1)[0].split(",")) == {"run_id", "step_name", "status"}
    assert set(params) == {"r", "nse", "ok"}
    assert conn.commits == 1
