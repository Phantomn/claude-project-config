#!/usr/bin/env python3
"""spec-audit 작업 공간 도구 (stdlib only, Python 3.10+)."""
from __future__ import annotations

import re

Z = 1500
CAP = 5
AXES = ("refs", "selfcontained", "rootcause", "oracle")
EXEC_AXES = AXES[1:]

# (스냅샷 순번 i, a, b) — 1부터, 양끝 포함
Range = tuple[int, int, int]


def axis_lines(targets: list[dict], axis: str) -> list[Range]:
    """축이 맡는 줄 범위. refs = 전부, 다른 축 = role spec·plan만. lines == 0 제외."""
    out: list[Range] = []
    for i, t in enumerate(targets, 1):
        if t["lines"] == 0:
            continue
        if axis != "refs" and t["role"] not in ("spec", "plan"):
            continue
        out.append((i, 1, t["lines"]))
    return out


def shard(ranges: list[Range], z: int = Z) -> list[list[Range]]:
    """범위를 이은 줄을 정확히 z줄마다 자른다(범위·대상 경계를 넘을 수 있음)."""
    shards: list[list[Range]] = []
    cur: list[Range] = []
    room = z
    for i, a, b in ranges:
        while a <= b:
            end = min(b, a + room - 1)
            cur.append((i, a, end))
            room -= end - a + 1
            a = end + 1
            if room == 0:
                shards.append(cur)
                cur, room = [], z
    if cur:
        shards.append(cur)
    return shards


_ORACLE_RE = re.compile(r"^## Reference Oracle\b")


def oracle_needed(text: str) -> bool:
    """코드 펜스 밖 '## Reference Oracle' 절의 첫 비어 있지 않은 줄이 '['로 시작하지 않으면 True."""
    in_fence = False
    in_section = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            if in_section:
                return True  # 펜스 시작 = 비어 있지 않은 줄, '['가 아님
            continue
        if in_fence:
            continue
        if in_section:
            if line.startswith("#"):
                return False
            if line.strip():
                return not line.lstrip().startswith("[")
        elif _ORACLE_RE.match(line):
            in_section = True
    return False


def range_len(rs: list[Range]) -> int:
    return sum(b - a + 1 for _, a, b in rs)


def overlaps(a: list[Range], b: list[Range]) -> bool:
    return any(i == j and x <= v and u <= y for i, x, y in a for j, u, v in b)
