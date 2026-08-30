#!/usr/bin/env bash
# reset-coderead-count.sh - PostToolUse: codegraph/serena 도구 호출 시 코드읽기 카운터 리셋.
#   auto-approve-readonly.sh 의 소프트 카운터($ROOT/.claude/logs/coderead-count)를 지운다(=0).
#   → codegraph/serena 를 쓰면 bash 코드읽기 예산이 회복된다(serena 공식 모델). PostToolUse 라
#     판정하지 않는다 — 부작용(리셋)만. fail-open.
set -euo pipefail
command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
# ★실제 코드탐색 도구만 리셋한다 — codegraph_status·codegraph_files·serena list_memories 등
#   no-op/메타 호출로 카운터가 리셋되면 "3회 읽기 + no-op MCP 1회" 반복으로 DENY 가 무력화된다
#   (적대검증 2026-08-30 관점5). 코드를 실제로 조회한 호출에만 예산을 회복시킨다.
case "$TOOL" in
  mcp__codegraph__codegraph_search|mcp__codegraph__codegraph_node|mcp__codegraph__codegraph_context \
  |mcp__codegraph__codegraph_callers|mcp__codegraph__codegraph_callees|mcp__codegraph__codegraph_impact \
  |mcp__serena__find_symbol|mcp__serena__find_referencing_symbols|mcp__serena__get_symbols_overview \
  |mcp__serena__search_for_pattern) ;;
  *) exit 0 ;;
esac

root="$(git rev-parse --show-toplevel 2>/dev/null || printf '%s' "$PWD")"
rm -f "$root/.claude/logs/coderead-count" 2>/dev/null || true
exit 0
