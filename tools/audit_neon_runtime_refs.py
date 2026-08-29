from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "neon-runtime-ref-audit.json"

STRONG_TERMS = (
    "@neondatabase/serverless",
    "DATABASE_URL",
    "NEON_DATABASE_URL",
    "psycopg2",
)
WEAK_TERMS = ("platform_config", "kite_session")
TERMS = STRONG_TERMS + WEAK_TERMS

SKIP_DIRS = {
    ".git", "node_modules", ".next", ".open-next", "_archive", "docs", "artifacts",
    ".local-input", "research", "tests", "uat", "compatibility",
}
SUPPORT_PREFIXES = (
    "tools/d1_",
    "tools/diagnostics/",
    "tools/audit_neon_runtime_refs.py",
    "_scripts/tests/",
)

WEB_PREFIXES = ("app/", "lib/")
WEB_EXACT = {"auth.ts"}
PIPELINE_PREFIXES = ("pipeline/",)
PIPELINE_EXACT = {
    "_scripts/job_runner.py",
    "_scripts/run_ipo_pipeline_lean.py",
    "_scripts/nse_preopen_capture.py",
    "_scripts/refresh_kite_token.py",
    "_scripts/prod/env_utils.py",
    "_scripts/prod/kite_sync_and_predict.py",
}

CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".sql"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def base_included(path: Path) -> bool:
    r = rel(path)
    parts = path.relative_to(ROOT).parts
    if any(part in SKIP_DIRS for part in parts):
        return False
    if any(r.startswith(p) for p in SUPPORT_PREFIXES):
        return False
    return path.suffix.lower() in CODE_SUFFIXES


def strip_nonexec_line(line: str, suffix: str) -> str:
    s = line.strip()
    if not s:
        return ""
    if suffix == ".py" and s.startswith("#"):
        return ""
    if suffix in {".ts", ".tsx", ".js", ".mjs", ".cjs"} and s.startswith("//"):
        return ""
    if suffix == ".sql" and s.startswith("--"):
        return ""
    return s


def classify(r: str) -> str:
    if r in WEB_EXACT or r.startswith(WEB_PREFIXES):
        if ".test." in r or ".spec." in r:
            return "support"
        return "web"
    if r in PIPELINE_EXACT or r.startswith(PIPELINE_PREFIXES):
        name = Path(r).name
        if name.startswith("test_") or name in {"conftest.py", "inspect_schema.py", "inspect_checks.py", "verify_r2.py", "verify_scores.py"}:
            return "support"
        return "pipeline"
    return "support"


def main() -> int:
    buckets: dict[str, list[dict]] = {"web": [], "pipeline": [], "support": []}
    for path in ROOT.rglob("*"):
        if not path.is_file() or not base_included(path):
            continue
        r = rel(path)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        executable = [strip_nonexec_line(raw, path.suffix.lower()) for raw in lines]
        has_strong = any(any(term in line for term in STRONG_TERMS) for line in executable if line)
        matches = []
        for n, line in enumerate(executable, 1):
            if not line:
                continue
            terms = [t for t in TERMS if t in line]
            # A table-name mention in UI copy/metadata is not a database dependency.
            # Weak terms only count when the same file also contains a real DB client/env reference.
            if terms and (has_strong or any(t in STRONG_TERMS for t in terms)):
                matches.append({"line": n, "terms": terms, "text": line[:220]})
        if matches:
            buckets[classify(r)].append({"path": r, "matches": matches})

    result = {
        "web_runtime_blockers": len(buckets["web"]),
        "pipeline_owner_runtime_blockers": len(buckets["pipeline"]),
        "nonblocking_support_refs": len(buckets["support"]),
        "web_runtime_paths": [x["path"] for x in buckets["web"]],
        "pipeline_owner_runtime_paths": [x["path"] for x in buckets["pipeline"]],
        "support_paths": [x["path"] for x in buckets["support"]],
        "details": buckets,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "web_runtime_blockers": result["web_runtime_blockers"],
        "pipeline_owner_runtime_blockers": result["pipeline_owner_runtime_blockers"],
        "nonblocking_support_refs": result["nonblocking_support_refs"],
        "web_runtime_paths": result["web_runtime_paths"],
        "pipeline_owner_runtime_paths": result["pipeline_owner_runtime_paths"],
    }, indent=2))
    print(f"output={OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
