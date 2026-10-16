#!/usr/bin/env python3
"""Write·Edit·NotebookEdit 직전에 '이 세션이 손대기 전 상태'를 장부에 기록한다 (spec §3.7 기록 주체 1).

스위치와 무관하게 항상 기록하고, 출력 없음·종료 0. 규칙 본체는 target_class.note_touch.
"""
from __future__ import annotations

import json
import os
import sys

from target_class import make_ctx, note_touch


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read())   # 바이트로 — 텍스트 인코딩에 좌우되지 않게
        ti = payload["tool_input"]
        path = ti.get("file_path") or ti.get("notebook_path")
        if isinstance(path, str) and path:
            if not os.path.isabs(path):
                path = os.path.join(payload.get("cwd") or os.getcwd(), path)
            note_touch(path, make_ctx(payload, os.environ, 3.0), payload.get("tool_name"))
    except Exception:  # noqa: BLE001 — 기록 실패가 도구 호출을 막으면 안 된다
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
