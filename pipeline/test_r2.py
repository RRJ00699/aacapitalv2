#!/usr/bin/env python3
"""Unit tests for r2.py — no network, no creds, no DB.

Covers key/url derivation, url parsing, and no-op degradation when R2 is
unconfigured. Importing this module must be side-effect safe for pytest
collection; executable behavior is kept under __main__.
"""
import os


def run_checks():
    # ensure a clean, cred-free environment for the no-op assertions
    for _k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        os.environ.pop(_k, None)
    os.environ["R2_BUCKET_RHP"] = "aac-rhp"
    os.environ["R2_BUCKET_SBI"] = "aac-sbi"

    import r2
    r2._client.cache_clear()

    ok = True

    def chk(m, c):
        nonlocal ok
        ok = ok and c
        print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    chk("configured() False without creds", r2.configured() is False)
    chk("key_for(sha) == '<sha>.pdf'", r2.key_for("abc123") == "abc123.pdf")

    chk("url_for rhp uses the RHP bucket", r2.url_for("rhp", "deadbeef") == "r2://aac-rhp/deadbeef.pdf")
    chk("url_for sbi uses the SBI bucket", r2.url_for("sbi", "deadbeef") == "r2://aac-sbi/deadbeef.pdf")
    chk("research_note maps to the SBI (retained) bucket", r2.url_for("research_note", "x") == "r2://aac-sbi/x.pdf")

    chk("parse_url round-trips", r2.parse_url("r2://aac-rhp/deadbeef.pdf") == ("aac-rhp", "deadbeef.pdf"))
    chk("parse_url rejects a non-r2 url", r2.parse_url("https://x/y.pdf") is None)
    chk("parse_url rejects a bucket-only url", r2.parse_url("r2://onlybucket") is None)

    # no-op degradation without creds (the laptop local-only path)
    chk("put_document -> None (no creds)", r2.put_document("rhp", "abc", b"bytes") is None)
    chk("get_to_file -> False (no creds)", r2.get_to_file("r2://b/k.pdf", "unused.pdf") is False)
    chk("delete_url -> False (no creds)", r2.delete_url("r2://b/k.pdf") is False)

    print(f"\n{'ALL PASS' if ok else 'SOME FAILED'}")
    return ok


def test_r2_contract():
    assert run_checks()


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_checks() else 1)
