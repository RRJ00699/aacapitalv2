# R2 immutable document contract

**Status:** PR A implements the client and object contract only. It does not activate
download, ledger, extraction, or SBI workflow cutovers.

## Ownership and security

- Cloudflare R2 Standard bucket: `aacapital-ipo-documents` (private).
- `R2_DOCUMENT_BUCKET` is the reviewed bucket variable. `R2_BUCKET_RHP` and
  `R2_BUCKET_SBI` are warning-emitting compatibility fallbacks only and must resolve to
  the same bucket when both exist.
- The Python pipeline uses S3-compatible credentials scoped to object read/write in
  this bucket. Bucket administration, lifecycle administration, and public access are
  neither required nor permitted by this application contract.
- The public Next.js Worker receives no R2 binding or credential. Secrets must remain
  in the pipeline secret store and must not appear in logs, exceptions, or URLs.
- Neon remains authoritative for metadata, ownership, state, and extraction ledger.

## Immutable object format

R2 stores PDF bytes permanently. Normal production flows have no delete operation and
must never overwrite a mismatching object. Keys are:

```text
rhp/<ISIN>/<YYYY-MM-DD>/<sha256>.pdf
sbi/<ISIN>/<YYYY-MM-DD>/<sha256>.pdf
<type>/unresolved-ipo-<ipo_id>/<YYYY-MM-DD>/<sha256>.pdf
```

ISIN must come from authoritative metadata; it is never inferred from a company name,
slug, filename, or upstream URL. Document dates are strict calendar dates. SHA-256 is
64 lowercase hexadecimal characters. Stored metadata is limited to `sha256` and
`contract-version=1`; it contains no company or upstream filename.

The accepted PDF size range is 100 KiB–100 MiB for RHP and 10 KiB–100 MiB for SBI.
The expected content type is `application/pdf`.

## Request and failure behavior

An attempted upload performs one HEAD. A matching existing object stops there (one
Class B operation and no Class A operation). A missing object performs PUT followed by
a second HEAD (one Class A and two Class B operations). Verification checks key,
content length, content type, SHA-256 metadata, and contract version. ETag is never
treated as a digest. Any mismatch, PUT failure, post-PUT HEAD failure, or missing
production configuration fails closed.

No live integration probe is part of PR A. An owner-approved probe must use only a test
prefix and a tiny valid PDF, and its test-only cleanup must not be available to normal
document flows.

## Activation and rollback

PR B must add/reconcile the Neon ledger fields, backfill reviewed rows, and migrate the
current `fill_v2.put_document` and download callers to the new key-based methods. Until
then the pre-cutover uploader remains explicitly marked as compatibility behavior and
does not activate this contract.

Rollback PR A by reverting its commit. It creates no database or R2 state, changes no
Worker binding, and uploads no object, so no data rollback or object deletion is needed.
