"""
_scripts/kite_connect.py

Shared Kite connection helper.
All scripts import this instead of reading KITE_ACCESS_TOKEN from env.
Token is read from Neon platform_config table.

Usage in any script:
    from _scripts.kite_connect import get_kite
    kite = get_kite()
    data = kite.ltp(["NSE:RELIANCE"])
"""

import os
import logging
import psycopg2
from kiteconnect import KiteConnect

# Self-load .env so DB access works even when the caller didn't export env vars
# (the refresh script self-loads; the pipeline preflight calls us without a shell env).
try:
    from dotenv import load_dotenv
    # repo root = parent of _scripts/ (this file lives in _scripts/)
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env.local"))
    load_dotenv(os.path.join(_root, ".env"))
    load_dotenv(".env.local")  # also try cwd
    load_dotenv(".env")
except Exception:
    pass

log = logging.getLogger(__name__)

API_KEY      = os.environ.get("KITE_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_credentials_from_db() -> tuple[str, str]:
    """Read active Kite access token from Neon platform_config."""
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()
    cur.execute("""SELECT key, value, updated_at FROM platform_config
                   WHERE key IN ('kite_api_key','kite_access_token')""")
    rows = cur.fetchall()
    conn.close()

    values = {row[0]: row[1] for row in rows}
    if not values.get("kite_access_token"):
        raise Exception(
            "No kite_access_token in Neon platform_config.\n"
            "Run: python _scripts/refresh_kite_token.py"
        )

    key = values.get("kite_api_key") or API_KEY
    if not key:
        raise Exception("No KITE_API_KEY available")
    updated_at = next((row[2] for row in rows if row[0] == "kite_access_token"), None)
    log.info(f"Kite credentials from DB (token updated: {str(updated_at)[:16]})")
    return key, values["kite_access_token"]


def get_token_from_db() -> str:
    return get_credentials_from_db()[1]


def get_token() -> str:
    """
    Get Kite access token.
    Priority: 1) Neon DB  2) KITE_ACCESS_TOKEN env var
    """
    # Try DB first
    try:
        if DATABASE_URL:
            return get_token_from_db()
    except Exception as e:
        log.warning(f"DB token fetch failed: {e}")

    # Fall back to env var
    token = os.environ.get("KITE_ACCESS_TOKEN", "")
    if token:
        log.info("Using KITE_ACCESS_TOKEN from environment")
        return token

    raise Exception(
        "No Kite access token available.\n"
        "Run: python _scripts/refresh_kite_token.py"
    )


def resolve_credentials() -> tuple[str, str, str]:
    """Return one complete, unmixed credential pair and its non-secret source."""
    db_error = None
    if DATABASE_URL:
        try:
            key, token = get_credentials_from_db()
            return key, token, "database"
        except Exception as exc:
            db_error = type(exc).__name__
    env_key = os.environ.get("KITE_API_KEY", "")
    env_token = os.environ.get("KITE_ACCESS_TOKEN", "")
    if env_key and env_token:
        return env_key, env_token, "environment"
    if env_key or env_token:
        raise Exception("Incomplete environment Kite credential pair; set both KITE_API_KEY and KITE_ACCESS_TOKEN")
    reason = f"; database lookup failed ({db_error})" if db_error else ""
    raise Exception("No complete Kite credential pair available" + reason)


def get_kite() -> KiteConnect:
    """Return an authenticated KiteConnect instance."""
    api_key, token, source = resolve_credentials()
    log.info("Using Kite credentials from %s", source)
    kite  = KiteConnect(api_key=api_key)
    kite.set_access_token(token)
    return kite
