#!/usr/bin/env python3
"""Docs-cleanup contract tests (2026-07-20). Offline.

Guards the documentation single-source-of-truth:
  * docs/AACAPITAL_PRODUCT_CONTRACT.md exists, is marked AUTHORITATIVE, and
    carries the required sections + the locked MID 4-15 rule + rejected register
  * every file in docs/archive/ carries the ARCHIVED header pointing at the contract
  * README is IPO-only (no equity-era "200 equities"/AMFI claims) and links the contract
  * every non-archived tracked .md carries a Status: line
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DOCS = os.path.join(REPO, "docs")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def test_contract_exists_and_is_authoritative():
    p = os.path.join(DOCS, "AACAPITAL_PRODUCT_CONTRACT.md")
    assert os.path.exists(p)
    src = _read(p)
    assert "AUTHORITATIVE" in src
    for section in ("Product mission", "Product flow", "Non-goals",
                    "Approved scoring systems", "Approved data sources",
                    "Locked rules", "Rejected-factor register",
                    "Documentation authority"):
        assert section in src, f"contract missing section: {section}"
    assert "MID 4–15%" in src or "MID 4-15%" in src, "locked core trade missing"
    assert "n≥30" in src, "signal bar missing"
    assert "LQI" in src and "CIR" in src, "rejected register incomplete"


def test_archived_docs_carry_header():
    arch = os.path.join(DOCS, "archive")
    files = [f for f in os.listdir(arch) if f.endswith(".md")]
    assert files, "docs/archive must not be empty"
    for f in files:
        head = _read(os.path.join(arch, f))[:400]
        assert "ARCHIVED DOCUMENT" in head and "AACAPITAL_PRODUCT_CONTRACT.md" in head, \
            f"{f} missing the archive header"


def test_readme_is_ipo_only_and_links_contract():
    src = _read(os.path.join(REPO, "README.md"))
    assert "AACAPITAL_PRODUCT_CONTRACT.md" in src
    for stale in ("200 Indian equities", "AMFI liquidity scoring",
                  "commentary scoring engine", "Intelligence Layer — Complete Pack"):
        assert stale not in src, f"equity-era claim back in README: {stale}"
    assert "IPO-only" in src


def test_every_tracked_md_has_status():
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=REPO,
                         capture_output=True, text=True).stdout.split()
    missing = []
    for rel in out:
        # pipeline/ docs came in with the merged pipeline repo (#283) and follow their own
        # convention (no app "Status:" header). Exclude them from the app doc-stamp rule.
        if (rel.startswith("docs/archive/") or "/archive/" in rel or rel.startswith("_archive/")
                or rel.startswith("pipeline/")):
            continue
        head = _read(os.path.join(REPO, rel))[:200]
        if "Status:" not in head and "AUTHORITATIVE" not in head:
            missing.append(rel)
    assert not missing, f"docs without Status header: {missing}"
