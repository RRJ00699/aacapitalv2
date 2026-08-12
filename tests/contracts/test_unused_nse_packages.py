"""Direct NSE client dependencies must have a production caller."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_stock_nse_india_removed_when_no_production_caller_exists():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert "stock-nse-india" not in package["dependencies"]
    assert "node_modules/stock-nse-india" not in lock["packages"]
    production_roots = ("app", "components", "lib", "pipeline", "workers")
    callers = []
    for name in production_roots:
        for path in (ROOT / name).rglob("*"):
            if path.is_file() and "stock-nse-india" in path.read_text(encoding="utf-8", errors="ignore"):
                callers.append(path.relative_to(ROOT).as_posix())
    assert callers == []
