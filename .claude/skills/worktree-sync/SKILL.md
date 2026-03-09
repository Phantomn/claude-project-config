---
name: worktree-sync
description: 모든 git worktree를 main 브랜치에서 일괄 rebase
triggers:
  - /worktree-sync
  - worktree sync
  - worktree 동기화
---

# /worktree-sync - Worktree 동기화 스킬

## What
현재 repo의 모든 git worktree를 main 브랜치 기준으로 일괄 rebase한다.
충돌 발생 시 해당 브랜치를 보고하고 중단한다.

## When
- main 브랜치에 공통 스킬/에이전트/CLAUDE.md 변경 후
- 여러 worktree가 main과 동기화가 필요할 때

## Workflow

아래 스크립트를 실행하라:

```bash
bash .claude/skills/worktree-sync/scripts/worktree-sync.sh
```

## Output

성공:
```
Syncing all worktrees with main...

  [dev] rebasing... ✓
  [vuln/os] rebasing... ✓
  [vuln/pentest] rebasing... ✓
  [vuln/sca] rebasing... ✓
  [vuln/ir] rebasing... ✓

All worktrees synced.
```

충돌 시:
```
  [vuln/pentest] rebasing... CONFLICT
Failed: vuln/pentest
Resolve conflicts manually, then run: git rebase --continue
```

## 주의사항
- 각 worktree에서 uncommitted changes가 없어야 함
- 충돌 해결 후 해당 worktree에서 `git rebase --continue` 실행
- main 브랜치 worktree는 자동 스킵
