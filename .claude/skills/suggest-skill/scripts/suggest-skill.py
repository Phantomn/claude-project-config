#!/usr/bin/env python3
"""UserPromptSubmit 훅: 현재 프롬프트 컨텍스트 기반 로컬 스킬 추천"""
from __future__ import annotations
import json
import sys
from typing import Optional

RULES: list[tuple[list[str], list[str]]] = [
    # Pentest / 취약점 분석
    (["취약점", "모의해킹", "pentest", "바이너리 분석", "binary analysis", "웹 취약점", "apk 분석", "ipa 분석", "ida", "분석 시작", "대상 분석"], ["/pentest"]),
    (["다음 세션", "세션 이어서", "분석 재개", "세션 로드"], ["/recall", "/pentest"]),
    (["rca", "근본 원인", "발견사항", "취약점 발견", "분석 완료"], ["/wrap", "/pentest"]),
    # General
    (["코드", "수정", "변경", "구현", "작성", "완료", "fix", "edit"], ["/verify"]),
    (["아이디어", "막연", "모르겠", "뭘 만들", "어떻게 시작", "기획"], ["/brainstorm"]),
    (["계획", "단계", "분해", "태스크", "todo"], ["/breakdown"]),
    (["심볼", "함수", "클래스", "아키텍처", "코드 분석"], ["/mcp-analyze"]),
    (["문서", "공식", "라이브러리", "api", "docs"], ["/mcp-docs"]),
    (["검색", "최신", "웹", "찾아봐", "search"], ["/mcp-search"]),
    (["테스트", "e2e", "브라우저", "playwright"], ["/mcp-test"]),
    (["커밋", "commit", "pr ", "push", "깃"], ["/commit"]),
    (["생각", "추론", "전략", "깊이", "구조적"], ["/thinking"]),
    (["병렬", "여러 관점", "패널", "panel"], ["/panel"]),
    (["세션", "마무리", "정리", "끝", "wrap"], ["/wrap"]),
    (["어제", "이전", "히스토리", "recall", "컨텍스트 로드"], ["/recall"]),
    (["어떤 스킬", "어떤 명령", "스킬 찾기"], ["/find-skills"]),
    (["에이전트 팀", "team"], ["/team-assemble"]),
    (["워크트리", "worktree", "브랜치 동기화"], ["/worktree-sync"]),
]


def get_suggestions(prompt: str) -> list[str]:
    prompt_lower = prompt.lower()
    suggestions: list[str] = []
    for keywords, skills in RULES:
        if any(kw in prompt_lower for kw in keywords):
            suggestions.extend(skills)
    return list(dict.fromkeys(suggestions))[:3]


def last_user_prompt(transcript_path: str) -> str:
    """Stop 훅: transcript에서 마지막 사용자 메시지 추출"""
    import pathlib
    try:
        lines = pathlib.Path(transcript_path).read_text().strip().splitlines()
        for line in reversed(lines):
            entry = json.loads(line)
            if entry.get("type") == "user":
                for block in entry.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block["text"]
    except Exception:
        pass
    return ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    if "transcript_path" in data:
        # Stop 훅
        prompt = last_user_prompt(data["transcript_path"])
        label = "다음 단계"
    else:
        # UserPromptSubmit 훅
        prompt = data.get("prompt", "")
        label = "추천 스킬"

    if not prompt:
        return
    suggestions = get_suggestions(prompt)
    if suggestions:
        print(f"💡 {label}: {' | '.join(suggestions)}")


if __name__ == "__main__":
    main()
