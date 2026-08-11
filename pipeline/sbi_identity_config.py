"""Reviewed, exact-SHA SBI identity decisions."""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass

CONFIG_PATH = pathlib.Path(__file__).with_name("config") / "sbi_identity_overrides.json"
CLASSIFICATIONS = {"junk", "reit", "fpo", "out_of_universe"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISIN = re.compile(r"^INE[A-Z0-9]{9}$")


@dataclass(frozen=True)
class ReviewedDecision:
    kind: str
    entry: dict


def load_config(path=CONFIG_PATH):
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if set(payload) != {"overrides", "exclusions"}:
        raise ValueError("SBI identity config must contain only overrides and exclusions")
    return payload


def reviewed_decision(local_sha256: str, filename: str, *, path=CONFIG_PATH):
    """Return only an exact-SHA reviewed decision; never approximate."""
    if not SHA256.fullmatch(local_sha256):
        raise ValueError("invalid local_sha256")
    config = load_config(path)
    matches = []
    for kind in ("overrides", "exclusions"):
        for entry in config[kind]:
            if entry.get("local_sha256") == local_sha256:
                if not entry.get("filename"):
                    raise ValueError("reviewed SBI decision requires filename")
                matches.append((kind, entry))
    if len(matches) > 1:
        raise ValueError("duplicate reviewed SBI SHA decision")
    if not matches:
        return None
    kind, entry = matches[0]
    if not entry.get("evidence"):
        raise ValueError("reviewed SBI decision requires evidence")
    if kind == "exclusions":
        if entry.get("classification") not in CLASSIFICATIONS:
            raise ValueError("unsupported SBI exclusion classification")
    elif (not entry.get("owner_approved") or not isinstance(entry.get("ipo_id"), int)
          or entry["ipo_id"] <= 0 or not ISIN.fullmatch(str(entry.get("isin", "")))):
        return ReviewedDecision("unapproved_override", entry)
    return ReviewedDecision(kind[:-1], entry)
