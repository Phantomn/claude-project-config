#!/usr/bin/env bash
# qmd-no-rerank.sh — PreToolUse(mcp__qmd__query): rerank 를 항상 끈다.
#
# 왜: qmd MCP query 는 rerank 기본 true(src/mcp/server.ts)인데, 한국어 코퍼스 실측(27문항, qmd bench)에서
#   hybrid(rerank 끔) recall@5 0.815 > full(rerank 켬) 0.593 — rerank 가 나아지게 한 질문 0개, 나빠진 질문 6개.
#   /recall 은 CLI --no-rerank 라 무관, MCP 경로만 노출. 모델이 true 를 넘겨도 덮어쓴다(이긴 사례가 없음).
#
# @experimental  Owner: phantom · Start: 2026-10-02 · Expiry: 2026-12-31
# Removal criteria: upstream tobi/qmd#1031 이 기본값을 false 로 바꾸거나 설정으로 끌 수 있게 되면 이 훅을 지우고
#   그 설정을 쓴다. 만료일에 재측정(~/.agents/qmd/bench-light.mjs fx-all hybrid,full)해 full ≥ hybrid 면 제거.
set -uo pipefail
command -v jq >/dev/null 2>&1 || { echo "qmd-no-rerank: jq 없음 — 건너뜀" >&2; exit 0; }
jq -c '{hookSpecificOutput: {hookEventName: "PreToolUse", updatedInput: ((.tool_input // {}) + {rerank: false})}}'
exit 0
