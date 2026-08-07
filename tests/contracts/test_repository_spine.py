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


def test_production_code_has_no_legacy_neon_url_fallback():
    """NEON_DATABASE_URL is not a production credential alias.

    Tests may clear the old variable to prove absence; production app/lib/pipeline
    code must neither read it nor silently fall back to it.
    """
    hits = []
    for base in ("app", "lib", "pipeline"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or "test" in path.name:
                continue
            if "NEON_DATABASE_URL" in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(path.relative_to(ROOT)))
    assert not hits


def test_command_and_details_share_canonical_intelligence_inputs():
    for path in ("lib/v2/ipo-command.ts", "lib/v2/ipo-details.ts"):
        source = text(path)
        assert 'from "@/lib/intelligence/canonical-inputs"' in source
        assert "buildCanonicalProFormaInputs" in source


def test_canonical_profile_contract_and_economic_engine_remain_single_owned():
    profile = text("lib/intelligence/ipo-profile.ts")
    schema = text("lib/intelligence/ipo-profile.schema.json")
    assert 'IPO_PROFILE_SCHEMA_VERSION = "ipo-profile:v1"' in profile
    assert '"const": "ipo-profile:v1"' in schema
    assert "calculateProForma" in profile


def test_snapshot_publication_is_zero_wake_and_keeps_previous_pointer():
    route = text("app/api/admin/snapshots/route.ts")
    snapshot = text("lib/versioned-snapshot.ts")
    assert "@neondatabase/serverless" not in route
    assert "DATABASE_URL" not in route
    assert 'pointer(name, "previous")' in snapshot
    assert 'pointer(name, "active")' in snapshot


def test_extraction_and_valuation_owners_are_explicit():
    assert "rhp_sections" in text("pipeline/rhp_sonnet.py")
    assert "from rhp_writer import route_extraction" in text("pipeline/rhp_sonnet.py")
    assert (ROOT / "pipeline/score_engine.py").is_file()
    assert (ROOT / "lib/intelligence/ipo-profile.ts").is_file()


def test_live_subprocess_and_workflow_paths_exist():
    corpus = "\n".join(text(path) for path in (
        "_scripts/job_runner.py", ".github/workflows/pipeline.yml",
        ".github/workflows/preopen-capture.yml", ".github/workflows/sbi-notes.yml",
    ))
    candidates = set(re.findall(r"(?:pipeline|_scripts)/[A-Za-z0-9_./-]+\.(?:py|ts|mjs)", corpus))
    missing = sorted(path for path in candidates if not (ROOT / path).exists())
    assert not missing


def test_duplicate_pipeline_script_tree_is_gone():
    duplicate_dir = ROOT / "pipeline" / "_scripts"
    assert not duplicate_dir.exists() or not any(duplicate_dir.iterdir())


def test_classified_scripts_live_outside_production_script_tree():
    inventory = text("docs/repository-inventory.tsv")
    forbidden = []
    for line in inventory.splitlines()[1:]:
        path, classification, *_ = line.split("\t")
        if path.startswith("_scripts/") and classification in {"RESEARCH", "DIAGNOSTIC", "SUPERSEDED"}:
            forbidden.append((path, classification))
    assert not forbidden


def test_consolidated_compatibility_is_not_called_by_production():
    runner = text("_scripts/job_runner.py")
    lean = text("_scripts/run_ipo_pipeline_lean.py")
    assert "compatibility/consolidated/" not in runner
    assert "../compatibility/consolidated/" not in lean
    for name in ("consolidate_master.py", "build_ipo_consolidated.py", "build_ipo_consolidated_v2.py"):
        assert not (ROOT / "_scripts" / name).exists()


def test_current_docs_use_the_architecture_hierarchy():
    root_docs = sorted(path.name for path in (ROOT / "docs").glob("*.md"))
    # IPO_INTELLIGENCE_V1 remains UNKNOWN and therefore cannot be moved by cleanup.
    assert root_docs == ["IPO_INTELLIGENCE_V1.md"]
