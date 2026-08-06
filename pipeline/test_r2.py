"""Unit and structural tests for the immutable R2 document contract."""

from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import re

import pytest

import document_contract as contract
import r2


DIGEST = "a" * 64
ROOT = Path(__file__).resolve().parents[1]


class NotFound(Exception):
    response = {"ResponseMetadata": {"HTTPStatusCode": 404}, "Error": {"Code": "NoSuchKey"}}


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
        self.head = matching_head(len(kwargs["Body"]), kwargs["Metadata"]["sha256"])

    def get_object(self, **kwargs):
        return {"Body": io.BytesIO(b"pdf")}


def matching_head(size=3, digest=DIGEST):
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
    assert store(fake).put_document_if_absent("rhp/x", b"pdf", DIGEST).startswith("r2://")
    assert fake.puts == []


@pytest.mark.parametrize("head", [matching_head(4), matching_head(3, "b" * 64)])
def test_existing_mismatching_object_fails_closed(head):
    fake = FakeClient(head=head)
    with pytest.raises(r2.R2ContractError):
        store(fake).put_document_if_absent("rhp/x", b"pdf", DIGEST)
    assert fake.puts == []


def test_missing_object_puts_then_heads_and_verifies():
    fake = FakeClient()
    store(fake).put_document_if_absent("rhp/x", b"pdf", DIGEST)
    assert len(fake.puts) == 1
    assert fake.heads == 2
    assert fake.puts[0]["ContentType"] == "application/pdf"
    assert fake.puts[0]["Metadata"] == contract.object_metadata(DIGEST)


def test_put_failure_fails():
    with pytest.raises(r2.R2OperationError):
        store(FakeClient(put_error=RuntimeError("failed"))).put_document_if_absent("x", b"pdf", DIGEST)


def test_post_put_head_failure_fails():
    with pytest.raises(r2.R2OperationError):
        store(FakeClient(post_head_error=RuntimeError("head failed"))).put_document_if_absent("x", b"pdf", DIGEST)


def test_post_put_missing_head_fails():
    fake = FakeClient()
    fake.put_object = lambda **kwargs: fake.puts.append(kwargs)
    with pytest.raises(r2.R2ContractError, match="missing"):
        store(fake).put_document_if_absent("x", b"pdf", DIGEST)


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
