import pathlib

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
