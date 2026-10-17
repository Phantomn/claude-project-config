"""bash-guard 스위치 값 (spec §3.9). 표준 라이브러리만 — 판정 대상이 없는 명령의 빠른 길이 큰 모듈 없이 모드를 낸다."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping

MODE_RANK = {"off": 0, "shadow": 1, "on": 2}
# 설정 파일은 있는데 못 읽은 경우(깨진 JSON·권한) — 조용한 off 가 shadow 에서 '켰는데 안 켜짐'으로 보이지 않게 기록에 싣는다(최종 리뷰 M4)
read_failures: list[str] = []


def repo_root(path: str, environ: Mapping[str, str]) -> str | None:
    p = os.path.abspath(path)
    # 루트는 dirname 이 자기 자신인 곳 — POSIX 는 `//` 를 `/` 와 따로 두어 `== "/"` 비교로는 끝나지 않는다(훅 멈춤)
    while True:
        if os.path.lexists(os.path.join(p, ".git")):
            break
        if os.path.dirname(p) == p:
            return None
        p = os.path.dirname(p)
    home = environ.get("HOME")
    if os.path.dirname(p) == p or (home and os.path.realpath(home) == os.path.realpath(p)):
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
        except (OSError, ValueError, AttributeError) as e:
            if not isinstance(e, FileNotFoundError):
                read_failures.append(f".claude/{name}: {type(e).__name__}")
            continue
        if isinstance(env, dict) and "HARNESS_BASH_GUARD" in env:
            v = env["HARNESS_BASH_GUARD"]
            return v if isinstance(v, str) and v in MODE_RANK else "off"
    return "off"
