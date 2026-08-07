"""Static architecture contracts for the cleanup spine."""
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_product_pages_do_not_import_database_clients():
    pages = [
        "app/dashboard/ipo2/page.tsx",
        "app/dashboard/ipo2/details/[isin]/page.tsx",
        "app/dashboard/journey/page.tsx",
    ]
    forbidden = ("@neondatabase/serverless", "@/lib/db", "psycopg", "DATABASE_URL", "NEON_DATABASE_URL")
    hits = {path: token for path in pages for token in forbidden if token in text(path)}
    assert not hits


def test_production_web_code_never_self_migrates_schema():
    pattern = re.compile(r"\b(?:CREATE|ALTER|DROP)\s+TABLE\b", re.I)
    hits = []
    for base in ("app", "lib"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix in {".ts", ".tsx"} and pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                hits.append(str(path.relative_to(ROOT)))
    assert not hits


def test_admin_job_catalogs_are_synchronized():
    runner = ast.parse(text("_scripts/job_runner.py"))
    runner_keys = set()
    for node in ast.walk(runner):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "JOBS" for t in node.targets):
            runner_keys = {k.value for k in node.value.keys}
    api = set(re.findall(r'"([a-z_]+)"', text("app/api/admin/jobs/route.ts").split("const ALLOWED_JOBS",1)[1].split("]);",1)[0]))
    ui = set(re.findall(r'key:\s*"([a-z_]+)"', text("app/dashboard/admin/AdminConsoleClient.tsx")))
    assert runner_keys == api == ui


def test_document_write_owner_is_ledger():
    callers = []
    for base in ("pipeline", "_scripts"):
        for path in (ROOT / base).rglob("*.py"):
            if path.name.startswith("test_") or path.name == "r2.py" or "tests" in path.parts:
                continue
            if re.search(r"(?:r2\.put_document|\.put_document_if_absent)\(", path.read_text(encoding="utf-8", errors="ignore")):
                callers.append(str(path.relative_to(ROOT)))
    assert callers == ["pipeline/document_ledger.py"]


def test_confirmed_dead_tracker_is_not_served_or_referenced():
    assert not (ROOT / "app/api/tracker/route.ts").exists()
    assert not (ROOT / "app/dashboard/tracker/page.tsx").exists()
    hits=[]
    for base in ("app", "components", "lib"):
        for path in (ROOT/base).rglob("*"):
            if path.suffix in {".ts", ".tsx"} and ("/api/tracker" in path.read_text(errors="ignore") or "/dashboard/tracker" in path.read_text(errors="ignore")):
                hits.append(str(path.relative_to(ROOT)))
    assert not hits
