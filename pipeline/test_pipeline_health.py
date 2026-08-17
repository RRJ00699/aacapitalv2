import datetime as dt
import json
from pathlib import Path
import re

import pipeline_health as health


class Response:
    def __init__(self, value): self.value = value
    def read(self): return json.dumps(self.value).encode()


def rows(status_error=""):
    now = dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc)
    return [("schema sync (single owner of DDL)", True, status_error, now),
            ("smoke probe (live API)", True, "", now)]


def test_health_contract_success_partial_failure_skip_and_secret_redaction():
    secret = "postgresql://user:password@host/db"
    failures = [("refresh GMP", "\n".join(["line"] * 13 + [secret]),
                 dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc))]
    payload = health.build_payload(rows("partial: retry_required"), failures,
                                   environ={"DATABASE_URL": secret})
    assert payload["run_complete"] is True
    assert payload["steps"][0]["status"] == "partial"
    assert secret not in json.dumps(payload)
    assert len(payload["failures"][0]["stderr_tail"].splitlines()) == 12
    failed = health.build_payload([("x", False, "boom", None)], [])
    assert failed["steps"][0]["status"] == "failed" and failed["run_complete"] is False
    skipped = health.build_payload([("x", True, "skipped — unavailable", None)], [])
    assert skipped["steps"][0]["status"] == "skipped"


def test_absent_publication_configuration_is_zero_call_skip():
    def forbidden(*_args, **_kwargs): raise AssertionError("network called")
    result = health.publish({}, environ={}, urlopen=forbidden)
    assert result == {"step": "pipeline health publication", "status": "skipped",
                      "reason": "owner: configure snapshot publication"}


def test_health_uses_existing_snapshot_endpoint_and_confirms_version_without_leaking_key():
    seen = {}
    def open_request(request, timeout):
        seen.update(url=request.full_url, timeout=timeout,
                    body=json.loads(request.data), key=request.headers["X-aac-key"])
        return Response({"published": {health.SNAPSHOT_NAME: "version-1"}})
    env = {"SNAPSHOT_PUBLISH_URL": "https://example.test/base", "SNAPSHOT_PUBLISH_KEY": "secret-key"}
    result = health.publish({"run_complete": True}, environ=env, urlopen=open_request)
    assert result == {"step": "pipeline health publication", "status": "ok", "version": "version-1"}
    assert seen["url"] == "https://example.test/api/admin/snapshots"
    assert seen["body"]["snapshots"][0]["name"] == "pipeline-health:v1"
    assert "secret-key" not in json.dumps(result)


def test_failed_pointer_confirmation_is_visible_and_preserves_prior_state_by_no_claim():
    result = health.publish({}, environ={"SNAPSHOT_PUBLISH_URL": "https://example.test",
                            "SNAPSHOT_PUBLISH_KEY": "key"},
                            urlopen=lambda *_args, **_kwargs: Response({"published": {}}))
    assert result["status"] == "failed"
    assert result["reason"] == "pipeline health active pointer was not confirmed"


def test_expected_lane_contract_matches_existing_admin_consumer_order():
    source = (Path(__file__).parents[1] / "lib" / "pipeline-steps.ts").read_text(encoding="utf-8")
    expected = tuple(re.findall(r'\{ step: "([^"]+)"', source))
    assert health.EXPECTED_LEAN_STEPS == expected
