#!/usr/bin/env bash
set -euo pipefail

agent="${1:-}"
completed_task_id="${2:-}"
completed_status="${3:-idle}"

if [ -z "$agent" ]; then
    printf 'usage: %s <agent> [task-id] [status]\n' "$0" >&2
    exit 2
fi

log_dir=".codex/logs"
log_file="${log_dir}/agent-team.jsonl"
mkdir -p "$log_dir"

timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$log_file" "$agent" "$completed_task_id" "$completed_status" "$timestamp" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
record = {
    "event": "teammate_idle",
    "agent": sys.argv[2],
    "completed_task_id": sys.argv[3],
    "completed_status": sys.argv[4],
    "timestamp": sys.argv[5],
}
with path.open("a", encoding="utf-8") as fp:
    fp.write(json.dumps(record, ensure_ascii=False) + "\n")
PY

printf 'teammate idle logged: %s\n' "$agent"
