#!/usr/bin/env python3
"""Offline-only proposal generator; it never imports a database or network client."""
from __future__ import annotations

import argparse
import json
import pathlib
import re

try:
    from .company_identity import canon
except ImportError:
    from company_identity import canon


def connector_canon(value):
    value = re.sub(r"(?:%20|[_-])?(?:and|&|%26)(?:%20|[_-])?", " & ", str(value),
                   flags=re.IGNORECASE)
    return canon(value)


def candidates(note, spine):
    name = note["company"]
    exact = [row for row in spine if connector_canon(row["name_display"]) == connector_canon(name)]
    if exact:
        return "EXACT_VARIANT", exact
    needle = canon(name)
    contained = [row for row in spine
                 if needle and (needle in canon(row["name_display"])
                                or canon(row["name_display"]) in needle)]
    return ("CONTAINMENT", contained) if contained else ("NO_ROW_FOUND", [])


def generate(inventory, spine):
    rows = []
    for note in inventory:
        tier, found = candidates(note, spine)
        status = tier if len(found) == 1 else ("AMBIGUOUS" if len(found) > 1 else "NO_ROW_FOUND")
        rows.append({"note": note, "status": status, "candidates": found})
    return rows


def markdown(rows):
    lines = ["# SBI identity override proposal", "", "Generated offline; every proposal requires owner review.", "",
             "| SHA-256 | Filename | Result | Proposed IPO ID | Proposed ISIN | Evidence |",
             "|---|---|---|---|---|---|"]
    for row in rows:
        found = row["candidates"]
        ids = "<br>".join(str(candidate["ipo_id"]) for candidate in found)
        isins = "<br>".join(str(candidate.get("isin") or "") for candidate in found)
        evidence = "<br>".join(f"{candidate['name_display']} ({candidate.get('listing_date') or ''})" for candidate in found)
        note = row["note"]
        lines.append(f"| {note['local_sha256']} | {note['filename']} | {row['status']} | {ids} | {isins} | {evidence} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=pathlib.Path)
    parser.add_argument("spine", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    spine = json.loads(args.spine.read_text(encoding="utf-8"))
    args.output.write_text(markdown(generate(inventory, spine)), encoding="utf-8")


if __name__ == "__main__":
    main()
