#!/usr/bin/env bash
set -euo pipefail

task_id="${1:-}"
task_subject="${2:-}"
agent="${3:-codex}"

if [ -z "$task_id" ]; then
    printf 'usage: %s <task-id> [subject] [agent]\n' "$0" >&2
    exit 2
fi

log_dir=".codex/logs"
log_file="${log_dir}/agent-team.jsonl"
mkdir -p "$log_dir"

timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$log_file" "$agent" "$task_id" "$task_subject" "$timestamp" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
record = {
    "event": "task_completed",
    "agent": sys.argv[2],
    "task_id": sys.argv[3],
    "task_subject": sys.argv[4],
    "timestamp": sys.argv[5],
}
with path.open("a", encoding="utf-8") as fp:
    fp.write(json.dumps(record, ensure_ascii=False) + "\n")
PY

printf 'task completed logged: %s %s\n' "$task_id" "$task_subject"
