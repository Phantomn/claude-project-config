#!/usr/bin/env bash
# auto-approve-readonly.sh - PreToolUse 훅: Bash 명령 자동 승인/차단
# permissions.allow에 안 잡히는 복합 명령(파이프라인, heredoc 등)을
# 블랙리스트 방식으로 처리: 위험한 것만 ask, 나머지 전부 allow.
set -euo pipefail

# stdin에서 JSON 입력 읽기
INPUT=$(cat)

# command 필드 추출
if command -v jq >/dev/null 2>&1; then
    CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
    CMD=$(printf '%s' "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | head -1 | sed 's/.*"command"[[:space:]]*:[[:space:]]*"//;s/"$//')
fi

# 명령어가 비어있으면 통과
if [ -z "$CMD" ]; then
    exit 0
fi

# --- [삭제] cd / pushd / popd 차단 (2026-08-05, 사용자 명시 승인) ---
#   ①근거가 거짓이었다. 차단 사유는 "cwd 변경 시 Hook 상대경로가 파손된다" 였는데,
#     settings.json 의 **모든 훅이 스스로** `cd $(git rev-parse --show-toplevel)` 로 시작한다.
#     훅은 자기 프로세스에서 작업 디렉토리를 잡으므로 모델의 cwd 와 무관하다.
#   ②매칭이 명령줄 전체 문자열이라 **인용부호 안 리터럴에도 발화**했다 — 실측: 이 파일을
#     읽으려던 `grep -n 'cd\b|pushd|...' <file>` 이 차단됐다. 도구가 자기 자신을 못 읽었다.
#   절대경로 선호는 이미 시스템 프롬프트가 안내한다. 근거 없는 규칙 + 오탐 ⇒ 판단에 맡긴다.
#   ★재도입한다면 명령 위치로 앵커할 것(줄 시작·체인 구분자 뒤·서브쉘 여는 괄호 뒤).
#     아래 재귀삭제 가드가 그 형태다 — 판정 축을 문자열이 아니라 대상에 둔다.

# --- 코드 파일 읽기 → codegraph/serena 유도 (cat/head/tail/sed -n/grep) ---
CODE_EXT='\.(ts|tsx|py|js|jsx|mjs|cjs|go|rs|java|kt|cpp|c|h)([[:space:]]|$)'
CODE_EXT_TOK='\.(ts|tsx|py|js|jsx|mjs|cjs|go|rs|java|kt|cpp|c|h)$'   # 토큰 추출용(줄 끝 앵커)
CODEGRAPH_HINT="의도에 맞는 도구: codegraph_search(심볼 위치) | codegraph_node(파일 읽기) | codegraph_callers(호출자) | codegraph_callees(피호출자) | codegraph_impact(변경 영향) | codegraph_context(영역 파악) | codegraph_files(디렉토리) | serena find_symbol(심볼 조회)"
CODEREAD_N=3   # 이 횟수 이상이면 넛지 대신 deny. codegraph/serena 호출 시 리셋(reset-coderead-count.sh).

# 명령에서 코드파일 토큰 하나 추출(첫 매치) — deny/넛지 사유에 정확한 대체명령을 채우기 위함.
_extract_codefile() {
    printf '%s' "$1" | tr ' \t|;&' '\n' | grep -oE '[^[:space:]]+'"$CODE_EXT_TOK" | head -1
}

# 코드읽기 게이트: N회 미만은 additionalContext 넛지(allow), N회 이상은 deny. 둘 다 정확한
#   codegraph 대체명령을 사유에 채운다. 상태는 세션 카운터(리셋은 PostToolUse 훅).
# ponytail: 카운터 write 는 병렬 훅 간 race 를 무시한다 — 근사치면 충분하다(정확성 필요 시 flock).
_coderead_gate() {
    local file="$1" cf cnt=0 root tool_hint
    root="$(git rev-parse --show-toplevel 2>/dev/null || printf '%s' "$PWD")"
    cf="$root/.claude/logs/coderead-count"
    if [ -f "$cf" ]; then cnt="$(tr -dc '0-9' < "$cf" 2>/dev/null || true)"; fi
    [ -n "$cnt" ] || cnt=0
    tool_hint="→ 이 파일은 codegraph_node ${file:-<file>} (또는 serena find_symbol). $CODEGRAPH_HINT"
    if [ "$cnt" -ge "$CODEREAD_N" ]; then
        jq -n --arg r "[BLOCKED] bash 코드읽기 ${cnt}회 — codegraph/serena 로 전환하세요. $tool_hint" \
          '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":$r}}'
        exit 0
    fi
    mkdir -p "$(dirname "$cf")" 2>/dev/null || true
    printf '%s\n' "$((10#$cnt + 1))" > "$cf" 2>/dev/null || true
    jq -n --arg c "🔍 코드읽기 $((10#$cnt + 1))/${CODEREAD_N} — codegraph 권장. $tool_hint" \
      '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":$c}}'
    exit 0
}

# ★opt-in — 이 가드는 codegraph/serena 가 실제로 붙은 프로젝트에서만 옳다. 없는 프로젝트에서
#   켜면 "없는 도구를 쓰라"며 bash 를 막는다(헌장: 없는 것을 지시하지 않는다).
#   켜기: 프로젝트 settings.json 의 env 에 HARNESS_CODEREAD_GUARD=1
if [ "${HARNESS_CODEREAD_GUARD:-0}" = "1" ]; then
    # cat/head/tail·sed -n·grep 이 **코드파일을 직접 인자로** 받을 때만 유도(파이프·텍스트필터 통과).
    #   ★grep 은 앞경계에서 `|` 를 뺀다 — `cmd | grep p`(필터)는 통과, 줄시작·;·& 뒤 grep 만.
    #     cat/sed 는 `| cat file` 도 코드읽기라 `|` 포함 앞경계 유지.
    if printf '%s' "$CMD" | grep -qE '(^|[;&|[:space:]])(cat|head|tail)([[:space:]]+-[^[:space:]]+)*[[:space:]]+[^|;&]*'"$CODE_EXT" \
    || printf '%s' "$CMD" | grep -qE '(^|[;&|[:space:]])sed[[:space:]]+(-n|-[a-zA-Z]*n)[[:space:]]+[^|;&]*'"$CODE_EXT" \
    || printf '%s' "$CMD" | grep -qE '(^|[;&][[:space:]]*)grep([[:space:]]+-[^[:space:]]+)*[[:space:]]+[^|;&]*'"$CODE_EXT"; then
        _coderead_gate "$(_extract_codefile "$CMD")"
    fi
fi  # HARNESS_CODEREAD_GUARD

# --- 재귀 삭제: **경로**로 판정한다 (2026-08-05) ------------------------------
# ★왜 명령 형태가 아니라 경로인가.
#   이전 판은 `rm -fr` 리터럴 하나만 막았다 — 즉 `rm -rf <무엇이든>` 은 블랙리스트를 통과해
#   맨 아래 기본 분기에서 **자동 승인**됐다(이 훅은 미매치 시 allow 다). 철자 하나가 권한
#   시스템을 통째로 우회시킨 것이다.
#   그렇다고 `rm -rf` 전부를 막으면 스크래치패드 정리까지 걸려 **과잉 제약**이 된다.
#   ⇒ 축은 "무슨 명령인가"가 아니라 **"무엇을 지우는가"** 다. 지우면 안 되는 것만 막는다.
#
# 2단: 복구 불가능(deny) vs git 으로 복구 가능(ask).
RM_DESTRUCTIVE='(^|[;&|(][[:space:]]*|\bsudo[[:space:]]+)rm[[:space:]]+(-{1,2}[a-zA-Z-]*[rRf][a-zA-Z-]*|--recursive|--force)'

# ★대상 추출 — 아래 판정은 rm 의 **피연산자만** 본다 (2026-08-24 근본fix).
#   종전엔 RM_FATAL/RM_REPO/RM_ABS 를 `$CMD` **전체**에 걸었다. 그래서 실제로 지우는 대상이
#   스크래치패드여도, 같은 줄 **다른 명령의 인자**에 `.git`·`.claude` 리터럴이 있으면 deny 였다.
#   실측 3회 차단: 복구 리허설의 `find … -not -path '*/.git/*'`, 死번들 정리의
#   `git rm -rq --cached .claude/…`, 그리고 이 결함을 진단하려던 명령 자체.
#   `.claude/CLAUDE.md` 헌장 "차단 훅은 명령 문자열이 아니라 **대상**으로 판정한다 — 명령
#   형태로 막으면 인용부호 안 리터럴에까지 발화한다"의 직접 위반이었다(같은 문서가 `cd` 가드
#   에서 이미 밟은 결함이라고 적어 둔 바로 그 형태다).
#   `git rm` 은 대상에서 제외한다 — 인덱스 조작이지 파일시스템 재귀삭제 축이 아니다.
#   한계(명시): 피연산자가 미전개 변수(`"$DIR"`)뿐이면 분류 불가라 ④ 통과로 흐른다.
#     이 가드가 잡는 것은 **리터럴로 적힌 치명 대상**이다.
rm_targets() {
    printf '%s' "$1" \
      | sed -E 's/(\&\&|\|\||;|\|)/\n/g' \
      | sed -E 's/^[[:space:]]+//; s/^sudo[[:space:]]+//' \
      | grep -E '^rm([[:space:]]|$)' \
      | sed -E 's/^rm[[:space:]]*//' \
      | tr ' \t' '\n\n' \
      | grep -vE '^-' | grep -v '^$' \
      | tr '\n' ' '
}

if printf '%s' "$CMD" | grep -qE "$RM_DESTRUCTIVE"; then
    RM_ARGS=" $(rm_targets "$CMD") "
    # 대상이 0개 = 실제로 지우는 것이 없다(인용 리터럴·다른 명령의 하위 rm). 통과.
    if [ -n "$(printf '%s' "$RM_ARGS" | tr -d '[:space:]')" ]; then
    # ① 복구 수단이 없다 — 루트/홈/git 오브젝트/시크릿. 확인이 아니라 거부.
    RM_FATAL='([[:space:]](/|~|\$HOME|\$\{HOME\})([[:space:]]|$|/\*)|/\*([[:space:]]|$)|\.git([[:space:]]|/|$)|\.secrets)'
    if printf '%s' "$RM_ARGS" | grep -qE "$RM_FATAL"; then
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[BLOCKED] 복구 수단이 없는 경로의 재귀 삭제 — 루트/홈/.git/.secrets. 대상을 좁혀 다시 시도하세요."}}\n'
        exit 0
    fi
    # ② 저장소 추적 트리 — git 으로 복구되지만 의도치 않은 삭제는 여전히 비싸다.
    #   ★2026-08-18 복원. `db131d4c`(커밋 메시지는 스킬의 死도구 제거만 기술 · 실제 97파일)가
    #     이 분기와 아래 위험패턴 8종을 **언급 없이** 지웠다. 분기 번호가 ①→③ 으로 뛰고
    #     DANGEROUS_PATTERNS 에 카테고리 헤더만 남은 것이 그 흔적이다.
    #     라이브 실측(복원 전): `rm -rf challenges/anchorwatch` → allow.
    #     `settings.json` 의 `permissions.allow` 에 맨 `Bash` 가 있어 이 훅이 유일한 방어선이다.
    # ★디렉터리 목록은 프로젝트가 정한다 — 저장소마다 트리가 다르다. analysis 는
    #   agent|challenges|research|ctf|tools|.claude 를 settings.json env 로 넘긴다.
    RM_REPO="(^|[[:space:]]|/)(${HARNESS_RM_REPO_DIRS:-src|lib|app|docs|scripts|\.claude})(/|[[:space:]]|$)"
    if printf '%s' "$RM_ARGS" | grep -qE "$RM_REPO"; then
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"저장소 추적 트리의 재귀 삭제 — 대상 확인 필요"}}\n'
        exit 0
    fi
    # ③ 저장소·스크래치 밖의 절대경로 — 무엇을 지우는지 사람이 봐야 한다.
    #   (`/tmp/**` 스크래치패드는 제외 — 세션 임시 산출물이라 통과가 맞다.)
    RM_ABS='[[:space:]](/|~|\$HOME|\$\{HOME\})[^[:space:]]'
    if printf '%s' "$RM_ARGS" | grep -qE "$RM_ABS" && ! printf '%s' "$RM_ARGS" | grep -qE '[[:space:]]/tmp/'; then
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"저장소·스크래치 밖 절대경로의 재귀 삭제 — 대상 확인 필요"}}\n'
        exit 0
    fi
    # ④ 그 외(스크래치패드·상대경로 빌드 산출물 등)는 통과시킨다. 여기서 막으면 과잉 제약이다.
    fi
fi

# --- 블랙리스트: 위험 패턴 → "ask" (사용자 확인 요구) ---
DANGEROUS_PATTERNS=(
    # 파일 시스템 파괴
    # ※재귀 삭제(`rm -rf` 등)는 이 목록이 아니라 **위쪽 경로 가드**가 판정한다.
    #   여기에 명령 형태로 넣으면 스크래치패드 정리까지 걸려 과잉 제약이 된다(실측: 걸렸다).
    #   `rmdir` 은 빈 디렉토리만 지우므로 그대로 둔다.
    'rmdir'
    'mkfs'
    # 디스크 직접 조작
    'dd if='
    'dd of='
    # 권한 남용
    'chmod -R 777'
    # 프로세스/시스템
    'killall'
    'systemctl stop'
    'systemctl disable'
    # Git 파괴적 작업
    'git push.*--force'
    'git push.*-f'
    'git reset --hard'
    'git clean -fd'
    'git checkout -- \.'
    # 위험한 리다이렉션 (시스템 파일 덮어쓰기)
    '>/etc/'
    '>>/etc/'
    '>/dev/sd'
    # 인터프리터 인라인 실행 (python3 -c, node -e 등)
    #'python3?\s+-c'
    #'node\s+-e'
    #'ruby\s+-e'
    #'perl\s+-e'
    # xargs를 통한 파괴적 명령 실행
    'xargs.*rm'
    'xargs.*chmod'
    # tee로 민감한 시스템 경로 덮어쓰기
    'tee\s+/etc/'
    'tee\s+/usr/'
    'tee\s+/bin/'
    'tee\s+/sbin/'
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if printf '%s' "$CMD" | grep -qiE "$pattern"; then
        # PreToolUse 공식 포맷: 사용자에게 확인 요청.
        # ★사유에 **정규식을 그대로 넣는다** — 문자열 연결로 조립하면 JSON 이 깨진다.
        #   실측 2026-08-30: `perl -e` 가 패턴 `perl\s+-e` 에 매치되자 `\s` 가 JSON 에 박혀
        #   "Invalid escape character s" 로 훅 출력이 통째 폐기됐다. 26패턴 중 9개가 같은
        #   상태였다(`\s` 7 · `\.` 1 등). 하필 **위험 매치 시에만** 깨지므로 가드가 가장
        #   필요한 순간에만 증발했다(미매치 경로의 allow 는 리터럴이라 멀쩡했다 = 무증상).
        #   ⇒ 값이 데이터일 때는 인코더에 맡긴다. 위 _deny_codegraph 와 같은 관용구다.
        jq -n --arg p "$pattern" \
          '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":("위험 패턴 감지: " + $p)}}'
        exit 0
    fi
done

# --- 블랙리스트에 없으면 자동 승인 ---
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}\n'
exit 0
