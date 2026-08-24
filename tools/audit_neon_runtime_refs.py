from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", "node_modules", ".next", ".open-next", "_archive", "docs", "artifacts", ".local-input"}
EXCLUDED_PREFIXES = {
    "tools/d1_",  # one-time migration/backfill tooling intentionally reads Neon
    "compatibility/",  # legacy compatibility tree; audited separately before deletion
}
TERMS = [
    "@neondatabase/serverless",
    "DATABASE_URL",
    "NEON_DATABASE_URL",
    "psycopg2",
    "platform_config",
    "kite_session",
]


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
        return False
    return not any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def main() -> int:
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not included(path):
            continue
        if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".sql"}:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        matched = []
        for n, line in enumerate(lines, 1):
            terms = [term for term in TERMS if term in line]
            if terms:
                matched.append({"line": n, "terms": terms, "text": line.strip()[:220]})
        if matched:
            hits.append({"path": path.relative_to(ROOT).as_posix(), "matches": matched})

    result = {"active_files_with_neon_refs": len(hits), "files": hits}
    out = ROOT / "artifacts" / "neon-runtime-ref-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"active_files_with_neon_refs": len(hits), "paths": [h["path"] for h in hits]}, indent=2))
    print(f"output={out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
