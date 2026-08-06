"""Fail-closed Cloudflare R2 client for immutable PDF document objects.

The public Worker has no R2 binding.  This module is for the Python pipeline and
expects bucket-scoped S3-compatible object read/write credentials.
"""

from __future__ import annotations

import functools
import os
import warnings
from typing import Any

if __package__:
    from .document_contract import (
        CONTRACT_VERSION,
        PDF_CONTENT_TYPE,
        object_metadata,
        redact_diagnostic,
        validate_pdf_source,
        validate_sha256,
    )
else:
    from document_contract import (
        CONTRACT_VERSION,
        PDF_CONTENT_TYPE,
        object_metadata,
        redact_diagnostic,
        validate_pdf_source,
        validate_sha256,
    )


_CREDENTIAL_NAMES = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
_LEGACY_BUCKET_NAMES = ("R2_BUCKET_RHP", "R2_BUCKET_SBI")


class R2ConfigurationError(RuntimeError):
    pass


class R2ContractError(RuntimeError):
    pass


class R2OperationError(RuntimeError):
    pass


def configured() -> bool:
    return all(os.environ.get(name) for name in _CREDENTIAL_NAMES) and bool(document_bucket())


def document_bucket(env: dict[str, str] | None = None) -> str | None:
    values = os.environ if env is None else env
    if values.get("R2_DOCUMENT_BUCKET"):
        return values["R2_DOCUMENT_BUCKET"]
    present = [name for name in _LEGACY_BUCKET_NAMES if values.get(name)]
    if present:
        buckets = {values[name] for name in present}
        if len(buckets) != 1:
            raise R2ConfigurationError("legacy R2 bucket variables disagree")
        warnings.warn(
            "legacy R2 bucket environment variable used; configure R2_DOCUMENT_BUCKET",
            FutureWarning,
            stacklevel=2,
        )
        return buckets.pop()
    return None


@functools.lru_cache(maxsize=1)
def _client():
    missing = [name for name in _CREDENTIAL_NAMES if not os.environ.get(name)]
    if missing:
        raise R2ConfigurationError("R2 credentials are not configured")
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = str(response.get("Error", {}).get("Code", ""))
    return status == 404 or code in {"404", "NoSuchKey", "NotFound"}


def _is_precondition_conflict(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = str(response.get("Error", {}).get("Code", ""))
    return status in {409, 412} or code in {
        "409",
        "412",
        "ConditionalRequestConflict",
        "PreconditionFailed",
    }


class R2DocumentStore:
    """Immutable document operations. There is intentionally no delete method."""

    def __init__(self, *, client: Any | None = None, bucket: str | None = None):
        self.bucket = bucket or document_bucket()
        if not self.bucket:
            raise R2ConfigurationError("R2_DOCUMENT_BUCKET is not configured")
        self.client = client if client is not None else _client()

    def head_document(self, key: str) -> dict[str, Any] | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise R2OperationError(redact_diagnostic(exc, _secret_values())) from None

    def verify_document(self, key: str, sha256: str, size: int, head: dict[str, Any] | None = None) -> dict[str, Any]:
        digest = validate_sha256(sha256)
        result = self.head_document(key) if head is None else head
        if result is None:
            raise R2ContractError("document object is missing")
        metadata = {str(k).lower(): str(v) for k, v in result.get("Metadata", {}).items()}
        checks = {
            "key": result.get("Key", key) == key,
            "content length": result.get("ContentLength") == size,
            "content type": result.get("ContentType") == PDF_CONTENT_TYPE,
            "sha256 metadata": metadata.get("sha256") == digest,
            "contract version": metadata.get("contract-version") == CONTRACT_VERSION,
        }
        failed = [name for name, valid in checks.items() if not valid]
        if failed:
            raise R2ContractError("document object contract mismatch: " + ", ".join(failed))
        return result

    def put_document_if_absent(
        self,
        key: str,
        content,
        sha256: str,
        *,
        doc_type: str,
        content_type: str = PDF_CONTENT_TYPE,
    ) -> str:
        # Local validation precedes HEAD so invalid input performs zero R2 operations.
        validated = validate_pdf_source(content, doc_type, sha256, content_type=content_type)
        digest = validated.sha256
        existing = self.head_document(key)
        if existing is not None:
            self.verify_document(key, digest, validated.size, existing)
            return f"r2://{self.bucket}/{key}"
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=validated.body,
                ContentType=PDF_CONTENT_TYPE,
                Metadata=object_metadata(digest),
                IfNoneMatch="*",
            )
        except Exception as exc:
            # A concurrent immutable creator may win after our missing HEAD. Conditional
            # PUT prevents overwrite; accept the race only after exact HEAD verification.
            if _is_precondition_conflict(exc):
                self.verify_document(key, digest, validated.size)
                return f"r2://{self.bucket}/{key}"
            raise R2OperationError(redact_diagnostic(exc, _secret_values())) from None
        # A fresh HEAD is mandatory: a successful PUT response is not verification.
        self.verify_document(key, digest, validated.size)
        return f"r2://{self.bucket}/{key}"

    def get_document(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)
        except Exception as exc:
            raise R2OperationError(redact_diagnostic(exc, _secret_values())) from None

    def document_exists(self, key: str) -> bool:
        return self.head_document(key) is not None


def _secret_values() -> dict[str, str]:
    return {name: os.environ.get(name, "") for name in _CREDENTIAL_NAMES}


# Module-level methods keep call sites simple while preserving client injection in tests.
def head_document(key: str, *, store: R2DocumentStore | None = None):
    return (store or R2DocumentStore()).head_document(key)


def put_document_if_absent(key: str, content, sha256: str, *, doc_type: str, content_type: str = PDF_CONTENT_TYPE, store: R2DocumentStore | None = None):
    return (store or R2DocumentStore()).put_document_if_absent(
        key, content, sha256, doc_type=doc_type, content_type=content_type
    )


def verify_document(key: str, sha256: str, size: int, *, store: R2DocumentStore | None = None):
    return (store or R2DocumentStore()).verify_document(key, sha256, size)


def get_document(key: str, *, store: R2DocumentStore | None = None):
    return (store or R2DocumentStore()).get_document(key)


def document_exists(key: str, *, store: R2DocumentStore | None = None) -> bool:
    return (store or R2DocumentStore()).document_exists(key)


# Read compatibility for pre-cutover documents. PR B will move callers to key-based GET.
def parse_url(url: str):
    if not url or not url.startswith("r2://"):
        return None
    bucket, separator, key = url[5:].partition("/")
    return (bucket, key) if bucket and separator and key else None


def get_to_file(url: str, destination: str, *, client: Any | None = None) -> bool:
    parsed = parse_url(url)
    if not parsed:
        return False
    active_client = client if client is not None else _client()
    bucket, key = parsed
    try:
        active_client.download_file(bucket, key, destination)
        return True
    except Exception as exc:
        raise R2OperationError(redact_diagnostic(exc, _secret_values())) from None


def put_document(doc_type: str, sha256: str, content_bytes: bytes):
    """Pre-cutover compatibility entry point used by ``fill_v2``.

    It deliberately does not upload under the new namespace without the identity and
    document date required by the contract. PR B must replace this call with
    ``document_key`` plus ``put_document_if_absent``. Missing configuration retains the
    pre-existing return value until that coordinated cutover.
    """
    warnings.warn(
        "legacy put_document does not activate the R2 document contract; migrate the caller in PR B",
        FutureWarning,
        stacklevel=2,
    )
    if not all(os.environ.get(name) for name in _CREDENTIAL_NAMES):
        return None
    legacy_name = "R2_BUCKET_SBI" if doc_type in {"sbi", "research_note"} else "R2_BUCKET_RHP"
    bucket = os.environ.get(legacy_name)
    if not bucket:
        return None
    key = f"{sha256}.pdf"
    active_client = _client()
    try:
        try:
            active_client.head_object(Bucket=bucket, Key=key)
        except Exception as exc:
            if not _is_not_found(exc):
                raise
            active_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=content_bytes,
                ContentType=PDF_CONTENT_TYPE,
            )
        return f"r2://{bucket}/{key}"
    except Exception as exc:
        raise R2OperationError(redact_diagnostic(exc, _secret_values())) from None
