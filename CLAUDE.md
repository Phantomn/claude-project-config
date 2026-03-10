# claude-project-config
Claude Code 범용 프로젝트 템플릿 저장소. Skills, Agents, Hooks 제공.
**중요**: 이 파일은 이 프로젝트 고유 설정. `.claude/CLAUDE.md`와 `~/.claude/CLAUDE.md`는 동기화 유지.

## Tech Stack
- **Language**: Markdown, Shell (Bash), Python 3.10+, JSON
- **Linting**: shellcheck, ruff, py_compile, markdownlint, jq, yamllint

## Commands
```bash
# Shell 스크립트 검증
find .claude/skills -name "*.sh" -exec shellcheck {} \;
shellcheck .claude/hooks/scripts/*.sh

# Python 구문 검증
find .claude -name "*.py" -exec python -m py_compile {} \;

# JSON 유효성
jq empty .claude/*.json

# 전체 검증 (순차)
shellcheck .claude/skills/verify/scripts/*.sh && \
shellcheck .claude/hooks/scripts/*.sh && \
python -m py_compile .claude/skills/wrap/scripts/*.py && \
jq empty .claude/*.json
```

## Code Style

### We Use
- **Shell**: `set -euo pipefail`, 색상 변수, 함수 분리
- **Python**: 타입 힌트, pathlib, dataclass, 3.10+ 호환
- **SKILL.md**: YAML frontmatter (name, description, triggers) 필수

### We Avoid
- **Shell**: Bash 전용 → POSIX 호환 권장 (`[[` → `[`, `echo -e` → `printf`)
  - 현재 verify-*.sh에 `[[` 사용 중 - 점진적 마이그레이션 예정
- **Python**: `os.path` → `pathlib.Path`, 3.12+ 전용 문법 지양
- **하드코딩된 경로**: `$(dirname "$0")` 또는 `pathlib.Path(__file__).parent` 사용

## Architecture
```
.claude/
├── CLAUDE.md           # 프로젝트 설정 (~/.claude/CLAUDE.md와 동기화)
├── README.md           # 프로젝트 설명
├── settings.json       # 훅 + 권한 설정 (PreToolUse, PostToolUse, TeammateIdle, TaskCompleted)
├── settings.local.json # 로컬 전용 설정 (.gitignore)
├── extensions/         # Progressive Disclosure 확장 문서
│   ├── modes/          # brainstorming, deep-research, token-efficiency
│   └── mcp/            # context7, serena, tavily, ida
├── hooks/scripts/      # 훅 스크립트 (settings.json에서 참조)
│   ├── auto-approve-readonly.sh # PreToolUse: 블랙리스트 기반 자동 승인/차단
│   ├── hooks-common.sh     # 공통 유틸 (로깅, 알림, 진행률)
│   ├── on-teammate-idle.sh # TeammateIdle 핸들러
│   └── on-task-completed.sh # TaskCompleted 핸들러
├── logs/               # 훅 로그 (JSONL, .gitignore 처리)
├── memory/             # Auto Memory (MEMORY.md, 로컬 전용)
├── agents/             # 역할 기반 에이전트 (7개, Agent Teams 지원)
│   ├── implementer.md  # 구현 (sonnet, acceptEdits)
│   ├── reviewer.md     # 리뷰 (sonnet, plan)
│   ├── planner.md      # 계획 (opus, plan)
│   ├── code-analyzer.md # Serena+Sequential 분석 (sonnet, plan)
│   ├── docs-researcher.md # Context7 문서 조회 (haiku, plan)
│   ├── web-researcher.md  # Tavily 웹 검색 (haiku, plan)
│   └── doc-writer.md   # 문서 작성 (sonnet, acceptEdits)
└── skills/             # Progressive Disclosure 스킬 (17개)
    ├── brainstorm/     # /brainstorm 요구사항 발견 (소크라테스 대화)
    ├── breakdown/      # /breakdown 작업 계획
    ├── commit/         # /commit Git 커밋 자동화
    ├── find-skills/    # /find-skills 스킬 검색
    ├── notebooklm/     # /notebooklm NotebookLM 연동
    ├── panel/          # /panel N-Agent Panel 분석
    ├── recall/         # /recall 세션/문서 컨텍스트 로드
    ├── sync-claude-sessions/ # /sync-claude-sessions Obsidian 동기화
    ├── tasknotes/      # /tasknotes 작업 관리
    ├── team-assemble/  # /team-assemble 에이전트 팀 조립
    ├── thinking/       # /thinking 구조적 사고 전략 (9가지)
    ├── verify/         # /verify 언어별 검증 스크립트
    ├── wrap/           # /wrap 학습 추출
    └── mcp-*/          # MCP 격리 스킬 (analyze, docs, search, test)
```

## Gotchas

### CLAUDE.md 동기화 누락
- **함정**: `.claude/CLAUDE.md`와 `~/.claude/CLAUDE.md`를 개별 수정하여 내용 불일치
- **대안**: 한쪽 수정 후 반드시 다른 쪽에 동기화. 두 파일은 항상 동일 내용 유지

### Skills/Agents 무분별 수정
- **함정**: 다른 프로젝트에서 사용 중인 스킬/에이전트 임의 수정
- **대안**: 수정 전 영향 범위 확인, 범용성 유지

### Shell 스크립트 Bash 전용 문법
- **함정**: `[[ ]]`, `echo -e`, array 사용 (현재 verify-*.sh에 존재)
- **대안**: 신규 스크립트는 POSIX 호환 권장, 기존은 점진적 마이그레이션

### Python 버전 호환
- **함정**: match-case, 새 타입 힌트 등 3.12+ 전용 문법
- **대안**: 3.10+ 호환 유지, `from __future__ import annotations`

### MEMORY.md vs CLAUDE.md Lessons Learned 혼동
- **함정**: MEMORY.md에 팀 공유 규칙 작성, 또는 CLAUDE.md에 로컬 메모리 작성
- **대안**: CLAUDE.md Lessons Learned = 팀 공유 (Git 추적), MEMORY.md = Claude 자동 참조 지식 (로컬, 200줄 제한)

### Agent Teams 비용
- **함정**: 팀원 5명 스폰 시 토큰 ~7배 증가
- **대안**: 최소 팀원 수 유지, Sonnet/Haiku 모델 사용, 완료 후 즉시 정리

### 스킬 이름과 내장 명령 충돌
- **함정**: 스킬 이름이 Claude Code 내장 명령(`plan`, `help` 등)과 동일하면 스킬 호출 불가
- **대안**: 충돌 시 이름 변경 (예: `plan` → `breakdown`)

### 훅 설정 위치
- **함정**: `.claude/hooks.json` 파일에 훅 정의 (Claude Code가 인식하지 않음)
- **대안**: 모든 훅은 `settings.json`의 `hooks` 필드에 정의. PreToolUse 출력은 `hookSpecificOutput.permissionDecision` 포맷 필수

### 템플릿(.claude/CLAUDE.md)에 프로젝트 특정 내용 추가
- **함정**: Gotchas/Lessons Learned를 `.claude/CLAUDE.md`(템플릿)에 추가하면 다른 프로젝트 복사 시 오염
- **대안**: 이 프로젝트 고유 내용은 루트 `CLAUDE.md`에, 범용 규칙만 `.claude/CLAUDE.md`에 작성

### Worktree 도입 시 3중 동기화 주의
- **함정**: `.claude/CLAUDE.md`(템플릿) ↔ `~/.claude/CLAUDE.md`(전역) ↔ 각 브랜치 CLAUDE.md를 각각 수정하면 불일치 발생
- **대안**: 공통 수정은 main에서만, 카테고리 전용은 해당 브랜치에서만 수정

### Worktree 스킬 중복 증식 경계
- **함정**: 5개 worktree에 동일 스킬 복붙 시 파일 5배 증가
- **대안**: main에서 공통 스킬 유지, 각 브랜치에 카테고리 전용 차분(diff)만 추가

### 훅 스크립트 전역 경로 사용
- **함정**: `settings.json`에서 `~/.claude/hooks/` 절대 경로 사용 → 다른 환경 복사 시 파일 없음 오류
- **대안**: 훅 스크립트는 `.claude/hooks/scripts/`에 배치, `settings.json`에서 `${CLAUDE_PROJECT_DIR}/.claude/` 패턴으로 참조. 상대 경로(`.claude/`)는 worktree 환경에서 cwd가 달라질 때 실패함

### 전역 settings.json 중복 설정
- **함정**: `~/.claude/settings.json`에 훅/권한을 정의하면 프로젝트 settings.json과 중복 적용
- **대안**: `~/.claude/settings.json`은 `{}`로 비워두고, 모든 훅/권한은 `.claude/settings.json`에만 정의

## Lessons Learned
- **외부 프롬프트 → 스킬 변환 시 MVP 먼저**: 복잡한 Phase는 사용자 확인 전에 구현하지 않는다. 초기 설계를 제시하고 피드백으로 범위를 확정한다.
- **passive 모드 vs active 스킬**: `extensions/modes/`는 자동 활성화 행동 변화, `skills/`는 명시적 호출 플로우. 동일 기능처럼 보여도 역할이 다르므로 두 파일에 상호 참조를 명시한다.
- **git worktree 기반 역할 분리**: 카테고리별 Claude 환경 분리 시 git worktree 사용. CLAUDE.md/skills는 git으로 공유, 세션 메모리는 경로별 자동 분리 (컨텍스트 오염 없음).
- **공통 업데이트 전파**: main 수정 후 각 worktree에서 `git rebase main` (merge 아닌 rebase로 선형 히스토리 유지).
- **훅 스크립트 경로는 `${CLAUDE_PROJECT_DIR}` 기준으로**: `settings.json` 훅에서 `~/.claude/` 전역 경로나 `.claude/` 상대 경로 모두 부적합. 전역 경로는 다른 환경 복사 시 실패, 상대 경로는 worktree 환경(cwd 불일치)에서 실패. `bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/scripts/foo.sh"` 패턴이 유일하게 안전. 단, 출력 경로(`~/.claude/qmd-sessions` 등)는 홈 기준 유지.
- **`cp -r` 대신 `cp -rL`**: 심볼릭 링크를 포함한 디렉토리 복사 시 `cp -r`은 링크 자체를 복사해 dangling symlink를 유발한다. `cp -rL`로 링크를 실제 파일로 해소하여 복사한다.
- **UserPromptSubmit 훅 stdout → Claude 컨텍스트 주입**: UserPromptSubmit 훅에서 stdout으로 출력한 내용은 Claude 컨텍스트에 자동 주입된다. 스킬 추천, 자동 컨텍스트 로딩 등에 활용 가능하다.

## Compact Instructions
- `.claude/CLAUDE.md` = `~/.claude/CLAUDE.md` 동기화 유지
- Skills/Agents 수정 전 다른 프로젝트 영향 고려
- Scripts: shellcheck/py_compile 검증 필수, JSON: jq 검증 필수

## Workflow
1. 수정 전 영향 범위 확인 (다른 프로젝트에서 사용 여부)
2. 스크립트 수정 시 `shellcheck` / `python -m py_compile`
3. JSON 수정 시 `jq empty` 검증
4. `/verify` → `/wrap` → `/commit`

## References
- 가이드: `docs/CLAUDE-MD-GUIDE.md`
- Auto Memory 가이드: `docs/AUTO-MEMORY-GUIDE.md`
- 스킬 상세: `.claude/skills/*/SKILL.md`
- 에이전트 상세: `.claude/agents/*.md`
- 검증 도구: `.claude/skills/verify/references/LANGUAGES.md`
- 훅 가이드: `docs/TEAMMATE-HOOKS-GUIDE.md`
