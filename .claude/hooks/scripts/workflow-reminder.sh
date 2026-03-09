#!/bin/bash
# workflow-reminder.sh - UserPromptSubmit 훅
# 세션 시작 or 작업 계획 키워드 감지 시 워크플로우 리마인더 출력

WORKFLOW="⚠️ Workflow: /recall → (/brainstorm →) [plan 모드] → /breakdown → [plan 모드 종료] → 구현 → /verify → /wrap → /commit"

SHOW=false

# 1. 세션 시작 감지: CLAUDE_CODE_SSE_PORT는 세션마다 고유
SESSION_ID="${CLAUDE_CODE_SSE_PORT:-unknown}"
SESSION_MARKER="/tmp/claude-wf-${SESSION_ID}"

if [ ! -f "$SESSION_MARKER" ]; then
    touch "$SESSION_MARKER"
    SHOW=true
fi

# 2. 작업 계획 키워드 감지: stdin JSON에서 프롬프트 추출
PROMPT_TEXT=""
if [ ! -t 0 ]; then
    RAW=$(cat)
    PROMPT_TEXT=$(printf '%s' "$RAW" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('prompt', ''))
except Exception:
    pass
" 2>/dev/null || true)
fi

if printf '%s' "$PROMPT_TEXT" | grep -qE '(계획|설계|구현|만들|작성|작업|개발|breakdown|implement|build|create)'; then
    SHOW=true
fi

if [ "$SHOW" = "true" ]; then
    echo "$WORKFLOW"
fi
