#!/usr/bin/env python3
"""Mechanically resolve production callers of files below ``_scripts``.

This analyzer is deliberately syntax-oriented: it recognizes imports and script
path constants, including bare script names used by orchestrators whose working
directory is ``_scripts``. It never imports or executes repository code.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import warnings
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SCRIPT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".sh", ".ps1", ".bat", ".cmd"}
PRODUCTION_SUFFIXES = SCRIPT_SUFFIXES | {".sql"}
V1_TABLES = ("ipo_intelligence", "ipo_consolidated", "ipo_golden", "ipo_master", "ipo_rhp_intel", "price_candles", "ipo_verdicts", "ipo_flags")
PATH_TOKEN = re.compile(r"(?<![A-Za-z0-9_.-])((?:_scripts/|\.\.?/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:py|js|mjs|cjs|ts|tsx|sh|ps1|bat|cmd))(?![A-Za-z0-9_.-])")

@dataclass(frozen=True)
class Edge:
    caller: str
    callee: str
    kind: str

@dataclass
class Result:
    files: set[str]
    roots: dict[str, set[str]]
    edges: set[Edge]
    keep: set[str]
    predecessors: dict[str, set[str]]

    def shortest_chain(self, target: str) -> list[str]:
        queue = deque((root, [root]) for root in self.roots if root in self.keep)
        seen = set(self.roots)
        outgoing = defaultdict(set)
        for edge in self.edges:
            outgoing[edge.caller].add(edge.callee)
        while queue:
            node, chain = queue.popleft()
            if node == target:
                return chain
            for child in sorted(outgoing[node]):
                if child not in seen:
                    seen.add(child); queue.append((child, chain + [child]))
        return []

    def production(self) -> "Result":
        """Return the documented production view without changing graph edges.

        Production excludes ``_scripts/tests/**`` and tracked sidecars whose
        suffix is not in ``PRODUCTION_SUFFIXES``. In this repository those
        sidecars are the extensionless deploy trigger plus .md, .patch, .csv,
        and .pyc files.
        """
        files = {
            path for path in self.files
            if not path.startswith("_scripts/tests/")
            and PurePosixPath(path).suffix in PRODUCTION_SUFFIXES
        }
        return Result(
            files=files,
            roots={path: evidence for path, evidence in self.roots.items() if path in files},
            edges=self.edges,
            keep=self.keep & files,
            predecessors=self.predecessors,
        )


def tracked_scripts(repo: Path) -> set[str]:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "_scripts"], cwd=repo, check=True,
            capture_output=True, text=True,
        )
        tracked = {line for line in completed.stdout.splitlines() if line}
        if tracked:
            return tracked
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    # The graph remains usable in fixture directories without Git metadata.
    scripts = repo / "_scripts"
    return {p.relative_to(repo).as_posix() for p in scripts.rglob("*") if p.is_file()}


def _module_index(files: set[str]) -> dict[str, str]:
    out = {}
    for rel in files:
        path = PurePosixPath(rel)
        if path.suffix != ".py":
            continue
        parts = list(path.with_suffix("").parts)
        out[".".join(parts)] = rel
        if parts[-1] == "__init__":
            out[".".join(parts[:-1])] = rel
    return out


def _parse_python(source: str) -> ast.AST:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(source)


def _resolve_token(token: str, caller: str, files: set[str]) -> str | None:
    token = token.replace("\\", "/")
    caller_path = PurePosixPath(caller)
    candidates = []
    if token.startswith("_scripts/"):
        candidates.append(PurePosixPath(token))
    elif token.startswith("../") or token.startswith("./"):
        candidates.append(caller_path.parent / token)
    else:
        # Bare orchestration arguments in _scripts run with HERE as cwd.
        if caller.startswith("_scripts/"):
            candidates.append(PurePosixPath("_scripts") / token)
        candidates.append(caller_path.parent / token)
    for candidate in candidates:
        normalized = PurePosixPath(*[part for part in candidate.parts if part != "."])
        parts = []
        for part in normalized.parts:
            if part == "..":
                if parts: parts.pop()
            else: parts.append(part)
        rel = PurePosixPath(*parts).as_posix()
        if rel in files:
            return rel
    return None


def _python_edges(repo: Path, caller: str, files: set[str], modules: dict[str, str]) -> set[Edge]:
    source = (repo / caller).read_text(encoding="utf-8", errors="ignore")
    edges = set()
    try:
        tree = _parse_python(source)
    except SyntaxError:
        tree = None
    if tree is not None:
        package = ".".join(PurePosixPath(caller).with_suffix("").parts[:-1])
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = package.split(".")
                    base = ".".join(parent[: len(parent) - node.level + 1] + ([base] if base else []))
                names = [base] + ([f"{base}.{alias.name}" for alias in node.names] if base else [])
            for name in names:
                # Running a script directly puts ITS OWN directory on sys.path[0],
                # so a bare `import sibling` inside _scripts/<sub>/ resolves within
                # <sub> before anything else. Without the package-qualified
                # candidate, every sibling import below the top level was invisible
                # — which is how _scripts/prod/kite_sync_and_predict.py's
                # `from env_utils import ...` came to be misread as UNREACHABLE.
                # Candidates are not mutually exclusive on purpose: this graph
                # decides what must be KEPT, so over-approximating an edge is safe
                # while missing one deletes a live dependency.
                candidates = ([f"{package}.{name}"] if package else []) + [name, f"_scripts.{name}"]
                for candidate in candidates:
                    if (not caller.startswith("_scripts/") and candidate == f"_scripts.{name}"
                            and ((repo / PurePosixPath(caller).parent / f"{name.split('.')[0]}.py").exists()
                                 or (repo / PurePosixPath(caller).parent / name.split('.')[0] / "__init__.py").exists())):
                        continue  # A same-tree module wins normal Python resolution.
                    if candidate in modules:
                        edges.add(Edge(caller, modules[candidate], "python import"))
            # Constants are intentional: this catches step(["foo.py"]),
            # subprocess([python, "foo.py"]), os.system, and explicit paths.
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                for match in PATH_TOKEN.finditer(node.value):
                    callee = _resolve_token(match.group(1), caller, files)
                    if callee:
                        kind = "relative script argument" if "/" not in match.group(1) else "script path"
                        if callee != caller:
                            edges.add(Edge(caller, callee, kind))
    return edges


def file_edges(repo: Path, caller: str, files: set[str], modules: dict[str, str]) -> set[Edge]:
    if PurePosixPath(caller).suffix == ".py":
        return _python_edges(repo, caller, files, modules)
    source = (repo / caller).read_text(encoding="utf-8", errors="ignore")
    return {Edge(caller, callee, "shell/script path") for m in PATH_TOKEN.finditer(source)
            if (callee := _resolve_token(m.group(1), caller, files)) and callee != caller}


def analyze(repo: Path) -> Result:
    repo = repo.resolve(); files = tracked_scripts(repo); modules = _module_index(files)
    edges = set()
    for caller in files:
        edges.update(file_edges(repo, caller, files, modules))
    roots: dict[str, set[str]] = defaultdict(set)
    def root(callee: str | None, evidence: str):
        if callee in files: roots[callee].add(evidence)

    # job_runner itself is the documented cron entrypoint; JOBS paths are parsed
    # by the same constant resolver and also receive precise root evidence.
    runner = "_scripts/job_runner.py"
    root(runner, "documented VM cron entrypoint")
    if runner in files:
        source = (repo / runner).read_text(encoding="utf-8", errors="ignore")
        try:
            tree = _parse_python(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "JOBS" for t in node.targets):
                    for job, command in ast.literal_eval(node.value).items():
                        if command: root(_resolve_token(command[0], runner, files), f"_scripts/job_runner.py JOBS[{job}]")
        except (SyntaxError, ValueError): pass

    external = []
    workflows = repo / ".github" / "workflows"
    if workflows.exists(): external += [(p, "enabled workflow") for p in workflows.glob("*.y*ml")]
    package = repo / "package.json"
    if package.exists(): external.append((package, "package.json script"))
    pipeline = repo / "pipeline"
    if pipeline.exists(): external += [(p, "pipeline path/import") for p in pipeline.rglob("*") if p.is_file() and p.suffix in SCRIPT_SUFFIXES and not p.name.startswith("test_")]
    for path, kind in external:
        relcaller = path.relative_to(repo).as_posix(); source = path.read_text(encoding="utf-8", errors="ignore")
        for match in PATH_TOKEN.finditer(source):
            root(_resolve_token(match.group(1), relcaller, files), f"{kind}: {relcaller}")
        if path.suffix == ".py":
            for edge in _python_edges(repo, relcaller, files, modules):
                root(edge.callee, f"pipeline import: {relcaller}")

    outgoing = defaultdict(set); predecessors = defaultdict(set)
    for edge in edges: outgoing[edge.caller].add(edge.callee); predecessors[edge.callee].add(edge.caller)
    keep = set(roots); queue = deque(keep)
    while queue:
        for child in outgoing[queue.popleft()]:
            if child not in keep: keep.add(child); queue.append(child)
    return Result(files, dict(roots), edges, keep, dict(predecessors))


def v1_references(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    return [table for table in V1_TABLES if re.search(rf"\b{table}\b", source, re.IGNORECASE)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    raw = analyze(args.repo)
    production = raw.production()

    repo = args.repo.resolve()

    def summary(result: Result) -> dict[str, int]:
        v1_files = {path for path in result.files if v1_references(repo / path)}
        return {
            "total": len(result.files),
            "keep": len(result.keep),
            "unreachable": len(result.files - result.keep),
            "unknown": 0,
            "v1_total": len(v1_files),
            "kept_with_v1": len(v1_files & result.keep),
            "unreachable_with_v1": len(v1_files - result.keep),
        }

    selected = production if args.production else raw
    payload = {
        "mode": "production" if args.production else "raw",
        "production_totals": summary(production),
        "raw_all_tracked_totals": summary(raw),
        "keep": sorted(selected.keep),
        "unreachable": sorted(selected.files - selected.keep),
        "roots": {key: sorted(value) for key, value in sorted(selected.roots.items())},
        "edges": [edge.__dict__ for edge in sorted(raw.edges, key=lambda edge: (edge.caller, edge.callee, edge.kind))],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    if args.production:
        prod = payload["production_totals"]
        print("PRODUCTION TOTALS")
        print(f"TOTAL={prod['total']} KEEP={prod['keep']} UNREACHABLE={prod['unreachable']} UNKNOWN={prod['unknown']}")
        print(f"V1_TOTAL={prod['v1_total']} KEPT_WITH_V1={prod['kept_with_v1']} UNREACHABLE_WITH_V1={prod['unreachable_with_v1']}")
    raw_totals = payload["raw_all_tracked_totals"]
    print("RAW ALL-TRACKED TOTALS")
    print(f"TOTAL={raw_totals['total']} KEEP={raw_totals['keep']} UNREACHABLE={raw_totals['unreachable']} UNKNOWN={raw_totals['unknown']}")
    print(f"V1_TOTAL={raw_totals['v1_total']} KEPT_WITH_V1={raw_totals['kept_with_v1']} UNREACHABLE_WITH_V1={raw_totals['unreachable_with_v1']}")

if __name__ == "__main__": main()
