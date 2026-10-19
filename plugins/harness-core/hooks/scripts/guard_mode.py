"""bash-guard 스위치 값 (spec §3.9). 표준 라이브러리만 — 판정 대상이 없는 명령의 빠른 길이 큰 모듈 없이 모드를 낸다."""
from __future__ import annotations

import json
import os
import re
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


def setting(root: str, key: str) -> object:
    """대상 저장소 `.claude/settings.local.json` → `settings.json` 순으로 처음 나오는 env[key]. 없으면 None."""
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(root, ".claude", name), encoding="utf-8") as f:
                env = json.load(f).get("env")
        except (OSError, ValueError, AttributeError) as e:
            if not isinstance(e, FileNotFoundError):
                read_failures.append(f".claude/{name}: {type(e).__name__}")
            continue
        if isinstance(env, dict) and key in env:
            return env[key]
    return None


def switch_mode(path: str | None, environ: Mapping[str, str]) -> str:
    root = repo_root(path, environ) if path else None
    v = setting(root, "HARNESS_BASH_GUARD") if root else None
    return v if isinstance(v, str) and v in MODE_RANK else "off"


ALLOW_DELETE = "HARNESS_BASH_GUARD_ALLOW_DELETE"


def allow_delete_patterns(root: str, environ: Mapping[str, str]) -> list[tuple[str, str]]:
    """삭제 허용 목록(`:` 구분, `*` 글롭, 절대 또는 root 상대) → (원문, 정규화한 절대 패턴). 읽기 실패·깨진 값은 빈 목록(허용 안 함)."""
    n = len(read_failures)
    v = setting(root, ALLOW_DELETE)
    if len(read_failures) > n or v is None:   # 허용을 넓히는 값이라 설정 파일 하나라도 못 읽으면 다음 파일로 넘어가지 않는다
        return []
    if not isinstance(v, str):
        read_failures.append(f"{ALLOW_DELETE}: 문자열이 아니다")
        return []
    home, base = os.path.realpath(environ.get("HOME") or "/"), os.path.realpath(root)
    out = []
    for pat in filter(None, (x.strip() for x in v.split(":"))):
        full = os.path.realpath(os.path.join(base, pat))
        fixed = os.path.dirname(re.split(r"[*?[]", full, maxsplit=1)[0] + "x")   # 글롭 앞의 고정 폴더
        # 글롭이 '/'·홈 아래 전부, 또는 프로젝트 루트 아래 이름 전부(`*`·`**/*`)를 덮으면 거부
        if re.search(r"[*?[]", full) and (fixed in ("/", home) or (fixed == base and not os.path.basename(full).strip("*?"))):
            read_failures.append(f"{ALLOW_DELETE}: 전체를 덮는 패턴 거부: {pat}")
            continue
        out.append((pat, full))
    return out
