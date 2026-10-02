#!/usr/bin/env bash
# qmd-no-rerank.sh 시험 — rerank 강제 false · 다른 인자 보존 · 인자 없음 처리 · hooks.json 등록
set -uo pipefail
S="$(cd "$(dirname "$0")/../scripts" && pwd)/qmd-no-rerank.sh"
pass=0; fail=0
ok() { if [ "$2" = "$3" ]; then pass=$((pass + 1)); else echo "FAIL: $1 — got [$2] want [$3]"; fail=$((fail + 1)); fi; }
run() { printf '%s' "$1" | bash "$S"; }

out="$(run '{"tool_name":"mcp__qmd__query","tool_input":{"query":"q","rerank":true,"limit":5,"collections":["wiki"]}}')"
ok "true → false" "$(jq -r .hookSpecificOutput.updatedInput.rerank <<<"$out")" false
ok "다른 인자 보존" "$(jq -c '.hookSpecificOutput.updatedInput | [.query,.limit,.collections]' <<<"$out")" '["q",5,["wiki"]]'
ok "이벤트 이름" "$(jq -r .hookSpecificOutput.hookEventName <<<"$out")" PreToolUse
ok "권한 결정은 건드리지 않음" "$(jq -r '.hookSpecificOutput.permissionDecision // "none"' <<<"$out")" none
out="$(run '{"tool_name":"mcp__qmd__query","tool_input":{"query":"q"}}')"
ok "생략 → false" "$(jq -r .hookSpecificOutput.updatedInput.rerank <<<"$out")" false
out="$(run '{"tool_name":"mcp__qmd__query"}')"
ok "tool_input 없음" "$(jq -c .hookSpecificOutput.updatedInput <<<"$out")" '{"rerank":false}'
ok "hooks.json 등록" "$(jq -r '[.hooks.PreToolUse[] | select(.matcher=="mcp__qmd__query") | .hooks[].command] | any(test("qmd-no-rerank.sh"))' "$(dirname "$S")/../hooks.json")" true

echo "qmd-no-rerank: PASS $pass / FAIL $fail"
[ "$fail" -eq 0 ]
