#!/usr/bin/env python3
"""Pure unit test for rhp_writer._derive_flags — NO database.

Benign signals must count as red flags (WATCH), only severe signals become
junk_signals. Importing this module must be side-effect safe for pytest
collection; executable behavior is kept under __main__.
"""
from rhp_writer import _derive_flags, SEVERE_JUNK


def run_checks():
    ok = True

    def chk(m, c):
        nonlocal ok
        ok = ok and c
        print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    r, j = _derive_flags({"customer_concentration_high": True})
    chk("benign customer_concentration_high -> junk_signals empty", j == [])
    chk("benign customer_concentration_high -> red_flag_count 1", r == 1)

    r, j = _derive_flags({"customer_concentration_high": True, "contingent_liabilities_material": True})
    chk("two benign -> junk_signals empty", j == [])
    chk("two benign -> red_flag_count 2", r == 2)

    r, j = _derive_flags({"sebi_action": True})
    chk("sebi_action -> junk_signals=['sebi_action']", j == ["sebi_action"])
    chk("sebi_action counts as a red flag too", r == 1)

    r, j = _derive_flags({"sebi_action": True, "auditor_qualified": True})
    chk("mixed severe+benign -> junk_signals only severe", j == ["sebi_action"])
    chk("mixed severe+benign -> red_flag_count counts both", r == 2)

    r, j = _derive_flags({"auditor_qualified": True})
    chk("auditor_qualified alone -> NOT junk (owner ruling)", j == [])
    chk("auditor_qualified -> red flag", r == 1)

    chk("SEVERE_JUNK excludes auditor_qualified & criminal_litigation",
        "auditor_qualified" not in SEVERE_JUNK and "criminal_litigation" not in SEVERE_JUNK)

    print(f"\n{'ALL PASS' if ok else 'SOME FAILED'}")
    return ok


def test_derive_flags_contract():
    assert run_checks()


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_checks() else 1)
