#!/usr/bin/env bash
# task-handoff.sh — SessionStart: /wrap 이 맡겨 둔 미완료 태스크를 이 세션 목록으로 가져온다.
#
# 왜: 태스크 목록은 세션마다 따로다(~/.claude/tasks/session-<세션ID 앞 8자리>, 공식 agent-teams 문서).
#   저장소 고정 ID(CLAUDE_CODE_TASK_LIST_ID)로 잇자 동시에 연 세션끼리 목록이 섞였다(2026-10-02).
#   그래서 목록은 세션별로 두고, 넘기기만 한다: /wrap 이 handoff/<저장소>/<세션목록>/ 에 맡기고,
#   다음에 시작하는 세션 하나가 가장 최근 묶음을 mv(원자적)로 가져간다 — 동시 세션은 못 받는다.
# 또 Bash 에는 세션 ID 가 없어 /wrap 이 자기 목록을 못 찾으므로 HARNESS_TASK_LIST_DIR 로 넘긴다.
set -uo pipefail
command -v jq >/dev/null 2>&1 || { echo "task-handoff: jq 없음 — 건너뜀" >&2; exit 0; }

in="$(cat)"
sid="$(jq -r '.session_id // empty' <<<"$in")"
cwd="$(jq -r '.cwd // empty' <<<"$in")"; cwd="${cwd:-$PWD}"
[ -n "$sid" ] || exit 0

T="${HARNESS_TASKS_ROOT:-$HOME/.claude/tasks}"    # 시험용 덮어쓰기
# 목록 이름(실측 2026-10-02): 명시 ID > 대화형+agent teams 면 팀 이름 session-<앞 8자리> > 그 밖(-p 등)은 세션 UUID 전체
interactive=0; [ "${CLAUDE_CODE_ENTRYPOINT:-}" = cli ] && interactive=1
if [ -n "${CLAUDE_CODE_TASK_LIST_ID:-}" ]; then name="$CLAUDE_CODE_TASK_LIST_ID"
elif [ "$interactive" = 1 ] && [ "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-0}" = 1 ]; then name="session-${sid:0:8}"
else name="$sid"; fi
list="$T/$name"
[ -n "${CLAUDE_ENV_FILE:-}" ] && printf 'export HARNESS_TASK_LIST_DIR=%q\n' "$list" >> "$CLAUDE_ENV_FILE"
# 가져가기는 대화형만 — cron·SDK 의 -p 세션이 사람의 다음 세션 몫을 가로채지 않게
[ "$interactive" = 1 ] || exit 0

# 저장소 키 = git 메인 저장소(worktree 공유), git 밖이면 cwd — 영숫자 외 '-' (메모리 폴더와 같은 규칙)
g="$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" && root="${g%/.git}" || root="$cwd"
box="$T/handoff/$(printf %s "$root" | sed 's/[^A-Za-z0-9]/-/g')"
[ -d "$box" ] || exit 0

# shellcheck disable=SC2012  # 묶음 이름은 session-<hex> 뿐 — mtime 정렬에 ls 가 가장 짧다
src="$(ls -dt "$box"/*/ 2>/dev/null | head -1)"; src="${src%/}"
[ -n "$src" ] || exit 0
claim="$T/handoff/.claim-${box##*/}-${src##*/}-$$"   # box 밖 — 다른 세션이 claim 을 묶음으로 오인하지 않게
mv "$src" "$claim" 2>/dev/null || exit 0      # 동시에 시작한 다른 세션이 먼저 가져갔다
rmdir "$box" 2>/dev/null

mkdir -p "$list"
n=0; skip=""
for f in "$claim"/[0-9]*.json; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"
    if [ -e "$list/$b" ]; then skip="$skip ${b%.json}"; continue; fi
    cp "$f" "$list/" && n=$((n + 1))
done
[ -z "$skip" ] && rm -rf "$claim"            # 겹친 번호가 있으면 claim 폴더를 남겨 수동 복구

msg="이전 세션(${src##*/})이 /wrap 으로 넘긴 미완료 태스크 ${n}건을 이 세션 목록에 가져왔다 — TaskList 로 확인."
[ -n "$skip" ] && msg="$msg 번호가 겹쳐 못 가져온 것:${skip} (원본 $claim)"
jq -n --arg c "$msg" '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$c}}'
exit 0
