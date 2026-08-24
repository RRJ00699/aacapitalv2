#!/usr/bin/env python3
"""SEBI RHP + SBI note document/extraction lane for D1.

RHP and SBI PDFs are retained in immutable R2.  Anchor PDFs are intentionally NOT
handled here: the anchor lane downloads, extracts facts, and discards the PDF bytes per
owner policy.  Paid extraction is guarded by D1 (sha256 + model + prompt version) before
any Anthropic call.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from decimal import Decimal
from typing import Any

import pymupdf

from d1_extraction_routes import rhp_ops, sbi_ops
from d1_ingest import D1IngestClient
from document_contract import PDF_CONTENT_TYPE, document_key
from fill_ipo import _norm
from r2 import R2DocumentStore

ROOT = pathlib.Path(__file__).resolve().parents[1]
RHP_MANIFEST = ROOT / "download_manifest.json"
RHP_DIR = ROOT / "rhps"
SBI_DIR_DEFAULT = pathlib.Path(os.environ.get("RUNNER_TEMP", ROOT / ".tmp")) / "sbi-notes"


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _page_count(body: bytes) -> int:
    with pymupdf.open(stream=body, filetype="pdf") as doc:
        return len(doc)


def _resolve(client: D1IngestClient, *, name: str | None = None, isin: str | None = None):
    return client.resolve_identity(isin=isin, name_norm=_norm(name or "") if name else None)


def _store_r2_and_ledger(*, client: D1IngestClient, store: R2DocumentStore,
                         body: bytes, ipo: dict[str, Any], doc_type: str,
                         source_url: str | None, document_date: str):
    digest = _sha(body)
    key = document_key(doc_type, digest, document_date,
                       isin=ipo.get("isin"), ipo_id=int(ipo["id"]))
    store.put_document_if_absent(key, body, digest, doc_type=doc_type,
                                 content_type=PDF_CONTENT_TYPE)
    pages = _page_count(body)
    client.op({
        "op": "document_upsert", "sha256": digest, "ipo_id": int(ipo["id"]),
        "doc_type": doc_type, "source_url": source_url, "size_bytes": len(body),
        "page_count": pages, "r2_key": key, "fetched_at": _utcnow(),
    })
    return digest, key, pages


def run_sebi_download(*, max_rhps: int = 4):
    cmd = [sys.executable, str(ROOT / "_scripts" / "download_sebi_rhps_playwright.py"),
           "--max", str(max_rhps)]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, errors="replace",
                          timeout=2400)


def _rhp_records():
    if not RHP_MANIFEST.exists():
        return []
    manifest = json.loads(RHP_MANIFEST.read_text(encoding="utf-8"))
    out = []
    for url, rec in (manifest.get("filings") or {}).items():
        if rec.get("status") != "ok" or not rec.get("path"):
            continue
        path = (ROOT / rec["path"]).resolve() if not pathlib.Path(rec["path"]).is_absolute() else pathlib.Path(rec["path"])
        if path.exists():
            out.append((url, rec, path))
    # most recently downloaded first; missing timestamp sorts last
    out.sort(key=lambda x: str(x[1].get("downloaded_at") or ""), reverse=True)
    return out


def _extract_rhp(*, client: D1IngestClient, ipo: dict[str, Any], body: bytes,
                 document_sha256: str, company: str):
    from rhp_sections import gather_sections
    import rhp_sonnet

    guard = client.extraction_state(document_sha256=document_sha256,
                                    model=rhp_sonnet.MODEL,
                                    prompt_version=rhp_sonnet.PROMPT_VERSION)
    if guard.get("extracted"):
        return {"status": "ALREADY_EXTRACTED", "cost_usd": 0.0, "ops": 0}
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    with pymupdf.open(stream=body, filetype="pdf") as doc:
        pages = [(i + 1, doc[i].get_text()) for i in range(len(doc))]
    sections = gather_sections(pages)
    if not sections:
        raise RuntimeError("no targeted RHP sections located")
    prompt = rhp_sonnet.build_prompt(company, sections)
    raw, itok, otok = rhp_sonnet.call_sonnet(rhp_sonnet.SYSTEM, prompt, key)
    data = rhp_sonnet.parse_json(raw)
    if not isinstance(data, dict) or "structured" not in data:
        raise RuntimeError("RHP Sonnet response missing structured block")
    cost = itok * rhp_sonnet.IN_RATE + otok * rhp_sonnet.OUT_RATE
    observed = _utcnow()
    data["_meta"] = {"input_tokens": itok, "output_tokens": otok,
                     "cost_usd": round(cost, 6), "model": rhp_sonnet.MODEL}
    ops, skipped = rhp_ops(
        ipo_id=int(ipo["id"]), document_sha256=document_sha256, data=data,
        model=rhp_sonnet.MODEL, prompt_version=rhp_sonnet.PROMPT_VERSION,
        observed_at=observed, input_tokens=itok, output_tokens=otok, cost_usd=cost,
    )
    client.batch(ops)
    return {"status": "EXTRACTED_WITH_DROPS" if skipped else "EXTRACTED",
            "cost_usd": round(cost, 6), "ops": len(ops), "skipped": skipped}


def ingest_rhps(*, client: D1IngestClient, store: R2DocumentStore,
                max_extract: int = 4):
    report = {"found": 0, "resolved": 0, "r2_ledgered": 0, "extracted": 0,
              "already_extracted": 0, "unresolved": [], "failures": [], "cost_usd": 0.0}
    extracted_attempts = 0
    for url, rec, path in _rhp_records():
        report["found"] += 1
        company = rec.get("company") or rec.get("title")
        ipo = _resolve(client, name=company)
        if not ipo:
            report["unresolved"].append({"company": company, "path": str(path)})
            continue
        report["resolved"] += 1
        try:
            body = path.read_bytes()
            date = str(rec.get("downloaded_at") or _utcnow())[:10]
            digest, _key, _pages = _store_r2_and_ledger(
                client=client, store=store, body=body, ipo=ipo, doc_type="rhp",
                source_url=url, document_date=date)
            report["r2_ledgered"] += 1
            guard = client.extraction_state(document_sha256=digest,
                                            model="claude-sonnet-4-6", prompt_version="v2-full")
            if guard.get("extracted"):
                report["already_extracted"] += 1
                continue
            if extracted_attempts >= max_extract:
                continue
            extracted_attempts += 1
            result = _extract_rhp(client=client, ipo=ipo, body=body,
                                  document_sha256=digest, company=company)
            if result["status"] == "ALREADY_EXTRACTED":
                report["already_extracted"] += 1
            else:
                report["extracted"] += 1
                report["cost_usd"] += float(result.get("cost_usd") or 0)
        except Exception as exc:
            report["failures"].append({"company": company, "stage": "rhp", "error": f"{type(exc).__name__}:{exc}"})
    report["cost_usd"] = round(report["cost_usd"], 6)
    return report


def run_sbi_download(*, out_dir: pathlib.Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT / "_scripts" / "download_sbi_notes.py"),
           "--out", str(out_dir)]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, errors="replace",
                          timeout=2400)


def _extract_sbi(*, client: D1IngestClient, ipo: dict[str, Any], body: bytes,
                 document_sha256: str):
    from sbi_extraction_run import (anthropic_call, cost, count_tokens_call, guarded_input_tokens,
                                    load_owner_price_card, pdf_pages, parse_complete_response)
    from sbi_sonnet import MODEL, PROMPT_VERSION

    guard = client.extraction_state(document_sha256=document_sha256, model=MODEL,
                                    prompt_version=PROMPT_VERSION)
    if guard.get("extracted"):
        return {"status": "ALREADY_EXTRACTED", "cost_usd": Decimal(0), "ops": 0}
    if os.environ.get("SBI_SONNET_OWNER_APPROVED") != "YES":
        raise RuntimeError("SBI_SONNET_OWNER_APPROVED must be YES for paid production extraction")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    card = load_owner_price_card()
    pages = pdf_pages(body)
    official = count_tokens_call(pages=pages, api_key=api_key)
    guarded = guarded_input_tokens(official)
    projected = cost(guarded, card.output_cap, card)
    if projected > card.spend_cap:
        raise RuntimeError(f"single SBI document guarded maximum ${projected:.6f} exceeds run cap ${card.spend_cap:.6f}")
    raw, itok, otok, stop_reason = anthropic_call(pages=pages, api_key=api_key,
                                                  output_cap=card.output_cap)
    status, parsed = parse_complete_response(raw, doc_id=int(ipo["id"]),
                                             stop_reason=stop_reason, pages=pages)
    if status != "COMPLETE" or parsed is None:
        raise RuntimeError(f"SBI extraction incomplete: {status}")
    actual = cost(itok, otok, card)
    observed = _utcnow()
    ops = sbi_ops(ipo_id=int(ipo["id"]), document_sha256=document_sha256,
                  parsed=parsed, model=MODEL, prompt_version=PROMPT_VERSION,
                  observed_at=observed, raw_output=raw, input_tokens=itok,
                  output_tokens=otok, cost_usd=actual)
    client.batch(ops)
    return {"status": "EXTRACTED_WITH_DROPS" if parsed.get("dropped_items") else "EXTRACTED",
            "cost_usd": actual, "ops": len(ops)}


def ingest_sbi_notes(*, client: D1IngestClient, store: R2DocumentStore,
                     directory: pathlib.Path, max_extract: int = 8):
    from sbi_ingest import company_from_filename, document_date_from_filename
    report = {"found": 0, "resolved": 0, "r2_ledgered": 0, "extracted": 0,
              "already_extracted": 0, "unresolved": [], "failures": [], "cost_usd": 0.0}
    extracted_attempts = 0
    for path in sorted(directory.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True):
        report["found"] += 1
        company = company_from_filename(path)
        ipo = _resolve(client, name=company)
        if not ipo:
            report["unresolved"].append({"company": company, "path": str(path)})
            continue
        report["resolved"] += 1
        try:
            body = path.read_bytes()
            doc_date = document_date_from_filename(path) or dt.date.today()
            digest, _key, _pages = _store_r2_and_ledger(
                client=client, store=store, body=body, ipo=ipo, doc_type="sbi",
                source_url="https://www.sbisecurities.in/research/fundamental",
                document_date=doc_date.isoformat())
            report["r2_ledgered"] += 1
            guard = client.extraction_state(document_sha256=digest, model="claude-sonnet-4-6",
                                            prompt_version="sbi-v1.5")
            if guard.get("extracted"):
                report["already_extracted"] += 1
                continue
            if extracted_attempts >= max_extract:
                continue
            extracted_attempts += 1
            result = _extract_sbi(client=client, ipo=ipo, body=body,
                                  document_sha256=digest)
            if result["status"] == "ALREADY_EXTRACTED":
                report["already_extracted"] += 1
            else:
                report["extracted"] += 1
                report["cost_usd"] += float(result.get("cost_usd") or 0)
            # SBI note is retained in R2, but the temporary local copy is no longer needed.
            path.unlink(missing_ok=True)
        except Exception as exc:
            report["failures"].append({"company": company, "stage": "sbi", "error": f"{type(exc).__name__}:{exc}"})
    report["cost_usd"] = round(report["cost_usd"], 6)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rhps", type=int, default=4)
    ap.add_argument("--max-sbi", type=int, default=8)
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args(argv)
    client = D1IngestClient.from_env(); client.health()
    store = R2DocumentStore()
    if not args.skip_download:
        sebi = run_sebi_download(max_rhps=args.max_rhps)
        if sebi.returncode:
            print(sebi.stderr[-2000:], file=sys.stderr)
        sbi = run_sbi_download(out_dir=SBI_DIR_DEFAULT)
        if sbi.returncode:
            print(sbi.stderr[-2000:], file=sys.stderr)
    result = {
        "rhp": ingest_rhps(client=client, store=store, max_extract=args.max_rhps),
        "sbi": ingest_sbi_notes(client=client, store=store, directory=SBI_DIR_DEFAULT,
                                max_extract=args.max_sbi),
    }
    print("D1_DOCUMENT_SUMMARY=" + json.dumps(result, sort_keys=True, default=str))
    failures = result["rhp"]["failures"] + result["sbi"]["failures"]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
