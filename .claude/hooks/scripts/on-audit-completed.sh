#!/usr/bin/env bash
# on-audit-completed.sh - TaskCompleted 이벤트 핸들러 (OS 점검 완료 알림)
# audit/점검 키워드 태스크 완료 시 결과 아카이브 및 알림 발송
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=hooks-common.sh
. "${SCRIPT_DIR}/hooks-common.sh"

read_stdin_json

task_subject="${TASK_SUBJECT:-$(json_field taskSubject)}"

# audit/점검 키워드 필터
case "$task_subject" in
    *audit*|*점검*|*os-check*|*os_check*) ;;
    *) exit 0 ;;
esac

RESULTS_DIR="${CWD:-.}/results"

# 최신 JSON 결과 파일 탐색
latest_json=""
if [ -d "$RESULTS_DIR" ]; then
    latest_json=$(find "$RESULTS_DIR" -maxdepth 1 -name "*.json" -type f \
        2>/dev/null | sort | tail -1 || true)
fi

# 통계 추출
pass_count=0
fail_count=0
error_count=0
timeout_count=0

if [ -n "$latest_json" ] && [ -f "$latest_json" ]; then
    if command_exists jq; then
        pass_count=$(jq -r '.summary.pass // 0' "$latest_json" 2>/dev/null || printf '0')
        fail_count=$(jq -r '.summary.fail // 0' "$latest_json" 2>/dev/null || printf '0')
        error_count=$(jq -r '.summary.error // 0' "$latest_json" 2>/dev/null || printf '0')
        timeout_count=$(jq -r '.summary.timeout // 0' "$latest_json" 2>/dev/null || printf '0')
    else
        pass_count=$(grep -o '"pass":[0-9]*' "$latest_json" | grep -o '[0-9]*' || printf '0')
        fail_count=$(grep -o '"fail":[0-9]*' "$latest_json" | grep -o '[0-9]*' || printf '0')
    fi
fi

summary_msg="PASS:${pass_count} FAIL:${fail_count} ERROR:${error_count} TIMEOUT:${timeout_count}"
result_file="${latest_json:-없음}"

log_event "audit_completed" \
    "task_subject" "$task_subject" \
    "pass" "$pass_count" \
    "fail" "$fail_count" \
    "error" "$error_count" \
    "timeout" "$timeout_count" \
    "result_file" "$result_file"

send_notification "OS 점검 완료" "$summary_msg | 결과: $result_file"

log_info "OS 점검 완료: $summary_msg"
