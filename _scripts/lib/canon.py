# -*- coding: utf-8 -*-
"""_scripts/lib/canon.py — THE canonical company-name key. One definition.

Every matcher (scrapers, ingest, dedup, health gate) imports canon() from here.
The SQL twin is canon_company(text) (guardrails_canon.sql) and the route joins
use CANON_SQL_REGEX — all three strip the SAME token set. If the set ever needs
a new token (e.g. 'inc'), change it HERE + the SQL function together.

History: five divergent inline copies of this function caused the 2026-07-16
all-awaiting-cards incident (route join, ipomatrix_ingest ×2, fetch_nse, dedup).
"""
import re

# ltd/limited/pvt/private: corporate suffixes · ipo: IPOMatrix suffix ·
# and/&: conjunction variance ("M & B" vs "M And B")
_STRIP = re.compile(r"\b(ltd\.?|limited|pvt\.?|private|ipo|and)\b|&", re.I)
_KEEP = re.compile(r"[^a-z0-9]")

CANON_SQL_REGEX = r"\y(ltd|limited|pvt|private|ipo|and)\y|&|[^a-z0-9]"  # \y = PG word boundary; parity with _STRIP's \b

def canon(name):
    """'SBI Funds Management Ltd. IPO' == 'SBI Funds Management Limited' -> 'sbifundsmanagement'"""
    return _KEEP.sub("", _STRIP.sub(" ", (name or "").lower()))

if __name__ == "__main__":
    cases = [
        ("SBI Funds Management Ltd. IPO", "SBI Funds Management Limited"),
        ("Caliber Mining & Logistics Ltd.", "Caliber Mining and Logistics Limited"),
        ("M & B Switchgears Ltd.", "M And B Switchgears Limited"),
        ("Alpine Texworld Pvt. Ltd.", "ALPINE TEXWORLD PRIVATE LIMITED"),
    ]
    for a, b in cases:
        assert canon(a) == canon(b), (a, b, canon(a), canon(b))
    assert canon("Chipotle Brands Ltd") == "chipotlebrands"  # 'ipo' inside a word survives
    print("canon self-test: 5/5")
