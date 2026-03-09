#!/usr/bin/env bash
# worktree-sync: 모든 worktree를 main에서 rebase
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "Syncing all worktrees with main..."
echo ""

FAILED=""

while IFS= read -r line; do
  wt_path=$(echo "$line" | awk '{print $1}')
  branch=$(git -C "$wt_path" branch --show-current 2>/dev/null || true)

  [ "$branch" = "main" ] && continue
  [ -z "$branch" ] && continue

  printf "  [%s] rebasing... " "$branch"
  if git -C "$wt_path" rebase main --quiet 2>/dev/null; then
    printf "%b✓%b\n" "$GREEN" "$NC"
  else
    printf "%bCONFLICT%b\n" "$RED" "$NC"
    FAILED="$FAILED $branch"
  fi
done < <(git worktree list | tail -n +2)

echo ""
if [ -n "$FAILED" ]; then
  echo "Failed:$FAILED"
  echo "Resolve conflicts manually, then run: git rebase --continue"
  exit 1
fi

echo "All worktrees synced."
