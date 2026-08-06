"""Unit and structural tests for the immutable R2 document contract."""

from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

import document_contract as contract
import probe_r2_document_store as probe
import r2


ROOT = Path(__file__).resolve().parents[1]


def pdf_bytes(size=100 * 1024):
    return b"%PDF-" + b"0" * (size - 5)


RHP_PDF = pdf_bytes()
DIGEST = sha256(RHP_PDF).hexdigest()


class NotFound(Exception):
    response = {"ResponseMetadata": {"HTTPStatusCode": 404}, "Error": {"Code": "NoSuchKey"}}


class PreconditionConflict(Exception):
    response = {
        "ResponseMetadata": {"HTTPStatusCode": 412},
        "Error": {"Code": "PreconditionFailed"},
    }


class FakeClient:
    def __init__(self, *, head=None, put_error=None, post_head_error=None):
        self.head = head
        self.put_error = put_error
        self.post_head_error = post_head_error
        self.puts = []
        self.heads = 0

    def head_object(self, **kwargs):
        self.heads += 1
        if self.post_head_error and self.puts:
            raise self.post_head_error
        if self.head is None:
            raise NotFound()
        return self.head

    def put_object(self, **kwargs):
        if self.put_error:
            raise self.put_error
        self.puts.append(kwargs)
        body = kwargs["Body"]
        position = body.tell()
        payload = body.read()
        body.seek(position)
        self.head = matching_head(len(payload), kwargs["Metadata"]["sha256"])

    def get_object(self, **kwargs):
        return {"Body": io.BytesIO(b"pdf")}


class BoundedOversizedStream:
    """Seekable fake proving the validator stops one byte beyond the maximum."""

    def __init__(self, size):
        self.size = size
        self.position = 0
        self.largest_read = 0

    def tell(self):
        return self.position

    def seek(self, position):
        self.position = position

    def read(self, amount):
        self.largest_read = max(self.largest_read, amount)
        remaining = self.size - self.position
        if remaining <= 0:
            return b""
        count = min(amount, remaining)
        start = self.position
        self.position += count
        prefix = b"%PDF-" if start == 0 else b""
        return prefix + b"0" * (count - len(prefix))


def matching_head(size=len(RHP_PDF), digest=DIGEST):
    return {
        "ContentLength": size,
        "ContentType": "application/pdf",
        "Metadata": {"sha256": digest, "contract-version": contract.CONTRACT_VERSION},
    }


def store(fake):
    return r2.R2DocumentStore(client=fake, bucket="aacapital-ipo-documents")


def test_canonical_rhp_key():
    assert contract.document_key("RHP", DIGEST, "2026-08-01", isin="INE17IR01028") == f"rhp/INE17IR01028/2026-08-01/{DIGEST}.pdf"


def test_canonical_sbi_and_unresolved_keys():
    assert contract.document_key("sbi", DIGEST, "2026-08-01", isin="INE17IR01028").startswith("sbi/INE17IR01028/")
    assert contract.document_key("sbi", DIGEST, "2026-08-01", ipo_id=123) == f"sbi/unresolved-ipo-123/2026-08-01/{DIGEST}.pdf"


@pytest.mark.parametrize("isin", ["INE17IR0102", "US017IR01028", "INE17IR0102X", "company-ltd"])
def test_invalid_isin_rejected(isin):
    with pytest.raises(ValueError):
        contract.document_key("rhp", DIGEST, "2026-08-01", isin=isin)


def test_invalid_document_type_rejected():
    with pytest.raises(ValueError):
        contract.document_key("research_note", DIGEST, "2026-08-01", ipo_id=1)


@pytest.mark.parametrize("digest", ["abc", "A" * 64, "g" * 64])
def test_malformed_sha_rejected(digest):
    with pytest.raises(ValueError):
        contract.document_key("rhp", digest, "2026-08-01", ipo_id=1)


@pytest.mark.parametrize("value", ["2026-8-1", "2026-02-30", "2026-08-01T00:00:00Z"])
def test_invalid_date_rejected(value):
    with pytest.raises(ValueError):
        contract.document_key("rhp", DIGEST, value, ipo_id=1)


def test_company_name_never_enters_key_and_same_bytes_same_key():
    content = b"same immutable bytes"
    digest = sha256(content).hexdigest()
    first = contract.document_key("rhp", digest, "2026-08-01", ipo_id=7)
    second = contract.document_key("rhp", sha256(content).hexdigest(), "2026-08-01", ipo_id=7)
    assert first == second
    assert "company" not in first.lower()


def test_pdf_validation_limits():
    assert contract.pdf_validation_config("rhp").minimum_bytes == 100 * 1024
    assert contract.pdf_validation_config("sbi").minimum_bytes == 10 * 1024
    assert contract.pdf_validation_config("rhp").maximum_bytes == 100 * 1024 * 1024


def test_existing_matching_object_performs_no_put():
    fake = FakeClient(head=matching_head())
    assert store(fake).put_document_if_absent("rhp/x", RHP_PDF, DIGEST, doc_type="rhp").startswith("r2://")
    assert fake.puts == []


@pytest.mark.parametrize("head", [matching_head(len(RHP_PDF) + 1), matching_head(digest="b" * 64)])
def test_existing_mismatching_object_fails_closed(head):
    fake = FakeClient(head=head)
    with pytest.raises(r2.R2ContractError):
        store(fake).put_document_if_absent("rhp/x", RHP_PDF, DIGEST, doc_type="rhp")
    assert fake.puts == []


def test_missing_object_puts_then_heads_and_verifies():
    fake = FakeClient()
    store(fake).put_document_if_absent("rhp/x", RHP_PDF, DIGEST, doc_type="rhp")
    assert len(fake.puts) == 1
    assert fake.heads == 2
    assert fake.puts[0]["ContentType"] == "application/pdf"
    assert fake.puts[0]["Metadata"] == contract.object_metadata(DIGEST)
    assert fake.puts[0]["IfNoneMatch"] == "*"


@pytest.mark.parametrize("kind,size", [("rhp", 100 * 1024), ("sbi", 10 * 1024)])
def test_valid_pdf_type_and_minimum(kind, size):
    payload = pdf_bytes(size)
    fake = FakeClient()
    store(fake).put_document_if_absent(
        f"{kind}/x", payload, sha256(payload).hexdigest(), doc_type=kind
    )
    assert len(fake.puts) == 1


@pytest.mark.parametrize(
    ("payload", "kind", "content_type", "digest", "message"),
    [
        (b"not-pdf" + b"0" * (100 * 1024), "rhp", "application/pdf", None, "magic"),
        (pdf_bytes(100 * 1024 - 1), "rhp", "application/pdf", None, "minimum"),
        (pdf_bytes(10 * 1024 - 1), "sbi", "application/pdf", None, "minimum"),
        (RHP_PDF, "rhp", "text/plain", None, "content type"),
        (RHP_PDF, "rhp", "application/pdf", "b" * 64, "sha256"),
    ],
)
def test_invalid_pdf_performs_no_r2_call(payload, kind, content_type, digest, message):
    fake = FakeClient()
    requested = digest or sha256(payload).hexdigest()
    with pytest.raises(ValueError, match=message):
        store(fake).put_document_if_absent(
            "x", payload, requested, doc_type=kind, content_type=content_type
        )
    assert fake.heads == 0 and fake.puts == []


def test_oversized_stream_is_bounded_and_performs_no_r2_call():
    source = BoundedOversizedStream(contract.MAX_PDF_BYTES + 1)
    fake = FakeClient()
    with pytest.raises(ValueError, match="maximum"):
        store(fake).put_document_if_absent("x", source, DIGEST, doc_type="sbi")
    assert source.largest_read <= 1024 * 1024
    assert source.tell() == 0
    assert fake.heads == 0 and fake.puts == []


@pytest.mark.parametrize("head", [matching_head(), matching_head(digest="b" * 64)])
def test_concurrent_creation_race_accepts_only_exact_match(head):
    fake = FakeClient(put_error=PreconditionConflict())
    original_head = fake.head_object

    def race_head(**kwargs):
        if not fake.puts and fake.heads == 0:
            fake.heads += 1
            raise NotFound()
        return head

    fake.head_object = race_head
    # Record an attempted conditional PUT before raising the simulated race.
    original_put = fake.put_object
    fake.put_object = lambda **kwargs: (fake.puts.append(kwargs), original_put(**kwargs))[1]
    if head["Metadata"]["sha256"] == DIGEST:
        assert store(fake).put_document_if_absent("x", RHP_PDF, DIGEST, doc_type="rhp").startswith("r2://")
    else:
        with pytest.raises(r2.R2ContractError):
            store(fake).put_document_if_absent("x", RHP_PDF, DIGEST, doc_type="rhp")
    assert fake.puts[0]["IfNoneMatch"] == "*"


def test_put_failure_fails():
    with pytest.raises(r2.R2OperationError):
        store(FakeClient(put_error=RuntimeError("failed"))).put_document_if_absent("x", RHP_PDF, DIGEST, doc_type="rhp")


def test_post_put_head_failure_fails():
    with pytest.raises(r2.R2OperationError):
        store(FakeClient(post_head_error=RuntimeError("head failed"))).put_document_if_absent("x", RHP_PDF, DIGEST, doc_type="rhp")


def test_post_put_missing_head_fails():
    fake = FakeClient()
    fake.put_object = lambda **kwargs: fake.puts.append(kwargs)
    with pytest.raises(r2.R2ContractError, match="missing"):
        store(fake).put_document_if_absent("x", RHP_PDF, DIGEST, doc_type="rhp")


@pytest.mark.parametrize(
    "field,value",
    [
        ("ContentLength", len(RHP_PDF) + 1),
        ("ContentType", "application/octet-stream"),
        ("Metadata", {}),
        ("Metadata", {"sha256": DIGEST, "contract-version": "2"}),
    ],
)
def test_boto_head_contract_fields_are_required(field, value):
    head = matching_head()
    head[field] = value
    head["ETag"] = DIGEST  # An ETag cannot rescue any failed contract field.
    with pytest.raises(r2.R2ContractError):
        store(FakeClient(head=head)).verify_document("x", DIGEST, len(RHP_PDF), head)


def test_metadata_keys_are_normalized_deliberately():
    head = matching_head()
    head["Metadata"] = {"SHA256": DIGEST, "Contract-Version": contract.CONTRACT_VERSION}
    assert store(FakeClient(head=head)).verify_document("x", DIGEST, len(RHP_PDF), head)


def test_missing_credentials_in_production_fails(monkeypatch):
    for name in (*r2._CREDENTIAL_NAMES, "R2_DOCUMENT_BUCKET", *r2._LEGACY_BUCKET_NAMES):
        monkeypatch.delenv(name, raising=False)
    r2._client.cache_clear()
    with pytest.raises(r2.R2ConfigurationError):
        r2.R2DocumentStore()


def test_injected_fake_client_needs_no_credentials(monkeypatch):
    for name in r2._CREDENTIAL_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert store(FakeClient(head=matching_head())).document_exists("x")


def test_legacy_bucket_fallback_warns_without_value():
    env = {"R2_BUCKET_RHP": "secret-bucket-name"}
    with pytest.warns(FutureWarning) as caught:
        assert r2.document_bucket(env) == "secret-bucket-name"
    assert "secret-bucket-name" not in str(caught[0].message)


def test_secrets_are_redacted():
    message = contract.redact_diagnostic(
        "access_key=abc password=hunter2 opaque-secret",
        {"credential": "opaque-secret"},
    )
    assert "abc" not in message and "hunter2" not in message and "opaque-secret" not in message


def test_no_production_delete_method_or_normal_delete_call_path():
    assert not hasattr(r2.R2DocumentStore, "delete_document")
    assert not hasattr(r2, "delete_document")
    assert not hasattr(r2, "delete_url")
    for path in [ROOT / "pipeline" / "cron.py", ROOT / "pipeline" / "drive.py", ROOT / "pipeline" / "fill_v2.py"]:
        source = path.read_text(encoding="utf-8")
        assert ".delete_document(" not in source
        assert ".delete_object(" not in source
        assert "delete_url(" not in source


def test_public_wrangler_has_no_r2_binding_or_credentials():
    raw = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    config = json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))
    assert "r2_buckets" not in config
    serialized = json.dumps(config).upper()
    assert "R2_ACCESS_KEY_ID" not in serialized
    assert "R2_SECRET_ACCESS_KEY" not in serialized


def test_supported_import_modes_and_cron_entrypoint():
    commands = [
        (ROOT, "import pipeline.document_contract; import pipeline.r2"),
        (ROOT / "pipeline", "import document_contract; import r2"),
    ]
    for cwd, source in commands:
        result = subprocess.run(
            [sys.executable, "-c", source], cwd=cwd, text=True, capture_output=True
        )
        assert result.returncode == 0, result.stderr
    for cwd, script in [(ROOT, "pipeline/cron.py"), (ROOT / "pipeline", "cron.py")]:
        result = subprocess.run(
            [sys.executable, script, "--help"], cwd=cwd, text=True, capture_output=True
        )
        assert result.returncode == 0, result.stderr


def test_legacy_put_document_caller_map_is_explicit():
    callers = []
    for path in (ROOT / "pipeline").glob("*.py"):
        if path.name in {"r2.py", "test_r2.py"}:
            continue
        if "r2.put_document(" in path.read_text(encoding="utf-8"):
            callers.append(path.relative_to(ROOT).as_posix())
    assert callers == ["pipeline/fill_v2.py"]


class ProbeClient:
    def __init__(self, *, get_error=None):
        self.events = []
        self.object = None
        self.get_error = get_error

    def head_object(self, **kwargs):
        self.events.append("HEAD")
        if self.object is None:
            raise NotFound()
        return {
            "ContentLength": len(self.object["Body"]),
            "ContentType": self.object["ContentType"],
            "Metadata": self.object["Metadata"],
        }

    def put_object(self, **kwargs):
        self.events.append("PUT")
        assert kwargs["IfNoneMatch"] == "*"
        self.object = kwargs

    def get_object(self, **kwargs):
        self.events.append("GET")
        if self.get_error:
            raise self.get_error
        return {"Body": io.BytesIO(self.object["Body"])}

    def delete_object(self, **kwargs):
        self.events.append("DELETE")
        self.object = None


PROBE_ENV = {
    "R2_DOCUMENT_BUCKET": "private-test-bucket",
    "R2_ACCOUNT_ID": "private-account",
    "R2_ACCESS_KEY_ID": "private-access-key",
    "R2_SECRET_ACCESS_KEY": "private-secret",
}


def test_probe_without_confirmation_makes_zero_client_calls():
    calls = []
    code, result = probe.run_probe([], env=PROBE_ENV, client_factory=lambda env: calls.append(env))
    assert code != 0 and result["status"] == "confirmation-required"
    assert calls == []


def test_probe_missing_variable_makes_zero_client_calls():
    calls = []
    env = dict(PROBE_ENV)
    env.pop("R2_SECRET_ACCESS_KEY")
    code, result = probe.run_probe(
        ["--confirm-test-probe"], env=env, client_factory=lambda values: calls.append(values)
    )
    assert code != 0 and result["status"] == "configuration-missing"
    assert calls == []


def test_probe_success_sequence_and_safe_output():
    client = ProbeClient()
    code, result = probe.run_probe(
        ["--confirm-test-probe"], env=PROBE_ENV, client_factory=lambda values: client
    )
    assert code == 0
    assert result["key"].startswith("test/pr303/")
    assert client.events == ["HEAD", "PUT", "HEAD", "GET", "DELETE", "HEAD"]
    assert result["class_a_operations"] == 2
    assert result["class_b_operations"] == 4
    assert result["put_conditional"] and result["head_verified"]
    assert result["get_sha_verified"] and result["cleanup_verified"]
    output = json.dumps(result)
    assert set(result) == {
        "status", "key", "uploaded_bytes", "class_a_operations", "class_b_operations",
        "put_conditional", "head_verified", "get_sha_verified", "cleanup_verified", "runtime_ms",
    }
    assert not any(value in output for value in PROBE_ENV.values())


@pytest.mark.parametrize("key", ["rhp/x.pdf", "sbi/x.pdf", "test/pr303/not-generated/x.pdf"])
def test_probe_cleanup_rejects_non_generated_or_production_key(key):
    client = ProbeClient()
    with pytest.raises(ValueError, match="cleanup refused"):
        probe._safe_cleanup(client, "bucket", key, "test/pr303/" + "a" * 32 + "/" + "b" * 64 + ".pdf")
    assert client.events == []


def test_probe_does_not_accept_a_caller_supplied_prefix():
    with pytest.raises(SystemExit):
        probe.run_probe(
            ["--confirm-test-probe", "--prefix", "rhp/"],
            env=PROBE_ENV,
            client_factory=lambda values: pytest.fail("client must not be created"),
        )


def test_probe_failed_get_attempts_exact_test_cleanup_and_redacts():
    error = RuntimeError(" ".join(PROBE_ENV.values()))
    client = ProbeClient(get_error=error)
    code, result = probe.run_probe(
        ["--confirm-test-probe"], env=PROBE_ENV, client_factory=lambda values: client
    )
    assert code != 0
    assert client.events == ["HEAD", "PUT", "HEAD", "GET", "DELETE", "HEAD"]
    assert result["cleanup_verified"]
    output = json.dumps(result)
    assert not any(value in output for value in PROBE_ENV.values())


def test_probe_introduces_no_production_delete_api():
    assert not hasattr(r2.R2DocumentStore, "delete_document")
    assert not hasattr(r2.R2DocumentStore, "delete")
    assert not hasattr(r2, "delete_url")
