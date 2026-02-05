# claude-project-config
Claude Code 범용 프로젝트 템플릿 저장소. Skills, Agents, Hooks 제공.
**중요**: 이 파일은 이 프로젝트 자체의 설정. `.claude/CLAUDE.md`는 복사용 템플릿.

## Tech Stack
- **Language**: Markdown, Shell (Bash), Python 3.10+, JSON
- **Linting**: shellcheck, ruff, py_compile, markdownlint, jq, yamllint

## Commands
```bash
# Shell 스크립트 검증
find .claude/skills -name "*.sh" -exec shellcheck {} \;

# Python 구문 검증
find .claude -name "*.py" -exec python -m py_compile {} \;

# JSON 유효성
jq empty .claude/*.json

# 전체 검증 (순차)
shellcheck .claude/skills/verify/scripts/*.sh && \
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
├── CLAUDE.md           # 복사용 템플릿 (수정 시 영향 범위 확인!)
├── hooks.json          # 확장자별 자동 린트 (case문 구조)
├── agents/             # 역할 기반 에이전트 (7개)
│   ├── implementer.md  # 구현
│   ├── reviewer.md     # 보안/품질/성능 리뷰
│   ├── planner.md      # 계획 수립
│   └── [3 more]        # MCP 격리 에이전트
└── skills/             # Progressive Disclosure 스킬 (8개)
    ├── plan/           # /plan 작업 계획
    ├── verify/scripts/ # 언어별 검증 스크립트
    ├── wrap/scripts/   # 학습 추출 Python
    └── [mcp-*/]        # MCP 격리 스킬
```

## Gotchas

### 템플릿 vs 실제 설정 혼동
- **함정**: `.claude/CLAUDE.md`를 이 프로젝트용으로 수정
- **대안**: 루트 `CLAUDE.md`(이 파일)가 이 프로젝트 설정

### Skills/Agents 무분별 수정
- **함정**: 다른 프로젝트에서 사용 중인 스킬/에이전트 임의 수정
- **대안**: 수정 전 영향 범위 확인, 범용성 유지

### hooks.json 언어 추가
- **함정**: case문 구조 손상, `;;` 누락
- **대안**: 기존 패턴 복사, `esac` 직전에 추가, `jq empty` 검증

### Shell 스크립트 Bash 전용 문법
- **함정**: `[[ ]]`, `echo -e`, array 사용 (현재 verify-*.sh에 존재)
- **대안**: 신규 스크립트는 POSIX 호환 권장, 기존은 점진적 마이그레이션

### Python 버전 호환
- **함정**: match-case, 새 타입 힌트 등 3.12+ 전용 문법
- **대안**: 3.10+ 호환 유지, `from __future__ import annotations`

## Compact Instructions
- `.claude/CLAUDE.md`는 템플릿 - 이 프로젝트 설정은 루트 `CLAUDE.md`
- Skills/Agents 수정 전 다른 프로젝트 영향 고려
- Scripts: shellcheck/py_compile 검증 필수, JSON: jq 검증 필수

## Workflow
1. 수정 전 영향 범위 확인 (다른 프로젝트에서 사용 여부)
2. 스크립트 수정 시 `shellcheck` / `python -m py_compile`
3. JSON 수정 시 `jq empty` 검증
4. `/verify` → `/wrap` → `/commit`

## References
- 가이드: `docs/CLAUDE-MD-GUIDE.md`
- 스킬 상세: `.claude/skills/*/SKILL.md`
- 에이전트 상세: `.claude/agents/*.md`
- 검증 도구: `.claude/skills/verify/references/LANGUAGES.md`
