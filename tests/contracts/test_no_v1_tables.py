"""Production code must not read or write retired V1 tables."""
import io
import pathlib
import re
import tokenize
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCAN_ZONES = ("app", "components", "lib", "workers", "pipeline", "_scripts")
FORBIDDEN = (
    "ipo_intelligence",
    "ipo_consolidated",
    "ipo_golden",
    "ipo_master",
    "ipo_rhp_intel",
    "price_candles",
    "ipo_verdicts",
    "ipo_flags",
)
SOURCE_SUFFIXES = {".js", ".jsx", ".mjs", ".py", ".ts", ".tsx"}

# Architecture-owner approval is required to add an entry. This ratchet may
# shrink as V1 debt is retired, but must always exactly match caller evidence.
KEEP_V1_ALLOWLIST = {
    "_scripts/backfill_eps_post.py", "_scripts/backfill_master_computables.py",
    "_scripts/backup_critical_tables.py", "_scripts/compute_d10.py",
    "_scripts/compute_flags.py", "_scripts/compute_journal_outcomes.py",
    "_scripts/compute_quality_score.py", "_scripts/compute_verdicts.py",
    "_scripts/derive_peer_pe_from_notes.py", "_scripts/engines/market_regime.py",
    "_scripts/fetch_ipo_news.py", "_scripts/fetch_new_rhps.py",
    "_scripts/fetch_peer_pe.py", "_scripts/fill_listing_open_from_candles.py",
    "_scripts/ipo/backfill_ipo_ohlc.py", "_scripts/ipo/fetch_nse_ipos.py",
    "_scripts/ipo/ipo_play_selector.py", "_scripts/ipo_score.py",
    "_scripts/ipomatrix_ingest.py", "_scripts/lib/stage_state.py",
    "_scripts/lineage_registry.py", "_scripts/nse_preopen_capture.py",
    "_scripts/parse_sbi_notes.py", "_scripts/prod/kite_sync_and_predict.py",
    "_scripts/purge_candles_after_lockin.py", "_scripts/reconcile_listing_dates.py",
    "_scripts/rhp_auto.py", "_scripts/rhp_sonnet.py", "_scripts/rhp_sonnet_store.py",
    "_scripts/run_ipo_pipeline_lean.py", "_scripts/sbi_haiku_extract.py",
    "_scripts/schema_sync.py", "_scripts/smoke_probe.py",
    "_scripts/sync_inwindow_candles.py", "_scripts/sync_issue_details.py",
    "_scripts/vm_verify.py",
}


def _without_comments(path: pathlib.Path) -> str:
    source = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".py":
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        kept = []
        previous = None
        for token in tokens:
            is_docstring = token.type == tokenize.STRING and previous in {
                None,
                tokenize.INDENT,
                tokenize.NEWLINE,
            }
            if token.type != tokenize.COMMENT and not is_docstring:
                kept.append(token)
            if token.type not in {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING}:
                previous = token.type
        return tokenize.untokenize(kept)
    return re.sub(r"/\*.*?\*/|//[^\r\n]*", "", source, flags=re.DOTALL)


def test_no_v1_table_tokens_in_production_code():
    hits = []
    for zone in SCAN_ZONES:
        for path in (ROOT / zone).rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            relative = path.relative_to(ROOT)
            if zone == "_scripts" and "tests" in relative.parts:
                continue
            if relative == pathlib.Path("pipeline/inspect_schema.py"):
                continue  # Its explicitly named V1_DEBRIS inventory is diagnostic-only.
            source = _without_comments(path)
            for token in FORBIDDEN:
                if re.search(rf"\b{re.escape(token)}\b", source, re.IGNORECASE):
                    if relative.as_posix() not in KEEP_V1_ALLOWLIST:
                        hits.append(f"{relative}: {token}")
    assert not hits, "retired V1 table token(s) in production code:\n" + "\n".join(hits)


def test_v1_allowlist_exactly_matches_authoritative_keep_graph():
    sys.path.insert(0, str(ROOT / "tools"))
    import scripts_caller_graph

    result = scripts_caller_graph.analyze(ROOT).production()
    evidenced = {
        path for path in result.keep
        if scripts_caller_graph.v1_references(ROOT / path)
    }
    assert KEEP_V1_ALLOWLIST == evidenced
