#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
    printf 'usage: %s <file>\n' "$0" >&2
    exit 2
fi

file="$1"
ext="${file##*.}"

case "$ext" in
    py)
        python -m py_compile "$file"
        ;;
    sh)
        shellcheck "$file"
        ;;
    json)
        jq empty "$file"
        ;;
    toml)
        python3 - "$file" <<'PY'
import pathlib
import sys
import tomllib

tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
PY
        ;;
    yml|yaml)
        if command -v yamllint >/dev/null 2>&1; then
            yamllint "$file"
        else
            printf 'yamllint not found: %s\n' "$file" >&2
        fi
        ;;
    *)
        printf 'no configured post-edit check for: %s\n' "$file"
        ;;
esac
