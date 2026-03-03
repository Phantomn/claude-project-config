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

# --- 블랙리스트: 위험 패턴 → "ask" (사용자 확인 요구) ---
DANGEROUS_PATTERNS=(
    # 파일 시스템 파괴
    'rm -rf'
    'rm -fr'
    'rmdir'
    'mkfs'
    'format '
    # 디스크 직접 조작
    'dd if='
    'dd of='
    # 권한 남용
    'chmod 777'
    'chmod -R 777'
    'chown -R'
    # 네트워크 위험 (파이프로 쉘 실행)
    'curl.*[|].*sh'
    'wget.*[|].*sh'
    'curl.*[|].*bash'
    'wget.*[|].*bash'
    # 프로세스/시스템
    'kill -9'
    'killall'
    'pkill'
    'shutdown'
    'reboot'
    'systemctl stop'
    'systemctl disable'
    # Git 파괴적 작업
    'git push.*--force'
    'git push.*-f'
    'git reset --hard'
    'git clean -fd'
    'git checkout -- \.'
    # Docker 파괴적 작업
    'docker rm'
    'docker rmi'
    'docker system prune'
    'docker volume rm'
    # 패키지 매니저 (의도치 않은 전역 설치)
    'sudo apt'
    'sudo yum'
    'sudo dnf'
    'sudo pacman'
    'npm install -g'
    'pip install'
    # 환경 변수 오염
    'export PATH='
    'unset PATH'
    # 위험한 리다이렉션 (시스템 파일 덮어쓰기)
    '>/etc/'
    '>>/etc/'
    '>/dev/sd'
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if printf '%s' "$CMD" | grep -qiE "$pattern"; then
        # PreToolUse 공식 포맷: 사용자에게 확인 요청
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"위험 패턴 감지: %s"}}\n' "$pattern"
        exit 0
    fi
done

# --- 블랙리스트에 없으면 자동 승인 ---
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}\n'
exit 0
