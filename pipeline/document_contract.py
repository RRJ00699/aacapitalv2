"""Pure validation and key helpers for immutable R2 PDF documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any, Mapping


CONTRACT_VERSION = "1"
PDF_CONTENT_TYPE = "application/pdf"
MAX_PDF_BYTES = 100 * 1024 * 1024
_MIN_PDF_BYTES = {"rhp": 100 * 1024, "sbi": 10 * 1024}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")


@dataclass(frozen=True)
class PDFValidationConfig:
    minimum_bytes: int
    maximum_bytes: int = MAX_PDF_BYTES
    content_type: str = PDF_CONTENT_TYPE


def normalize_document_type(value: str) -> str:
    """Return the canonical storage type; only owner-approved types are valid."""
    if not isinstance(value, str) or value.strip().lower() not in _MIN_PDF_BYTES:
        raise ValueError("document type must be 'rhp' or 'sbi'")
    return value.strip().lower()


def validate_isin(value: str | None) -> str | None:
    """Validate an explicitly sourced Indian ISIN; never derive identity from names."""
    if value is None:
        return None
    if not isinstance(value, str) or not _ISIN_RE.fullmatch(value.strip().upper()):
        raise ValueError("invalid ISIN")
    return value.strip().upper()


def unresolved_identity(ipo_id: int) -> str:
    if isinstance(ipo_id, bool) or not isinstance(ipo_id, int) or ipo_id <= 0:
        raise ValueError("ipo_id must be a positive integer")
    return f"unresolved-ipo-{ipo_id}"


def normalize_document_date(value: date | datetime | str) -> str:
    """Normalize a strict calendar date (YYYY-MM-DD), rejecting datetime strings."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("document date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("invalid document date") from exc


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
    return value


def document_key(
    doc_type: str,
    sha256: str,
    document_date: date | datetime | str,
    *,
    isin: str | None = None,
    ipo_id: int | None = None,
) -> str:
    """Build an immutable key without filenames, slugs, or company names."""
    kind = normalize_document_type(doc_type)
    digest = validate_sha256(sha256)
    identity = validate_isin(isin)
    if identity is None:
        if ipo_id is None:
            raise ValueError("an ISIN or unresolved ipo_id is required")
        identity = unresolved_identity(ipo_id)
    return f"{kind}/{identity}/{normalize_document_date(document_date)}/{digest}.pdf"


def pdf_validation_config(doc_type: str) -> PDFValidationConfig:
    kind = normalize_document_type(doc_type)
    return PDFValidationConfig(minimum_bytes=_MIN_PDF_BYTES[kind])


def object_metadata(sha256: str) -> dict[str, str]:
    """Return the complete, non-secret metadata written to each object."""
    return {"sha256": validate_sha256(sha256), "contract-version": CONTRACT_VERSION}


def redact_diagnostic(value: Any, secrets: Mapping[str, str] | None = None) -> str:
    """Render an operational diagnostic while removing known credentials/tokens."""
    text = str(value)
    for secret in (secrets or {}).values():
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)(access[_-]?key|secret[_-]?access[_-]?key|token|password)(\s*[=:]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        text,
    )
    return text
