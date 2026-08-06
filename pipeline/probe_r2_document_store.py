#!/usr/bin/env python3
"""Owner-run, one-object R2 probe. This module is never imported by production flows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from typing import Any, Callable, Mapping

if __package__:
    from .document_contract import CONTRACT_VERSION, PDF_CONTENT_TYPE, object_metadata, redact_diagnostic
else:
    from document_contract import CONTRACT_VERSION, PDF_CONTENT_TYPE, object_metadata, redact_diagnostic


REQUIRED_ENV = (
    "R2_DOCUMENT_BUCKET",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)
_TEST_KEY_RE = re.compile(r"^test/pr303/[0-9a-f]{32}/[0-9a-f]{64}\.pdf$")


def _fixture() -> bytes:
    """Return a small generated PDF for this isolated probe, not production validation."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )


def _client(values: Mapping[str, str]):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"https://{values['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=values["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=values["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = str(response.get("Error", {}).get("Code", ""))
    return status == 404 or code in {"404", "NoSuchKey", "NotFound"}


def _head(client: Any, bucket: str, key: str):
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if _not_found(exc):
            return None
        raise


def _verify_head(head: Mapping[str, Any] | None, size: int, digest: str) -> bool:
    if head is None:
        return False
    metadata = {str(key).lower(): str(value) for key, value in head.get("Metadata", {}).items()}
    return (
        head.get("ContentLength") == size
        and head.get("ContentType") == PDF_CONTENT_TYPE
        and metadata.get("sha256") == digest
        and metadata.get("contract-version") == CONTRACT_VERSION
    )


def _safe_cleanup(client: Any, bucket: str, key: str, generated_key: str) -> None:
    """Delete only the exact internally generated PR #303 test object."""
    if key != generated_key or not _TEST_KEY_RE.fullmatch(key):
        raise ValueError("cleanup refused: key is not the generated PR #303 test key")
    client.delete_object(Bucket=bucket, Key=key)


def _summary(status: str, key: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "key": key,
        "uploaded_bytes": 0,
        "class_a_operations": 0,
        "class_b_operations": 0,
        "put_conditional": False,
        "head_verified": False,
        "get_sha_verified": False,
        "cleanup_verified": False,
        "runtime_ms": 0,
    }


def run_probe(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[[Mapping[str, str]], Any] = _client,
    uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int, dict[str, Any]]:
    parser = argparse.ArgumentParser(description="Run one isolated PR #303 R2 test object probe")
    parser.add_argument("--confirm-test-probe", action="store_true")
    args = parser.parse_args(argv)
    result = _summary("confirmation-required")
    if not args.confirm_test_probe:
        return 2, result

    values = os.environ if env is None else env
    missing = [name for name in REQUIRED_ENV if not values.get(name)]
    if missing:
        result["status"] = "configuration-missing"
        return 2, result

    payload = _fixture()
    digest = hashlib.sha256(payload).hexdigest()
    key = f"test/pr303/{uuid_factory().hex}/{digest}.pdf"
    result["key"] = key
    bucket = values["R2_DOCUMENT_BUCKET"]
    secrets = {name: values[name] for name in REQUIRED_ENV}
    started = clock()
    client = client_factory(values)
    put_attempted = False
    cleanup_attempted = False
    try:
        result["class_b_operations"] += 1
        if _head(client, bucket, key) is not None:
            raise RuntimeError("generated test key unexpectedly exists")

        put_attempted = True
        result["class_a_operations"] += 1
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=payload,
            ContentType=PDF_CONTENT_TYPE,
            Metadata=object_metadata(digest),
            IfNoneMatch="*",
        )
        result["put_conditional"] = True
        result["uploaded_bytes"] = len(payload)

        result["class_b_operations"] += 1
        head = _head(client, bucket, key)
        if not _verify_head(head, len(payload), digest):
            raise RuntimeError("post-PUT HEAD contract verification failed")
        result["head_verified"] = True

        result["class_b_operations"] += 1
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        downloaded = body.read() if hasattr(body, "read") else bytes(body)
        if hashlib.sha256(downloaded).hexdigest() != digest:
            raise RuntimeError("GET sha256 verification failed")
        result["get_sha_verified"] = True

        cleanup_attempted = True
        result["class_a_operations"] += 1
        _safe_cleanup(client, bucket, key, key)
        result["class_b_operations"] += 1
        if _head(client, bucket, key) is not None:
            raise RuntimeError("cleanup HEAD found the test object")
        result["cleanup_verified"] = True
        result["status"] = "ok"
        return 0, result
    except Exception as exc:
        result["status"] = "failed: " + redact_diagnostic(exc, secrets)
        if put_attempted and not cleanup_attempted:
            try:
                result["class_a_operations"] += 1
                _safe_cleanup(client, bucket, key, key)
                result["class_b_operations"] += 1
                result["cleanup_verified"] = _head(client, bucket, key) is None
            except Exception:
                result["cleanup_verified"] = False
        return 1, result
    finally:
        result["runtime_ms"] = max(0, round((clock() - started) * 1000))


def main(argv: list[str] | None = None) -> int:
    code, result = run_probe(argv)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
