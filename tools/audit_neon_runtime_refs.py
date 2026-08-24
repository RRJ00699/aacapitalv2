from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMS = [
    "@neondatabase/serverless",
    "DATABASE_URL",
    "NEON_DATABASE_URL",
    "psycopg2",
    "platform_config",
    "kite_session",
]
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs"}
GLOBAL_EXCLUDES = {".git", "node_modules", ".next", ".open-next", "_archive", "docs", "artifacts", ".local-input"}


def is_test_or_support(rel: str) -> bool:
    name = Path(rel).name.lower()
    return (
        rel.startswith(("research/", "tests/", "uat/", "tools/diagnostics/", "compatibility/"))
        or "/tests/" in rel
        or name.startswith("test_")
        or name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or rel.startswith("tools/d1_")
        or rel == "tools/audit_neon_runtime_refs.py"
    )


def tier(rel: str) -> str:
    if is_test_or_support(rel):
        return "nonblocking_support"
    if rel == "auth.ts" or rel.startswith("app/") or rel.startswith("lib/") or rel.startswith("workers/") or rel.startswith("pipeline/build/"):
        return "web_runtime"
    if rel.startswith("pipeline/") or rel.startswith("_scripts/"):
        return "pipeline_owner_runtime"
    return "nonblocking_support"


def executable_lines(path: Path):
    """Yield (line_no, text) with obvious comments removed.

    This is intentionally conservative: it removes full-line comments and TS/JS block
    comments so prose mentioning Neon does not become a runtime blocker. It does not
    attempt to parse language grammars; exact matched lines are still emitted for review.
    """
    in_block = False
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = raw.strip()
        if path.suffix.lower() in {".ts", ".tsx", ".js", ".mjs", ".cjs"}:
            if in_block:
                if "*/" in s:
                    in_block = False
                    s = s.split("*/", 1)[1].strip()
                else:
                    continue
            if s.startswith("/*"):
                if "*/" in s:
                    s = s.split("*/", 1)[1].strip()
                else:
                    in_block = True
                    continue
            if s.startswith("//"):
                continue
        elif path.suffix.lower() == ".py":
            if s.startswith("#"):
                continue
        if s:
            yield n, s


def main() -> int:
    buckets = {"web_runtime": [], "pipeline_owner_runtime": [], "nonblocking_support": []}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in CODE_EXTS:
            continue
        rel_path = path.relative_to(ROOT)
        if any(part in GLOBAL_EXCLUDES for part in rel_path.parts):
            continue
        rel = rel_path.as_posix()
        try:
            matched = []
            for n, line in executable_lines(path):
                terms = [term for term in TERMS if term in line]
                if terms:
                    matched.append({"line": n, "terms": terms, "text": line[:220]})
        except OSError:
            continue
        if matched:
            buckets[tier(rel)].append({"path": rel, "matches": matched})

    summary = {
        "web_runtime_blockers": len(buckets["web_runtime"]),
        "pipeline_owner_runtime_blockers": len(buckets["pipeline_owner_runtime"]),
        "nonblocking_support_refs": len(buckets["nonblocking_support"]),
        "web_runtime_paths": [x["path"] for x in buckets["web_runtime"]],
        "pipeline_owner_runtime_paths": [x["path"] for x in buckets["pipeline_owner_runtime"]],
    }
    result = {"summary": summary, **buckets}
    out = ROOT / "artifacts" / "neon-runtime-ref-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"output={out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
