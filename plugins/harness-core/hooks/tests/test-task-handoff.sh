#!/usr/bin/env bash
# task-handoff.sh 시험 — 가져오기·원자적 단일 수령·최신 묶음 우선·번호 겹침 보존·env 전달·무동작
# shellcheck disable=SC2016,SC2034  # 검사식은 작은따옴표로 보관했다가 ok() 의 eval 에서 펼친다
set -uo pipefail
S="$(cd "$(dirname "$0")/../scripts" && pwd)/task-handoff.sh"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass + 1)); else echo "FAIL: $1"; fail=$((fail + 1)); fi; }

export HARNESS_TASKS_ROOT="$W/tasks" CLAUDE_CODE_ENTRYPOINT=cli CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1; unset CLAUDE_CODE_TASK_LIST_ID
repo="$W/repo"; mkdir -p "$repo"; key="$(printf %s "$repo" | sed 's/[^A-Za-z0-9]/-/g')"
box="$HARNESS_TASKS_ROOT/handoff/$key"
run() { echo "{\"session_id\":\"$1\",\"cwd\":\"$repo\",\"source\":\"startup\"}" | CLAUDE_ENV_FILE="$W/env.$1" bash "$S"; }
task() { mkdir -p "$1"; echo "{\"id\":\"$2\",\"subject\":\"$3\",\"status\":\"pending\"}" > "$1/$2.json"; }

# 1) 맡긴 것이 없으면 출력 없음, env 는 전달
out="$(run aaaaaaaa-1)"
ok "빈 handoff 무출력" '[ -z "$out" ]'
ok "env 전달" 'grep -q "HARNESS_TASK_LIST_DIR=.*session-aaaaaaaa" "$W/env.aaaaaaaa-1"'

# 2) 묶음 두 개(오래된 old, 최신 new) → 최신만 가져가고 old 는 남는다
task "$box/session-old00000" 1 old; sleep 1; task "$box/session-new00000" 1 new; task "$box/session-new00000" 2 new2
out="$(run bbbbbbbb-2)"
ok "최신 묶음 수령" 'jq -e ".subject==\"new\"" "$HARNESS_TASKS_ROOT/session-bbbbbbbb/1.json" >/dev/null'
ok "2건 수령" '[ "$(ls "$HARNESS_TASKS_ROOT/session-bbbbbbbb" | wc -l)" = 2 ]'
ok "알림 출력" 'jq -e ".hookSpecificOutput.additionalContext | test(\"2건\")" <<<"$out" >/dev/null'
ok "수령분 제거" '[ ! -e "$box/session-new00000" ]'
ok "옛 묶음 보존" '[ -e "$box/session-old00000/1.json" ]'

# 3) 다음 세션이 남은 묶음을 받는다 — 한 번 받으면 다른 세션은 못 받는다
run cccccccc-3 >/dev/null
ok "남은 묶음 수령" 'jq -e ".subject==\"old\"" "$HARNESS_TASKS_ROOT/session-cccccccc/1.json" >/dev/null'
out="$(run dddddddd-4)"
ok "이미 받은 것 재수령 없음" '[ -z "$out" ] && [ ! -e "$HARNESS_TASKS_ROOT/session-dddddddd" ]'
ok "handoff 정리" '[ ! -e "$box" ]'

# 4) 번호가 겹치면 덮어쓰지 않고 원본을 남긴다(resume 처럼 목록에 이미 태스크가 있는 경우)
task "$HARNESS_TASKS_ROOT/session-eeeeeeee" 1 mine; task "$box/session-x0000000" 1 theirs
out="$(run eeeeeeee-5)"
ok "겹침 시 기존 보존" 'jq -e ".subject==\"mine\"" "$HARNESS_TASKS_ROOT/session-eeeeeeee/1.json" >/dev/null'
ok "겹침 보고·원본 보존" 'jq -e ".hookSpecificOutput.additionalContext | test(\"겹쳐\")" <<<"$out" >/dev/null && ls -d "$HARNESS_TASKS_ROOT"/handoff/.claim-* >/dev/null 2>&1'

# 5) 명시 ID 가 있으면 그 목록으로
rm -rf "$box"; task "$box/session-y0000000" 1 named
CLAUDE_CODE_TASK_LIST_ID=named run ffffffff-6 >/dev/null
ok "명시 ID 목록" '[ -e "$HARNESS_TASKS_ROOT/named/1.json" ]'

# 6) 비대화형(-p·SDK)은 가져가지 않고, 목록 경로는 세션 UUID 전체 · agent teams 꺼진 대화형도 UUID 전체
rm -rf "$box"; task "$box/session-z0000000" 1 keep
out="$(CLAUDE_CODE_ENTRYPOINT=sdk-cli run 11111111-7)"
ok "-p 는 안 가져감" '[ -z "$out" ] && [ -e "$box/session-z0000000/1.json" ]'
ok "-p 목록 = UUID 전체" 'grep -q "HARNESS_TASK_LIST_DIR=.*/11111111-7\$" "$W/env.11111111-7"'
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0 run 22222222-8 >/dev/null
ok "teams 꺼진 대화형 = UUID 전체" '[ -e "$HARNESS_TASKS_ROOT/22222222-8/1.json" ]'

# 7) hooks.json 등록
ok "hooks.json 등록" 'jq -e "[.hooks.SessionStart[].hooks[].command] | any(test(\"task-handoff.sh\"))" "$(dirname "$S")/../hooks.json" >/dev/null'

echo "task-handoff: PASS $pass / FAIL $fail"
[ "$fail" -eq 0 ]
