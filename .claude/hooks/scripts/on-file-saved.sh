#!/usr/bin/env bash
# on-file-saved.sh - PostToolUse: 파일 저장 후 자동 검증
# .sh → shellcheck, .py → py_compile, .json → jq empty
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=hooks-common.sh
. "${SCRIPT_DIR}/hooks-common.sh"

read_stdin_json

file_path="$(json_field "tool_input.file_path")"
[ -z "$file_path" ] && exit 0
[ -f "$file_path" ] || exit 0

ext="${file_path##*.}"

case "$ext" in
    sh)
        if command_exists shellcheck; then
            if ! shellcheck -x "$file_path" 2>/tmp/sc_out; then
                log_warning "shellcheck: $(head -5 /tmp/sc_out)"
            fi
        fi
        ;;
    py)
        if command_exists python3; then
            if ! python3 -m py_compile "$file_path" 2>/tmp/py_out; then
                log_warning "py_compile: $(cat /tmp/py_out)"
            fi
        fi
        ;;
    json)
        if command_exists jq; then
            if ! jq empty "$file_path" 2>/tmp/jq_out; then
                log_warning "jq: $(cat /tmp/jq_out)"
            fi
        fi
        ;;
esac
