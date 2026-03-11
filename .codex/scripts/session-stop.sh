#!/usr/bin/env bash
set -euo pipefail

python3 .codex/skills/suggest-skill/scripts/suggest-skill.py || true

if [ -n "${VAULT_DIR:-}" ]; then
    python3 .codex/skills/sync-claude-sessions/scripts/claude-sessions sync || true
fi

if command -v qmd >/dev/null 2>&1; then
    python3 .codex/skills/recall/scripts/extract-sessions.py --output ~/.codex/qmd-sessions --days 9999 || true
    qmd update || true
fi
