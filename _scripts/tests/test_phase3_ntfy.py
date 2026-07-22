#!/usr/bin/env python3
"""Tests for Phase-3 ntfy alerting (2026-07-20).
Offline — no network, no Neon. notify() is exercised FOR REAL with a
monkeypatched urlopen; integrations are file-contract checked.

Covers:
  A. lib/notify.py behavior: no-op without NTFY_TOPIC, priority mapping,
     custom NTFY_SERVER, dual-timezone stamp (IST + US-Central), never raises
  B. run_ipo_pipeline_lean: pushes on every failure-sink event + stale Kite token
  C. refresh_kite_token: URGENT push on every failure exit
  D. rhp_auto: run() results now collected; failures -> push + exit 1 (audit #5)
  E. fetch_new_rhps: attempted-but-zero downloads -> push + exit 1
"""
import importlib
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # _scripts/
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture()
def notify_mod(monkeypatch):
    import lib.notify as n
    importlib.reload(n)
    return n


# ── A. notify() behavior (real execution) ───────────────────────────────────
def test_notify_noop_without_topic(notify_mod, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    calls = []
    monkeypatch.setattr(notify_mod.urllib.request, "urlopen",
                        lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError))
    assert notify_mod.notify("t", "m") is False
    assert calls == [], "must not touch the network when NTFY_TOPIC is unset"


def test_notify_sends_with_priority_and_server(notify_mod, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "unit-test-topic")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.com/")
    seen = {}

    class FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["priority"] = req.get_header("Priority")
        seen["title"] = req.get_header("Title")
        seen["body"] = req.data.decode()
        return FakeResp()

    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", fake_urlopen)
    assert notify_mod.notify("Kite down", "boom", priority="urgent", tags=["rotating_light"]) is True
    assert seen["url"] == "https://ntfy.example.com/unit-test-topic"
    assert seen["priority"] == "5"       # urgent -> 5
    assert seen["title"] == "Kite down"
    # dual-timezone stamp: app/market in IST, Rakesh in US Central
    assert "IST " in seen["body"] and "US-Central " in seen["body"]


def test_notify_priority_map(notify_mod):
    assert notify_mod._PRIORITY["urgent"] == "5"
    assert notify_mod._PRIORITY["high"] == "4"
    assert notify_mod._PRIORITY["default"] == "3"


def test_notify_never_raises(notify_mod, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "unit-test-topic")
    def explode(*a, **k): raise OSError("network down")
    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", explode)
    assert notify_mod.notify("t", "m") is False   # swallowed, False returned


# ── B. pipeline integration ─────────────────────────────────────────────────
def test_lean_pipeline_alerts():
    src = _read("run_ipo_pipeline_lean.py")
    # step alerts import lib.notify ALIASED (step_alert): the bare name
    # shadowed the module-level notify() and made every non-failure exit
    # silently skip its ping (owner receipts 2026-07-22 17:29).
    assert "from lib.notify import notify as step_alert" in src
    # failure sink push sits with the pipeline_failures insert
    sink = src[src.index("INSERT INTO pipeline_failures"):]
    assert "step_alert(" in sink[:900], "failure sink must push to the phone"
    assert 'priority="high"' in src
    # stale Kite token at pipeline time -> push
    assert "Kite token STALE" in src


# ── C. token refresh ────────────────────────────────────────────────────────
def test_refresh_kite_token_urgent_alerts():
    src = _read("refresh_kite_token.py")
    assert "from lib.notify import notify" in src
    assert 'priority="urgent"' in src
    # every sys.exit(1) failure path must alert first
    assert src.count("_alert(") >= 3, "all three failure exits must push"


# ── D. rhp_auto (audit #5: no more silent failures) ─────────────────────────
def test_rhp_auto_propagates_failures():
    src = _read("rhp_auto.py")
    assert "failed_steps" in src, "run() results must be collected"
    for step in ('"download"', '"extract"', '"store"'):
        assert f"if not run({step}" in src, f"{step} result ignored"
    assert "sys.exit(1)" in src, "failures must produce a non-zero exit"
    assert "from lib.notify import notify" in src


# ── E. fetch_new_rhps ───────────────────────────────────────────────────────
def test_fetch_new_rhps_alerts_on_total_failure():
    src = _read("fetch_new_rhps.py")
    assert "tried" in src and "if tried > 0 and got == 0" in src
    assert "from lib.notify import notify" in src
    assert "sys.exit(1)" in src
