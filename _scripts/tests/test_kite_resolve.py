#!/usr/bin/env python3
"""kite_fetch.resolve_token — NSE-exact preferred, BSE-exact fallback.

Offline: a FAKE instrument dump is fed in (no Kite contact, no DB). Guards the
regression where the old NSE-only lookup silently dropped BSE-listed mainboard
IPOs, and proves the dump is fetched ONCE with NO exchange argument (the single
/instruments call)."""
import importlib.util
import os
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
# kite_fetch lives in the pipeline/ subtree (repo root), not _scripts/
_spec = importlib.util.spec_from_file_location(
    "kite_fetch", os.path.join(HERE, "..", "..", "pipeline", "kite_fetch.py"))
kf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(kf)

# Real tokens from the review: INDO-MIM lists on BOTH (NSE preferred), CUBEINVIT
# is BSE-only, VMOBILE is absent from the dump entirely.
FAKE_DUMP = [
    {"tradingsymbol": "INDOMIM",   "exchange": "NSE", "instrument_token": 195661057},
    {"tradingsymbol": "INDOMIM",   "exchange": "BSE", "instrument_token": 139478276},
    {"tradingsymbol": "CUBEINVIT", "exchange": "BSE", "instrument_token": 139238148},
    {"tradingsymbol": "RELIANCE",  "exchange": "NSE", "instrument_token": 738561},
    {"tradingsymbol": "INDOMIMX",  "exchange": "NSE", "instrument_token": 999999},  # near-miss noise
]


class FakeKite:
    def __init__(self, rows): self.rows = rows; self.calls = []
    def instruments(self, *args):
        self.calls.append(args)          # record how it was called
        return self.rows


@pytest.fixture(autouse=True)
def _reset_instrument_cache():
    kf._INSTRUMENTS = None               # the module caches the dump globally
    kf._TOKEN_EXCH = None                # and the token->exchange map
    yield
    kf._INSTRUMENTS = None
    kf._TOKEN_EXCH = None


def test_nse_preferred_when_listed_on_both():
    """INDO-MIM is on NSE and BSE -> NSE token wins."""
    tok, how = kf.resolve_token(FakeKite(FAKE_DUMP), None, "INDOMIM")
    assert (tok, how) == (195661057, "NSE")


def test_bse_fallback_when_no_nse():
    """CUBEINVIT is BSE-only -> the fallback recovers it (old code returned nothing)."""
    tok, how = kf.resolve_token(FakeKite(FAKE_DUMP), None, "CUBEINVIT")
    assert (tok, how) == (139238148, "BSE")


def test_unresolved_when_absent():
    """VMOBILE is not in the dump -> (None, 'unresolved'), never a guess."""
    tok, how = kf.resolve_token(FakeKite(FAKE_DUMP), None, "VMOBILE")
    assert (tok, how) == (None, "unresolved")


def test_exact_match_only_no_fuzzy():
    """A partial symbol must NOT match INDOMIM/INDOMIMX — exact tradingsymbol only."""
    tok, how = kf.resolve_token(FakeKite(FAKE_DUMP), None, "INDO")
    assert (tok, how) == (None, "unresolved")


def test_case_and_whitespace_normalised():
    tok, how = kf.resolve_token(FakeKite(FAKE_DUMP), None, "  indomim ")
    assert (tok, how) == (195661057, "NSE")


def test_empty_symbol_is_unresolved():
    for sym in (None, "", "   "):
        assert kf.resolve_token(FakeKite(FAKE_DUMP), None, sym) == (None, "unresolved")


def test_exchange_for_token_reads_back_provenance():
    """Backfill path: an already-stored token's exchange is read back from the dump
    (NSE|BSE), and a token absent from the dump (delisted) returns None so nothing is
    asserted."""
    k = FakeKite(FAKE_DUMP)
    assert kf.exchange_for_token(k, 195661057) == "NSE"   # INDOMIM on NSE
    assert kf.exchange_for_token(k, 139238148) == "BSE"   # CUBEINVIT on BSE
    assert kf.exchange_for_token(k, 424242424) is None    # not in dump -> unknown


def test_single_no_arg_instruments_call():
    """The dump is fetched ONCE per run, with NO exchange arg (one /instruments call)."""
    k = FakeKite(FAKE_DUMP)
    kf.resolve_token(k, None, "INDOMIM")
    kf.resolve_token(k, None, "CUBEINVIT")   # served from cache — no second fetch
    assert k.calls == [()], f"expected one no-arg instruments() call, got {k.calls}"
