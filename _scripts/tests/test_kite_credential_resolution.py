import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "kite_connect_resolution", Path(__file__).parents[1] / "kite_connect.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_complete_database_pair_is_used_together(monkeypatch):
    module.DATABASE_URL = "postgresql://configured"
    monkeypatch.setattr(module, "get_credentials_from_db", lambda: ("db-key", "db-token"))
    monkeypatch.setenv("KITE_API_KEY", "env-key")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env-token")
    assert module.resolve_credentials() == ("db-key", "db-token", "database")


def test_failed_database_pair_falls_back_to_complete_environment_pair(monkeypatch):
    module.DATABASE_URL = "postgresql://configured"
    monkeypatch.setattr(module, "get_credentials_from_db",
                        lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))
    monkeypatch.setenv("KITE_API_KEY", "env-key")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env-token")
    assert module.resolve_credentials() == ("env-key", "env-token", "environment")


def test_partial_pairs_fail_without_mixing(monkeypatch):
    module.DATABASE_URL = "postgresql://configured"
    monkeypatch.setattr(module, "get_credentials_from_db",
                        lambda: (_ for _ in ()).throw(RuntimeError("partial DB pair")))
    monkeypatch.setenv("KITE_API_KEY", "env-key")
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    with pytest.raises(Exception, match="Incomplete environment"):
        module.resolve_credentials()


def test_database_token_only_never_mixes_environment_key(monkeypatch):
    class Cursor:
        def execute(self, _sql): pass
        def fetchall(self): return [("kite_access_token", "db-token", None)]
    class Conn:
        def cursor(self): return Cursor()
        def close(self): pass
    module.DATABASE_URL = "postgresql://configured"
    monkeypatch.setattr(module.psycopg2, "connect", lambda _dsn: Conn())
    monkeypatch.setenv("KITE_API_KEY", "env-key")
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    with pytest.raises(Exception, match="Incomplete environment"):
        module.resolve_credentials()


def test_query_exception_always_closes_connection(monkeypatch):
    class Conn:
        closed = False
        def cursor(self): raise RuntimeError("query failed")
        def close(self): self.closed = True
    conn = Conn(); module.DATABASE_URL = "postgresql://configured"
    monkeypatch.setattr(module.psycopg2, "connect", lambda _dsn: conn)
    with pytest.raises(RuntimeError, match="query failed"):
        module.get_credentials_from_db()
    assert conn.closed


def test_refresh_and_fetch_resolve_identical_database_pair(monkeypatch):
    module.DATABASE_URL = "postgresql://configured"
    monkeypatch.setattr(module, "get_credentials_from_db", lambda: ("db-key", "db-token"))
    refresh_pair = module.resolve_credentials()[:2]
    fetch_pair = module.resolve_credentials()[:2]
    assert refresh_pair == fetch_pair == ("db-key", "db-token")
