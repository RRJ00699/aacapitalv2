#!/usr/bin/env python3
"""Guard: wrangler.jsonc must never contain a placeholder binding id.

2026-07-18 INCIDENT: a `CACHE` KV binding was merged with the literal id
`PLACEHOLDER_CACHE_NS_ID`. Cloudflare rejected every deploy with
"KV namespace 'PLACEHOLDER_CACHE_NS_ID' is not valid [code: 10042]" — production
deploys were broken until the binding was removed. Nothing in CI caught it
because wrangler.jsonc is never type-checked or executed in tests.
"""
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

PLACEHOLDER_TOKENS = ("PLACEHOLDER", "TODO", "CHANGEME", "XXXX", "your-", "<")


def _load_wrangler():
    raw = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    stripped = re.sub(r"^\s*//.*$", "", raw, flags=re.M)   # JSONC line comments
    return json.loads(stripped)


def test_wrangler_is_valid_json():
    _load_wrangler()


def test_no_placeholder_ids_in_bindings():
    """A placeholder id fails the DEPLOY, not the build — so it must fail here."""
    cfg = _load_wrangler()
    bad = []
    for ns in cfg.get("kv_namespaces", []):
        ident = str(ns.get("id", ""))
        if any(tok.lower() in ident.lower() for tok in PLACEHOLDER_TOKENS):
            bad.append(f"{ns.get('binding')}={ident}")
    for key in ("d1_databases", "r2_buckets", "queues"):
        for b in cfg.get(key, []) or []:
            blob = json.dumps(b)
            if any(tok.lower() in blob.lower() for tok in PLACEHOLDER_TOKENS):
                bad.append(f"{key}:{blob[:60]}")
    assert not bad, f"placeholder binding id(s) would break deploy: {bad}"


def test_kv_ids_look_like_real_namespace_ids():
    """Cloudflare KV namespace ids are 32-char hex."""
    cfg = _load_wrangler()
    for ns in cfg.get("kv_namespaces", []):
        ident = str(ns.get("id", ""))
        assert re.fullmatch(r"[0-9a-f]{32}", ident), \
            f"{ns.get('binding')} id is not a 32-char hex namespace id: {ident!r}"
