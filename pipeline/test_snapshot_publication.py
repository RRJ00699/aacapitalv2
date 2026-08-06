import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import warm_kv
import publish_snapshot_with_ledger as publisher

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
LEDGER = PIPELINE / "snapshot_publication_ledger.json"


def test_warm_kv_resolves_posix_npx(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/npx" if name == "npx" else None)
    assert warm_kv.resolve_npx() == "/usr/bin/npx"


def test_warm_kv_resolves_windows_npx_cmd(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "C:/node/npx.cmd" if name == "npx.cmd" else None)
    assert warm_kv.resolve_npx() == "C:/node/npx.cmd"


def test_warm_kv_missing_executable_fails_clearly(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="npx executable not found"):
        warm_kv.resolve_npx()


def test_warm_kv_passes_exact_resolved_command(monkeypatch):
    calls = []
    monkeypatch.setattr(warm_kv, "resolve_npx", lambda: "/bin/npx")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
    warm_kv.publish(limit=7, concurrency=2, dry_run=True)
    assert calls[0][0] == ["/bin/npx", "tsx", "pipeline/build/build_snapshots.ts", "--limit=7", "--concurrency=2", "--dry-run"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["cwd"] == str(ROOT)


class SnapshotEndpoint(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _pointer(name, which):
    return f"snapshot:{name}:{which}"


def _data_key(name, version):
    return f"snapshot:{name}:data:{version}"


class SnapshotHandler(http.server.BaseHTTPRequestHandler):
    expected_key = "unit-publish-key"
    kv = {}
    requests_seen = []
    fail_http = False
    fail_on_request = None
    skip_pointer = False

    def log_message(self, *_args):
        return

    def do_POST(self):
        self.__class__.requests_seen.append({"path": self.path, "key": self.headers.get("x-aac-key")})
        if self.path != "/api/admin/snapshots":
            self.send_response(404); self.end_headers(); return
        if self.headers.get("x-aac-key") != self.expected_key:
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"unauthorized"}'); return
        if self.fail_http or self.fail_on_request == len(self.requests_seen):
            self.send_response(503); self.end_headers(); self.wfile.write(b'{"error":"forced"}'); return
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
        published = {}
        for item in body["snapshots"]:
            name = item["name"]
            payload = json.dumps(item["payload"])
            version = f"v{len(self.kv)}"
            old = self.kv.get(_pointer(name, "active"))
            self.kv[_data_key(name, version)] = payload
            if old and old != version:
                self.kv[_pointer(name, "previous")] = old
            if not self.skip_pointer:
                self.kv[_pointer(name, "active")] = version
            published[name] = version
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "published": published}).encode())


class ServerContext:
    def __enter__(self):
        SnapshotHandler.kv = {}
        SnapshotHandler.requests_seen = []
        SnapshotHandler.fail_http = False
        SnapshotHandler.fail_on_request = None
        SnapshotHandler.skip_pointer = False
        self.server = SnapshotEndpoint(("127.0.0.1", 0), SnapshotHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.thread.join(timeout=5)


def run_publisher(origin, key="unit-publish-key", extra_env=None):
    env = os.environ.copy()
    env.update({
        "SNAPSHOT_PUBLISH_URL": origin,
        "SNAPSHOT_PUBLISH_KEY": key,
        "SNAPSHOT_TEST_FIXTURE": "1",
        "DATABASE_URL": "postgresql://fixture-not-used",
    })
    env.pop("NTFY_TOPIC", None)
    if extra_env:
        env.update(extra_env)
    LEDGER.unlink(missing_ok=True)
    return subprocess.run([sys.executable, "pipeline/publish_snapshot_with_ledger.py"], cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)


def consume_with_versioned_snapshot(kv):
    dump = PIPELINE / ".snapshot_test_kv.json"
    dump.write_text(json.dumps(kv), encoding="utf-8")
    try:
        script = """
          import { readVersionedSnapshot } from './lib/versioned-snapshot.ts';
          import fs from 'node:fs';
          async function main() {
            const data = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
            const kv = { get: async (k) => data[k] ?? null, put: async () => { throw new Error('read only') } };
            const hit = await readVersionedSnapshot(kv, 'ipo-command:v6');
            console.log(JSON.stringify({ source: hit?.source, payload: JSON.parse(hit?.payload ?? '{}') }));
          }
          main().catch((err) => { console.error(err); process.exit(1); });
        """
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        assert npx, "npx required for consumer proof"
        out = subprocess.check_output([npx, "tsx", "-e", script, str(dump)], cwd=ROOT, text=True, timeout=30)
        return json.loads(out)
    finally:
        dump.unlink(missing_ok=True)


def test_real_producer_chain_origin_without_trailing_slash_switches_active_pointer_and_consumer_hit():
    with ServerContext() as srv:
        res = run_publisher(srv.url)
        print("STDOUT\n" + res.stdout)
        print("STDERR\n" + res.stderr)
        assert res.returncode == 0
        assert SnapshotHandler.requests_seen == [
            {"path": "/api/admin/snapshots", "key": "unit-publish-key"},
            {"path": "/api/admin/snapshots", "key": "unit-publish-key"},
        ]
        active = SnapshotHandler.kv.get(_pointer("ipo-command:v6", "active"))
        assert active
        assert _data_key("ipo-command:v6", active) in SnapshotHandler.kv
        hit = consume_with_versioned_snapshot(SnapshotHandler.kv)
        assert hit["source"] == "active"
        assert hit["payload"]["cards"][0]["sym"] == "FIXTURE"
        details_active = SnapshotHandler.kv.get(_pointer("ipo-details:isin:INE000000001:v1", "active"))
        assert details_active
        details = json.loads(SnapshotHandler.kv[_data_key("ipo-details:isin:INE000000001:v1", details_active)])
        assert details["schema_version"] == "ipo-details-v1"


def test_real_builder_fixture_executes_and_checks_ipo_identity_and_date_parameter_sql():
    with ServerContext() as srv:
        res = run_publisher(srv.url)
        assert res.returncode == 0, res.stdout + res.stderr
        assert '"snapshot_fixture_sql_verified":true' in res.stdout


def test_builder_postgres_failure_names_stage_domain_and_redacts_database_url():
    secret_url = "postgresql://secret-user:secret-password@example.invalid/db"
    with ServerContext() as srv:
        res = run_publisher(srv.url, extra_env={
            "DATABASE_URL": secret_url,
            "SNAPSHOT_TEST_POSTGRES_ERROR": "1",
        })
        output = res.stdout + res.stderr
        assert res.returncode != 0
        assert "[snapshot builder]" in output
        assert "stage=query" in output
        assert "domain=journey-universe" in output
        assert "PostgreSQL error: column i.forced_missing does not exist" in output
        assert secret_url not in output
        assert "secret-password" not in output


def test_schema_smoke_requires_real_read_only_neon_but_not_publication_credentials():
    env = os.environ.copy()
    for name in ("DATABASE_URL", "NEON_DATABASE_URL", "NEON_READONLY_DATABASE_URL",
                 "SNAPSHOT_PUBLISH_URL", "SNAPSHOT_PUBLISH_KEY", "SNAPSHOT_TEST_FIXTURE"):
        env.pop(name, None)
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    assert npx
    res = subprocess.run(
        [npx, "tsx", "pipeline/build/build_snapshots.ts", "--limit=1", "--concurrency=1", "--schema-smoke"],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=30,
    )
    output = res.stdout + res.stderr
    assert res.returncode != 0
    assert "NEON_READONLY_DATABASE_URL is required for schema smoke" in output
    assert "SNAPSHOT_PUBLISH_URL" not in output
    assert "SNAPSHOT_PUBLISH_KEY" not in output


def test_schema_smoke_cannot_skip_details_sql_when_selected_universe_is_empty():
    """Regression: stale Details columns must fail schema smoke even on a zero-IPO day."""
    builder = (ROOT / "pipeline/build/build_snapshots.ts").read_text(encoding="utf-8")
    assert "const detailIds = selected.length || !schemaSmoke" in builder
    assert ": [-1]" in builder
    assert 'fetchDetailsRows(sql, detailIds)' in builder
    assert 'atBuilderStage("ipo-details"' in builder


def test_real_producer_chain_origin_with_trailing_slash_keeps_single_endpoint_path():
    with ServerContext() as srv:
        res = run_publisher(srv.url + "/")
        assert res.returncode == 0, res.stdout + res.stderr
        assert SnapshotHandler.requests_seen[0]["path"] == "/api/admin/snapshots"


def test_full_endpoint_url_is_normalized_without_duplicating_route():
    with ServerContext() as srv:
        res = run_publisher(srv.url + "/api/admin/snapshots")
        assert res.returncode == 0, res.stdout + res.stderr
        assert SnapshotHandler.requests_seen[0]["path"] == "/api/admin/snapshots"


def test_missing_snapshot_publish_url_fails_before_builder_and_records_ledger():
    env = os.environ.copy(); env.pop("SNAPSHOT_PUBLISH_URL", None); env["SNAPSHOT_PUBLISH_KEY"] = "k"; env.pop("NTFY_TOPIC", None)
    LEDGER.unlink(missing_ok=True)
    res = subprocess.run([sys.executable, "pipeline/publish_snapshot_with_ledger.py"], cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
    assert res.returncode != 0
    assert "SNAPSHOT_PUBLISH_URL" in LEDGER.read_text()
    ledger = json.loads(LEDGER.read_text())
    assert ledger["alert_status"] == "NOT_CONFIGURED"
    assert "::warning::" in res.stdout
    assert "snapshot builder command" not in res.stdout


def test_missing_snapshot_publish_key_fails_before_builder_and_records_ledger():
    env = os.environ.copy(); env["SNAPSHOT_PUBLISH_URL"] = "https://example.com"; env.pop("SNAPSHOT_PUBLISH_KEY", None); env.pop("NTFY_TOPIC", None)
    LEDGER.unlink(missing_ok=True)
    res = subprocess.run([sys.executable, "pipeline/publish_snapshot_with_ledger.py"], cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
    assert res.returncode != 0
    ledger = json.loads(LEDGER.read_text())
    assert "SNAPSHOT_PUBLISH_KEY" in ledger["error"]
    assert ledger["alert_status"] == "NOT_CONFIGURED"
    assert "snapshot builder command" not in res.stdout


def test_wrong_x_aac_key_http_failure_records_failed_ledger():
    with ServerContext() as srv:
        res = run_publisher(srv.url, key="wrong")
        assert res.returncode != 0
        ledger = json.loads(LEDGER.read_text())
        assert ledger["status"] == "failed"
        assert ledger["returncode"] != 0
        assert SnapshotHandler.requests_seen[0]["key"] == "wrong"


def test_http_publication_failure_records_failed_ledger():
    with ServerContext() as srv:
        SnapshotHandler.fail_http = True
        res = run_publisher(srv.url)
        assert res.returncode != 0
        ledger = json.loads(LEDGER.read_text())
        assert ledger["status"] == "failed"
        assert SnapshotHandler.kv == {}, "failed global/Journey request must fail before any Details request"


def test_failed_details_batch_preserves_successful_global_journey_and_records_batch_isin():
    with ServerContext() as srv:
        SnapshotHandler.fail_on_request = 2  # globals/Journey succeed; first Details batch fails
        res = run_publisher(srv.url)
        assert res.returncode != 0
        assert SnapshotHandler.kv.get(_pointer("ipo-command:v6", "active"))
        assert SnapshotHandler.kv.get(_pointer("journey:isin:INE000000001:v1", "active"))
        assert SnapshotHandler.kv.get(_pointer("ipo-details:isin:INE000000001:v1", "active")) is None
        ledger = json.loads(LEDGER.read_text())
        assert ledger["status"] == "failed"
        assert ledger["details_batch"] == 1
        assert ledger["failing_isins"] == ["INE000000001"]


def test_missing_pointer_switch_is_detected_by_consumer_proof():
    with ServerContext() as srv:
        SnapshotHandler.skip_pointer = True
        res = run_publisher(srv.url)
        assert res.returncode == 0
        assert SnapshotHandler.kv.get(_pointer("ipo-command:v6", "active")) is None
        hit = consume_with_versioned_snapshot(SnapshotHandler.kv)
        assert hit["payload"] == {}


def test_missing_npx_fails_clear(monkeypatch):
    with ServerContext() as srv:
        env = {"PATH": str(PIPELINE)}
        res = run_publisher(srv.url, extra_env=env)
        assert res.returncode != 0
        ledger = json.loads(LEDGER.read_text())
        assert "snapshot builder exited" in ledger["error"]
        assert "npx executable not found" in (res.stdout + res.stderr)


def test_tsx_compile_failure_fails_publication(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    npx = fakebin / ("npx.cmd" if os.name == "nt" else "npx")
    npx.write_text("#!/bin/sh\necho 'tsx compile failed' >&2\nexit 7\n")
    npx.chmod(0o755)
    with ServerContext() as srv:
        res = run_publisher(srv.url, extra_env={"PATH": str(fakebin)})
        assert res.returncode != 0
        ledger = json.loads(LEDGER.read_text())
        assert ledger["returncode"] != 0
        assert "tsx compile failed" in res.stderr


def test_configured_ntfy_path_is_attempted_on_failure(monkeypatch):
    calls = []
    class FakeResponse:
        def read(self): return b"ok"
    monkeypatch.setenv("NTFY_TOPIC", "unit-topic")
    monkeypatch.delenv("SNAPSHOT_PUBLISH_URL", raising=False)
    monkeypatch.setenv("SNAPSHOT_PUBLISH_KEY", "k")
    monkeypatch.setattr(publisher.urllib.request, "urlopen", lambda req, timeout=10: calls.append((req.full_url, timeout)) or FakeResponse())
    code = publisher.main()
    ledger = json.loads(publisher.LEDGER.read_text())
    assert code == 1
    assert calls and calls[0][0] == "https://ntfy.sh/unit-topic"
    assert ledger["alert_status"] == "SENT"
