import pathlib
import re
import shlex

ROOT = pathlib.Path(__file__).resolve().parents[2]

def test_pipeline_automatically_invokes_the_only_snapshot_producer():
    cron = (ROOT / "pipeline/cron.py").read_text()
    assert cron.count('"warm_kv.py"') == 1
    publisher = (ROOT / "pipeline/warm_kv.py").read_text()
    builder = (ROOT / "pipeline/build/build_snapshots.ts").read_text()
    endpoint = (ROOT / "app/api/admin/snapshots/route.ts").read_text()
    assert 'pipeline/build/build_snapshots.ts' in publisher
    assert '/api/admin/snapshots' in builder
    assert '@/lib/db' not in endpoint and '@neondatabase' not in endpoint

def test_ci_build_has_no_fake_database_url():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "postgresql://x:x@localhost/x" not in ci
    assert "env -u DATABASE_URL -u NEON_DATABASE_URL" in ci

def test_all_static_snapshot_consumers_have_no_db_import():
    routes = ["app/api/ipo-command/route.ts", "app/api/ipo/index/route.ts", "app/api/ipo/journey/route.ts", "app/api/ipo/live-preopen/route.ts"]
    for route in routes:
        source = (ROOT / route).read_text()
        assert "@/lib/db" not in source and "@neondatabase" not in source, route


def test_snapshot_publication_workflow_documents_required_configuration():
    wf = (ROOT / ".github/workflows/pipeline.yml").read_text()
    assert "SNAPSHOT_PUBLISH_URL: ${{ vars.SNAPSHOT_PUBLISH_URL }}" in wf
    assert "SNAPSHOT_PUBLISH_KEY: ${{ secrets.SNAPSHOT_PUBLISH_KEY }}" in wf
    assert "NTFY_TOPIC:        ${{ secrets.NTFY_TOPIC }}" in wf
    assert "Snapshot publication configuration required" in wf
    assert "x-aac-key" in wf


def test_schema_smoke_workflow_command_resolves_from_configured_working_directory():
    workflow = (ROOT / ".github/workflows/pipeline.yml").read_text()
    working_directory_match = re.search(
        r"defaults:\s+run:\s+working-directory:\s*([^\s#]+)", workflow
    )
    smoke_step_match = re.search(
        r"- name: Smoke-test snapshot queries.*?\n(?:.*\n)*?\s+run:\s*(npx tsx [^\n]+--schema-smoke)",
        workflow,
    )

    assert working_directory_match, "pipeline job must configure a working directory"
    assert smoke_step_match, "schema-smoke workflow command must be configured"

    working_directory = working_directory_match.group(1)
    command = shlex.split(smoke_step_match.group(1))
    command_path = command[2]
    resolved_path = ROOT / working_directory / command_path

    assert "pipeline/pipeline" not in resolved_path.as_posix()
    assert resolved_path.is_file(), f"workflow command path does not exist: {resolved_path}"
