#!/usr/bin/env bash
# symbol-tools.sh <serena|prompt|rule|allow> — serena·codegraph 연동 훅 4종.
# ★왜 플러그인에 있나 (2026-10-02). 이전엔 프로젝트 14곳의 settings.json 에 hook 2개·allow 1줄·rule 심링크를
#   복사해 두었다(정의 복사 = 갈라짐). 정의는 여기 한 벌, 프로젝트엔 스위치 1줄(HARNESS_CODEREAD_GUARD=1)만 둔다.
#   코드읽기 차단(auto-approve-readonly.sh)과 같은 스위치다 — 차단만 켜고 대체 도구 안내를 빼면 모순이므로 한 묶음.
# 꺼져 있거나 도구가 없으면 아무것도 출력하지 않는다(exit 0 = 개입 없음).
set -uo pipefail
[ "${HARNESS_CODEREAD_GUARD:-0}" = "1" ] || exit 0

case "${1:-}" in
    serena)   # SessionStart: serena 프로젝트 활성화 안내
        command -v serena-hooks >/dev/null 2>&1 || { echo "symbol-tools: serena-hooks 없음 — 건너뜀" >&2; exit 0; }
        exec serena-hooks activate --client claude-code ;;
    prompt)   # UserPromptSubmit: 구조 질문에 codegraph 맥락 주입
        command -v codegraph >/dev/null 2>&1 || { echo "symbol-tools: codegraph 없음 — 건너뜀" >&2; exit 0; }
        exec codegraph prompt-hook ;;
    rule)     # SessionStart: 인덱스가 있는 저장소에만 codegraph 우선 규칙 주입
        cat >/dev/null
        [ -d "${CLAUDE_PROJECT_DIR:-$PWD}/.codegraph" ] || exit 0
        command -v jq >/dev/null 2>&1 || { echo "symbol-tools: jq 없음 — rule 주입 건너뜀" >&2; exit 0; }
        jq -n --rawfile c "$(dirname "$0")/../../context/codegraph.md" \
          '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$c}}' ;;
    allow)    # PreToolUse(mcp__codegraph__*): 읽기 전용 도구라 승인 프롬프트 없이 허용
        cat >/dev/null
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}\n' ;;
    *) echo "symbol-tools: 알 수 없는 모드 '${1:-}'" >&2 ;;
esac
exit 0
