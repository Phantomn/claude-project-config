#!/usr/bin/env bash
# guard-read-codefile.sh - PreToolUse(Read) 넛지: 코드파일을 Read 로 읽을 때 codegraph 권고.
#   ★deny 하지 않는다 — Read 를 막으면 codegraph 인덱스에 없는 신규·미인덱스 코드파일까지
#     못 읽는다(사용자 결정 2026-08-30). allow + additionalContext 로 유도만 한다.
#   opt-in: 읽는 파일의 저장소 settings env 에 HARNESS_CODEREAD_GUARD=1 (codegraph/serena 가 붙은 프로젝트만).
#   판정 정의는 code-read-guard.py --root-if-guarded 한 곳(세션 env 만 보면 홈에서 연 세션에서 꺼진다).
set -euo pipefail
command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
[ "$TOOL" = "Read" ] || exit 0
FP=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$FP" ] || exit 0

# 코드파일 확장자만 — 문서·설정·비코드는 무개입(exit 0 = allow as-is).
printf '%s' "$FP" | grep -qE '\.(ts|tsx|py|js|jsx|mjs|cjs|go|rs|java|kt|cpp|c|h)$' || exit 0
python3 "$(dirname "$0")/code-read-guard.py" --root-if-guarded "$FP" >/dev/null || exit 0

# ★도구명: codegraph 1.6 은 codegraph_explore 하나만 기본 노출한다(codegraph_node 등은 CODEGRAPH_MCP_TOOLS 로만).
jq -n --arg c "🔍 코드파일 Read — 전체 통독이 목적이 아니면 심볼 단위가 더 정확·효율적입니다: serena get_symbols_overview(relative_path) → find_symbol(name_path_pattern, include_body=true), 인덱스(.codegraph)가 있으면 codegraph_explore(query=\"$FP\")." \
  '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":$c}}'
exit 0
