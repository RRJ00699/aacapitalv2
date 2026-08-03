#!/usr/bin/env python3
"""WCAG-AA contrast CONTRACT for the light theme: every semantic foreground
token must clear 4.5:1 on every background it can sit on. This killed the
last a11y CI family (green chips, 2026-07-25) and prevents the class."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = open(os.path.join(HERE, "..", "..", "app", "globals.css"), encoding="utf-8").read()


def _lum(h):
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _cr(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_every_light_fg_token_is_AA_on_every_bg():
    light = CSS.split('[data-theme="dark"]')[0]
    t = dict(re.findall(r"--t-([a-zA-Z]+):(#[0-9A-Fa-f]{6})", light))
    bgs = [t[k] for k in ("bg", "surface", "greenBg", "blueBg", "amberBg", "redBg", "grayBg") if k in t]
    fails = []
    for fg in ("text", "sub", "meta", "dim", "green", "blue", "amber", "red", "gold"):
        if fg not in t:
            continue
        for bg in bgs:
            c = _cr(t[fg], bg)
            if c < 4.5:
                fails.append((fg, bg, round(c, 2)))
    assert not fails, f"tokens below WCAG AA 4.5:1: {fails}"
