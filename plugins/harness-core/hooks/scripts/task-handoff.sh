#!/usr/bin/env bash
# task-handoff.sh — SessionStart: /wrap 이 맡겨 둔 미완료 태스크를 이 세션에 넘긴다(모델이 TaskCreate 로 등록).
#
# 왜 이런 구조인가(2026-10-02 실측):
#   - 태스크 목록은 세션마다 따로다. 저장소 고정 CLAUDE_CODE_TASK_LIST_ID 로 잇자 동시 세션끼리 섞였다 → 폐기.
#   - 목록 폴더를 직접 옮기려 했으나, resume 하면 Claude Code 가 목록 ID 를 새로 발급하면서 hook·Bash·
#     ~/.claude/sessions/<pid>.json 어디에도 알려 주지 않는다(전부 대화 ID). 그래서 폴더 경로로는 resume 에서
#     엉뚱한 목록에 넣게 된다. 실제 목록을 확실히 아는 것은 Task 도구뿐이다.
#   → /wrap 이 TaskList/TaskGet 으로 읽은 미완료를 handoff/<저장소키>/<묶음>.json 에 맡기고, 이 hook 은 묶음을
#     mv(원자적)로 하나 가져가 내용을 세션 첫 맥락에 넣는다. 모델이 TaskCreate 로 등록 → 어느 세션 ID 체계든 맞는 목록.
# 묶음 형식: [{"subject","description","status"}] JSON 배열. 예전 형식(태스크 JSON 파일들이 든 폴더)도 받는다.
# 대화형(CLAUDE_CODE_ENTRYPOINT=cli)만 가져간다 — cron·SDK 의 -p 세션이 사람 몫을 가로채지 않게.
set -uo pipefail
command -v jq >/dev/null 2>&1 || { echo "task-handoff: jq 없음 — 건너뜀" >&2; exit 0; }
[ "${CLAUDE_CODE_ENTRYPOINT:-}" = cli ] || { cat >/dev/null; exit 0; }

in="$(cat)"
cwd="$(jq -r '.cwd // empty' <<<"$in")"; cwd="${cwd:-$PWD}"
T="${HARNESS_TASKS_ROOT:-$HOME/.claude/tasks}"    # 시험용 덮어쓰기

# 저장소 키 = git 메인 저장소(worktree 공유), git 밖이면 cwd — 영숫자 외 '-' (메모리 폴더·/wrap 과 같은 규칙)
g="$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" && root="${g%/.git}" || root="$cwd"
box="$T/handoff/$(printf %s "$root" | sed 's/[^A-Za-z0-9]/-/g')"
[ -d "$box" ] || exit 0

while :; do
    # shellcheck disable=SC2012  # 묶음 이름은 우리가 만든 것뿐 — mtime 정렬에 ls 가 가장 짧다
    src="$(ls -dt "$box"/* 2>/dev/null | head -1)"
    [ -n "$src" ] || { rmdir "$box" 2>/dev/null; exit 0; }
    claim="$T/handoff/.claim-${box##*/}-$(basename "$src")-$$"   # box 밖 — 다른 세션이 claim 을 묶음으로 오인하지 않게
    # 실패 사유가 "다른 세션이 먼저 가져감"이면 src 가 사라져 있다 → 다음 묶음. 그대로면 다른 이유(권한 등) — 반복하지 않고 멈춘다.
    mv "$src" "$claim" 2>/dev/null || { [ -e "$src" ] && { echo "task-handoff: 묶음을 가져올 수 없음 — $src" >&2; exit 0; }; continue; }
    if [ -d "$claim" ]; then
        tasks="$(find "$claim" -maxdepth 1 -name '[0-9]*.json' -exec cat {} + 2>/dev/null \
                 | jq -s '[.[] | select(.status != "completed") | {subject, description, status}]' 2>/dev/null)"
    else
        tasks="$(jq '[.[] | select(.status != "completed") | {subject, description, status}]' "$claim" 2>/dev/null)"
    fi
    n="$(jq 'length' <<<"${tasks:-[]}" 2>/dev/null || echo 0)"
    if [ -z "$tasks" ] || [ "$n" = 0 ]; then
        if [ -z "$tasks" ]; then echo "task-handoff: 읽을 수 없는 묶음 — 원본 보존 $claim" >&2; else rm -rf "$claim"; fi
        continue                                                  # 빈·깨진 묶음은 건너뛰고 다음 것
    fi
    # 지우지 않고 보관 — 받은 세션이 등록 전에 끝나도(resume 직후 종료 등) 되살릴 수 있게. 30일 지나면 정리.
    done_dir="$T/handoff/.done"; mkdir -p "$done_dir"
    kept="$done_dir/${box##*/}-$(basename "$src")-$(date +%Y%m%d%H%M%S)"
    mv "$claim" "$kept" 2>/dev/null || kept="$claim"
    find "$done_dir" -mindepth 1 -maxdepth 1 -mtime +30 -exec rm -rf {} + 2>/dev/null
    rmdir "$box" 2>/dev/null
    break
done

ctx="$(jq -r --arg n "$n" --arg kept "$kept" '"이전 세션이 /wrap 으로 넘긴 미완료 작업 \($n)건이다. 사용자 요청을 처리하기 전에 아래 각 항목을 TaskCreate 로 등록하라(subject·description 그대로, status 가 in_progress 면 등록 후 TaskUpdate 로 in_progress). 등록했다고 한 줄로 알려라. (원본 보관: \($kept))\n\n" + ([to_entries[] | "\(.key + 1). [\(.value.status)] \(.value.subject)\n   \((.value.description // "") | gsub("\n"; "\n   "))"] | join("\n"))' <<<"$tasks")"
jq -n --arg c "$ctx" '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$c}}'
exit 0
