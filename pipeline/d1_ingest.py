"""Authenticated client for the AACapital D1 ingest Worker.

This is the only persistence seam the production Python pipeline should need after the
Neon cutover.  It exposes domain operations, never arbitrary SQL.  The Worker owns the
D1 binding and schema checks; the VM holds only the Worker URL + one ingest secret.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


class D1IngestError(RuntimeError):
    pass


def fingerprint(*parts: Any) -> str:
    body = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class D1IngestClient:
    base_url: str
    secret: str
    timeout: int = 45

    @classmethod
    def from_env(cls) -> "D1IngestClient":
        url = (os.environ.get("D1_INGEST_URL") or "").strip().rstrip("/")
        secret = (os.environ.get("D1_INGEST_AUTH_SECRET") or "").strip()
        missing = [name for name, value in (("D1_INGEST_URL", url),
                                             ("D1_INGEST_AUTH_SECRET", secret)) if not value]
        if missing:
            raise D1IngestError("missing D1 ingest configuration: " + ", ".join(missing))
        return cls(url, secret)

    def _request(self, path: str, payload: dict[str, Any] | None = None,
                 *, method: str = "POST", retries: int = 2) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.secret}",
            "User-Agent": "aacapital-pipeline/1",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as res:
                    data = json.loads(res.read().decode("utf-8"))
                if not isinstance(data, dict):
                    raise D1IngestError("ingest response was not an object")
                if data.get("ok") is False:
                    raise D1IngestError(str(data.get("error") or "ingest rejected request"))
                return data
            except urllib.error.HTTPError as exc:
                text = exc.read().decode("utf-8", errors="replace")
                # 4xx is a contract/identity failure. Retrying would only duplicate cost/noise.
                if 400 <= exc.code < 500:
                    try:
                        detail = json.loads(text).get("error")
                    except Exception:
                        detail = text[:300]
                    raise D1IngestError(f"ingest HTTP {exc.code}: {detail}") from None
                last = exc
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
        raise D1IngestError(f"ingest unavailable after retries: {type(last).__name__}: {last}")

    def health(self) -> dict[str, Any]:
        return self._request("/health", None, method="GET")

    def resolve_identity(self, *, isin: str | None = None,
                         name_norm: str | None = None) -> dict[str, Any] | None:
        return self._request("/v1/identity/resolve", {"isin": isin, "name_norm": name_norm}).get("row")

    def active_ipos(self, *, limit: int = 20, lookback_days: int = 100) -> list[dict[str, Any]]:
        return list(self._request("/v1/state/active", {"limit": limit, "lookback_days": lookback_days}).get("rows") or [])

    def listing_today(self, *, day: str, limit: int = 10) -> list[dict[str, Any]]:
        return list(self._request("/v1/state/listing-today", {"day": day, "limit": limit}).get("rows") or [])

    def market_ipos(self, *, limit: int = 30) -> list[dict[str, Any]]:
        return list(self._request("/v1/state/market", {"limit": limit}).get("rows") or [])

    def batch(self, ops: Iterable[dict[str, Any]], *, fail_fast: bool = True,
              chunk_size: int = 250) -> list[dict[str, Any]]:
        items = list(ops)
        out: list[dict[str, Any]] = []
        for start in range(0, len(items), chunk_size):
            chunk = items[start:start + chunk_size]
            result = self._request("/v1/ingest/batch", {"ops": chunk, "fail_fast": fail_fast})
            out.extend(result.get("results") or [])
            if result.get("failed") and fail_fast:
                failed = next((row for row in result.get("results", []) if not row.get("ok")), None)
                raise D1IngestError(f"batch failed at source index {start + int((failed or {}).get('index', 0))}: "
                                    f"{(failed or {}).get('error', 'unknown')}")
        return out

    def op(self, operation: dict[str, Any]) -> dict[str, Any]:
        rows = self.batch([operation])
        return (rows[0].get("result") if rows else {}) or {}

    def claim_job(self) -> dict[str, Any] | None:
        return self._request("/v1/jobs/claim", {}).get("job")

    def finish_job(self, job_id: int, *, status: str, exit_code: int | None,
                   error: str | None, log_tail: str | None) -> None:
        self._request("/v1/jobs/finish", {
            "id": job_id, "status": status, "exit_code": exit_code,
            "error": error, "log_tail": log_tail,
        })
