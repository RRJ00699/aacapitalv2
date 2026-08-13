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
