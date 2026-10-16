"""bash-guard 스위치 값 (spec §3.9). 표준 라이브러리만 — 판정 대상이 없는 명령의 빠른 길이 큰 모듈 없이 모드를 낸다."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping

MODE_RANK = {"off": 0, "shadow": 1, "on": 2}


def repo_root(path: str, environ: Mapping[str, str]) -> str | None:
    p = os.path.abspath(path)
    while True:
        if os.path.lexists(os.path.join(p, ".git")):
            break
        if p == "/":
            return None
        p = os.path.dirname(p)
    home = environ.get("HOME")
    if p == "/" or (home and os.path.realpath(home) == os.path.realpath(p)):
        return None
    return p


def switch_mode(path: str | None, environ: Mapping[str, str]) -> str:
    root = repo_root(path, environ) if path else None
    if root is None:
        return "off"
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(root, ".claude", name), encoding="utf-8") as f:
                env = json.load(f).get("env")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(env, dict) and "HARNESS_BASH_GUARD" in env:
            v = env["HARNESS_BASH_GUARD"]
            return v if isinstance(v, str) and v in MODE_RANK else "off"
    return "off"
