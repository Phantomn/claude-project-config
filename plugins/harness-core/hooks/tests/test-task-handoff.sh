#!/usr/bin/env bash
# task-handoff.sh 시험 — 묶음 수령(새 파일 형식·예전 폴더 형식)·최신 우선·단일 수령·완료 제외·빈/깨진 묶음·-p 미수령·등록
# shellcheck disable=SC2016,SC2034,SC2028  # 검사식은 작은따옴표로 보관했다가 ok() 의 eval 에서 펼친다 · \n 은 JSON 이스케이프 그대로
set -uo pipefail
S="$(cd "$(dirname "$0")/../scripts" && pwd)/task-handoff.sh"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass + 1)); else echo "FAIL: $1"; fail=$((fail + 1)); fi; }

export HARNESS_TASKS_ROOT="$W/tasks" CLAUDE_CODE_ENTRYPOINT=cli
repo="$W/repo"; mkdir -p "$repo"; key="$(printf %s "$repo" | sed 's/[^A-Za-z0-9]/-/g')"
box="$HARNESS_TASKS_ROOT/handoff/$key"
run() { echo "{\"session_id\":\"x\",\"cwd\":\"$repo\",\"source\":\"${1:-startup}\"}" | bash "$S"; }
ctx() { jq -r '.hookSpecificOutput.additionalContext' <<<"$1"; }

# 1) 맡긴 것이 없으면 출력 없음
out="$(run)"; ok "빈 handoff 무출력" '[ -z "$out" ]'

# 2) 새 형식(파일) 두 묶음 → 최신만, 완료 항목 제외, 등록 지시 포함
mkdir -p "$box"
echo '[{"subject":"old-task","description":"d","status":"pending"}]' > "$box/1-old.json"; sleep 1
echo '[{"subject":"new-a","description":"line1\nline2","status":"pending"},{"subject":"new-done","description":"","status":"completed"},{"subject":"new-b","description":"","status":"in_progress"}]' > "$box/2-new.json"
out="$(run)"
ok "최신 묶음 수령" '[[ $(ctx "$out") == *new-a* ]] && [[ $(ctx "$out") != *old-task* ]]'
ok "완료 항목 제외·건수" '[[ $(ctx "$out") != *new-done* ]] && [[ $(ctx "$out") == *"2건"* ]]'
ok "TaskCreate 지시" '[[ $(ctx "$out") == *TaskCreate* ]]'
ok "in_progress 표시" '[[ $(ctx "$out") == *"[in_progress] new-b"* ]]'
ok "수령분 제거·옛 묶음 보존" '[ ! -e "$box/2-new.json" ] && [ -e "$box/1-old.json" ]'

# 3) 다음 세션이 남은 묶음을 받는다(resume 포함) — 다 받으면 box 정리, 재수령 없음
out="$(run resume)"; ok "resume 도 수령" '[[ $(ctx "$out") == *old-task* ]]'
ok "box 정리" '[ ! -e "$box" ]'
out="$(run)"; ok "재수령 없음" '[ -z "$out" ]'

# 4) 예전 형식(태스크 JSON 파일 폴더)도 받는다
mkdir -p "$box/session-legacy"; echo '{"id":"3","subject":"legacy","description":"x","status":"pending"}' > "$box/session-legacy/3.json"
printf 32 > "$box/session-legacy/.highwatermark"; : > "$box/session-legacy/.lock"   # 실제 목록 폴더엔 이 파일들도 있다
out="$(run)"; ok "예전 폴더 형식 수령" '[[ $(ctx "$out") == *legacy* ]] && [ ! -e "$box" ]'

# 5) 빈 묶음은 건너뛰고 다음 것, 깨진 묶음은 원본 보존 후 건너뜀
mkdir -p "$box/session-empty"; echo 'not json' > "$box/9-broken.json"; sleep 1
echo '[{"subject":"after","description":"","status":"pending"}]' > "$box/0-good.json"; touch -d '2 minutes ago' "$box/0-good.json"
out="$(run 2>/dev/null)"
ok "빈·깨진 묶음 건너뛰고 수령" '[[ $(ctx "$out") == *after* ]]'
ok "깨진 묶음 원본 보존" 'ls "$HARNESS_TASKS_ROOT"/handoff/.claim-*9-broken* >/dev/null 2>&1'

# 6) 비대화형(-p·SDK)은 가져가지 않는다
mkdir -p "$box"; echo '[{"subject":"keep","description":"","status":"pending"}]' > "$box/k.json"
out="$(CLAUDE_CODE_ENTRYPOINT=sdk-cli run)"; ok "-p 는 안 가져감" '[ -z "$out" ] && [ -e "$box/k.json" ]'

# 7) 등록 — hooks.json 이 가리키는 모든 스크립트가 존재하고 git 에 추적된다(PR #10: 새 파일이 경로 지정 커밋에서 빠져 훅이 없는 파일을 가리켰다)
H="$(dirname "$S")/.."
ok "hooks.json 에 task-handoff 등록" 'jq -e "[.hooks.SessionStart[].hooks[].command] | any(test(\"task-handoff.sh\"))" "$H/hooks.json" >/dev/null'
miss=""; for f in $(jq -r '.. | .command? // empty' "$H/hooks.json" | grep -o 'hooks/scripts/[A-Za-z0-9._-]*' | sort -u); do
    p="$H/../$f"; [ -f "$p" ] && git -C "$H" ls-files --error-unmatch "$p" >/dev/null 2>&1 || miss="$miss $f"
done
ok "훅 스크립트 전부 존재·git 추적(미추적:${miss:- 없음})" '[ -z "$miss" ]'

echo "task-handoff: PASS $pass / FAIL $fail"
[ "$fail" -eq 0 ]
