#!/usr/bin/env python3
"""r2.py — Cloudflare R2 document store (S3-compatible), content-addressed by sha256.

Two buckets by LIFECYCLE (point 3): RHPs are transient (a 180-day R2 lifecycle backstop
plus the app's post-lock-in purge), SBI notes are retained because the UI shows them.
Keeping them in separate buckets is what lets each carry its own lifecycle policy —
prefixes could not express "purge RHPs, never touch SBI notes".

The object key IS the sha256 (`<sha256>.pdf`), so the dedup key doubles as the R2 key and
`documents.url` stores `r2://<bucket>/<sha256>.pdf`.

DEGRADES TO NO-OP when creds are absent: every function returns None/False rather than
raising, so a laptop run with no R2 configured still works entirely local-only.

Env (set in .env locally; GitHub Actions secrets/vars):
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_RHP, R2_BUCKET_SBI
"""
import os, functools

# doc_type -> which bucket env var. "sbi"/"research_note" share the retained bucket.
_BUCKET_ENV = {"rhp": "R2_BUCKET_RHP", "sbi": "R2_BUCKET_SBI", "research_note": "R2_BUCKET_SBI"}


def configured() -> bool:
    return all(os.environ.get(k) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))


def _bucket(doc_type: str):
    return os.environ.get(_BUCKET_ENV.get(doc_type, "R2_BUCKET_RHP"))


def key_for(sha256: str) -> str:
    return f"{sha256}.pdf"


def url_for(doc_type: str, sha256: str):
    b = _bucket(doc_type)
    return f"r2://{b}/{key_for(sha256)}" if b else None


def parse_url(url):
    """r2://<bucket>/<key> -> (bucket, key), or None."""
    if not url or not url.startswith("r2://"):
        return None
    bucket, _, key = url[len("r2://"):].partition("/")
    return (bucket, key) if bucket and key else None


@functools.lru_cache(maxsize=1)
def _client():
    if not configured():
        return None
    import boto3  # imported only when creds exist, so no hard dep on the laptop local path
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def exists(bucket, key) -> bool:
    c = _client()
    if not c or not bucket:
        return False
    try:
        c.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def put_document(doc_type: str, sha256: str, content_bytes: bytes):
    """Upload once (skipped if already present). Returns the r2:// url, or None if R2 is
    not configured / the upload failed (the data is already in the DB, so a storage hiccup
    must never break the pipeline)."""
    c = _client(); bucket = _bucket(doc_type)
    if not c or not bucket:
        return None
    key = key_for(sha256)
    try:
        if not exists(bucket, key):
            c.put_object(Bucket=bucket, Key=key, Body=content_bytes, ContentType="application/pdf")
        return url_for(doc_type, sha256)
    except Exception as e:
        print(f"  [r2] put failed for {doc_type}/{sha256[:12]}: {type(e).__name__}: {str(e)[:80]}")
        return None


def get_to_file(url, dest_path) -> bool:
    """Fetch r2://bucket/key to dest_path. Returns True on success."""
    c = _client(); pu = parse_url(url)
    if not c or not pu:
        return False
    bucket, key = pu
    try:
        c.download_file(bucket, key, dest_path)
        return True
    except Exception as e:
        print(f"  [r2] get failed for {url}: {type(e).__name__}: {str(e)[:80]}")
        return False


def delete_url(url) -> bool:
    c = _client(); pu = parse_url(url)
    if not c or not pu:
        return False
    bucket, key = pu
    try:
        c.delete_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False
