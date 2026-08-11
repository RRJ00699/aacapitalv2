"""Offline regressions for owner-observed derived-stage row shapes."""
import drive
import score_engine


class OwnerRowCursor:
    def __init__(self):
        self.query = ""

    def execute(self, query, _params=None):
        self.query = " ".join(query.split())

    def fetchone(self):
        if "FROM ipo_issue" in self.query:
            # Original owner compatibility shape: price/high/low only.  The scorer's
            # newer SELECT also asks for issue_size_cr/ofs_cr as trailing fields.
            return (100, 105, 95)
        return None

    def fetchall(self):
        if "FROM financial_statements" in self.query:
            return [("31-Mar-25", "Consolidated", 500, 80, 40, 200, 20, 300)]
        if "FROM source_facts" in self.query:
            return []
        return []


class OwnerRowConnection:
    def cursor(self):
        return OwnerRowCursor()


def test_drive_derived_accepts_owner_issue_tuple_in_dry_and_write_modes(monkeypatch):
    writes = []
    monkeypatch.setattr(score_engine, "write_valuation", lambda conn, value: writes.append(value))

    dry = drive.step_derived(OwnerRowConnection(), 5, False)
    live = drive.step_derived(OwnerRowConnection(), 12, True)

    assert dry["status"] == "dry"
    assert live["status"] == "ok"
    assert len(writes) == 1
    assert dry["score"] is not None and live["score"] == dry["score"]
