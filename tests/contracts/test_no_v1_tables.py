"""Production code must not read or write retired V1 tables."""
import io
import pathlib
import re
import tokenize


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCAN_ZONES = ("app", "components", "lib", "workers", "pipeline")
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
            if relative == pathlib.Path("pipeline/inspect_schema.py"):
                continue  # Its explicitly named V1_DEBRIS inventory is diagnostic-only.
            source = _without_comments(path)
            for token in FORBIDDEN:
                if re.search(rf"\b{re.escape(token)}\b", source, re.IGNORECASE):
                    hits.append(f"{relative}: {token}")
    assert not hits, "retired V1 table token(s) in production code:\n" + "\n".join(hits)
