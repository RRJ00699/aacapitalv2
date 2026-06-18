import os
from pathlib import Path
from urllib.parse import quote


def load_dotenv_files():
    """Tiny dotenv loader so scripts work without python-dotenv installed."""
    root = Path.cwd()
    for name in ('.env.local', '.env'):
        p = root / name
        if not p.exists():
            continue
        for raw in p.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


def db_url(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name) or default
    if not val:
        return None
    # Common Windows/local issue: password has @. Prefer percent-encoded password in env.
    return val


def require_neon_url() -> str:
    url = os.getenv('DATABASE_URL') or os.getenv('NEON_DATABASE_URL')
    if not url:
        raise RuntimeError(
            'DATABASE_URL/NEON_DATABASE_URL required. Add it to .env.local or set it in PowerShell before running.'
        )
    return url
