from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_public_worker_cannot_access_kite_access_token():
    route = read("app", "api", "ipo", "live-preopen", "route.ts")
    public_cfg = read("wrangler.jsonc")
    assert "KITE_ACCESS_TOKEN" not in public_cfg
    assert "KITE_ACCESS_TOKEN" not in route


def test_broker_worker_is_dedicated_and_endpoint_limited():
    src = read("workers", "kite-broker-proxy", "src", "index.ts")
    assert 'url.pathname === "/health"' in src
    assert 'url.pathname !== "/quotes"' in src
    assert "unsupported_endpoint" in src
    assert "MAX_SYMBOLS = 15" in src


def test_no_kite_token_written_to_kv_or_public_env():
    src = read("workers", "kite-broker-proxy", "src", "index.ts")
    route = read("app", "api", "ipo", "live-preopen", "route.ts")
    assert "broker:kite:access-token" not in src
    assert "KVNamespace" not in src
    assert "KITE_ACCESS_TOKEN" not in route


def test_rotation_default_does_not_write_platform_config_token():
    src = read("_scripts", "refresh_kite_token.py")
    assert "def legacy_save_to_db" in src
    assert 'ALLOW_LEGACY_KITE_DB_TOKEN_WRITE") != "1"' in src
    assert "rotate_worker_secret(access_token)" in src
    main_after = src.split("def main():", 1)[1]
    assert "save_to_db(access_token)" not in main_after.replace("legacy_save_to_db(access_token)", "")
    assert "access_token[:8]" not in src


def test_ntfy_attempted_on_rotation_failure():
    src = read("_scripts", "refresh_kite_token.py")
    assert "Broker verification failed" in src
    assert "_alert" in src
    assert "last_snapshot_timestamp" in src


def test_live_preopen_uses_snapshot_symbols_only():
    route = read("app", "api", "ipo", "live-preopen", "route.ts")
    helper = read("lib", "kite", "broker-proxy.ts")
    assert "approvedSymbolsFromSnapshot(payload)" in route
    assert "searchParams" not in route
    assert "allowed_symbols: params.symbols" in helper
