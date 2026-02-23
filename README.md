# Claude Code 범용 프로젝트 템플릿

모든 프로젝트 타입에서 사용 가능한 범용 Claude Code 설정 템플릿

## 개요

이 템플릿은 **기술 스택 중립적**으로 설계되어 백엔드, 프론트엔드, 풀스택, 사이버보안 등 모든 프로젝트에서 사용할 수 있습니다.

### 핵심 개념

- **Skills**: 반복 작업 자동화 (Progressive Disclosure 패턴)
- **Hooks**: 파일 확장자 기반 자동 린트/포맷
- **Agents**: 기술 중립적 역할 분담 (Implementer, Reviewer, Doc Writer)
- **CLAUDE.md**: 프로젝트별 커스터마이징 가능한 컨텍스트

## 범용 템플릿 구조

```
.claude/
├── CLAUDE.md           # 프로젝트별 커스터마이징 (기술 스택, 규칙)
├── hooks.json          # 확장자 기반 자동 린트 (py→ruff, ts→eslint, go→gofmt 등)
├── agents/
│   ├── implementer.md  # 기술 중립적 구현 에이전트
│   ├── reviewer.md     # 보안/품질/성능 리뷰 에이전트
│   └── doc-writer.md   # 문서화 전문 에이전트
└── skills/
    ├── wrap/           # 세션 정리 및 학습 추출
    ├── commit/         # Git 커밋 자동화
    ├── verify/         # 검증 루프
    └── breakdown/      # 작업 계획 수립
```

## 주요 변경 사항

### 이전 (타입별 템플릿)
- ❌ 프로젝트 타입마다 선택 필요 (backend/frontend/fullstack/cybersecurity)
- ❌ 중복 파일 관리 (skills 4벌 복사)
- ❌ 기술 스택 변경 시 템플릿 교체 필요

### 현재 (범용 템플릿)
- ✅ **단일 템플릿** 모든 프로젝트에 사용
- ✅ **자동 감지** 파일 확장자로 린터 자동 선택
- ✅ **프로젝트별 커스터마이징** CLAUDE.md만 수정

## 사용 방법

### 1. 새 프로젝트 생성
```bash
# 프로젝트 디렉토리 생성
mkdir my-project && cd my-project && git init

# 범용 템플릿 복사
cp -r ~/claude-project-config/.claude .

# CLAUDE.md 프로젝트 정보 수정
vim .claude/CLAUDE.md
# - [프로젝트명] 수정
# - Tech Stack 섹션 업데이트
# - 프로젝트별 규칙 추가

# Git 커밋
git add .claude
git commit -m "Add Claude Code configuration"
```

### 2. CLAUDE.md 커스터마이징 예시

#### Python 백엔드 프로젝트
```markdown
## Tech Stack
- Language: Python 3.11
- Framework: FastAPI
- Database: PostgreSQL
- Testing: pytest
- Linting: ruff
```

#### TypeScript 프론트엔드 프로젝트
```markdown
## Tech Stack
- Language: TypeScript 5.0
- Framework: React 18 + Next.js 14
- State: Zustand
- Testing: Vitest + Playwright
- Linting: ESLint + Prettier
```

#### Go 백엔드 프로젝트
```markdown
## Tech Stack
- Language: Go 1.21
- Framework: Gin
- Database: MongoDB
- Testing: standard testing package
- Linting: golangci-lint
```

### 3. 개발 워크플로우
```bash
# 세션 시작
claude

# 작업 계획
> /breakdown "사용자 인증 구현"

# 구현 진행...
# (파일 편집 시 자동으로 언어별 린터 실행)

# 검증
> /verify

# 세션 정리
> /wrap

# 커밋
> /commit
```

### 4. 팀원 온보딩
```bash
# 프로젝트 클론
git clone https://github.com/team/project.git
cd project

# .claude/ 디렉토리가 이미 포함됨
# Claude Code 실행하면 자동으로 설정 로드
claude
```

## Hooks 자동 감지

범용 `hooks.json`은 파일 확장자를 자동으로 감지하여 적절한 린터를 실행합니다:

```json
{
  "postToolUse": ["Edit", "Write"],
  "command": "case \"${ext}\" in
    py) ruff check --fix ;;
    ts|tsx|js|jsx) eslint --fix ;;
    go) gofmt -w ;;
    rs) rustfmt ;;
  esac"
}
```

**지원 언어**:
- **Python**: `ruff check --fix`
- **TypeScript/JavaScript**: `eslint --fix`
- **Go**: `gofmt -w`
- **Rust**: `rustfmt`

## 스킬 상세

### /wrap (세션 정리)
**목적**: 세션 종료 시 학습 내용 추출 및 CLAUDE.md 업데이트

**4개 관점 병렬 분석**:
- `doc-updater`: CLAUDE.md 업데이트 항목
- `automation-scout`: 자동화 기회 탐지
- `learning-extractor`: 배운 것/실수/발견
- `followup-suggester`: 다음 작업 제안

### /commit (Git 커밋)
**목적**: Conventional Commits 형식 자동 생성

**프로세스**:
1. `git diff --staged` 분석
2. 타입 분류 (feat/fix/refactor/...)
3. 커밋 메시지 생성
4. 사용자 확인 후 커밋
5. PR 생성 옵션

### /verify (검증)
**목적**: 언어별 린트/타입/테스트/빌드 자동 검증

**검증 항목** (프로젝트에 따라 자동 감지):
- **Python**: ruff, mypy, pytest
- **TypeScript**: eslint, tsc, vitest
- **Go**: golangci-lint, go test
- **Rust**: clippy, cargo test

### /breakdown (작업 계획)
**목적**: 복잡한 작업을 단계별로 분해

**구조**:
- Phase 1-3: 준비 → 구현 → 검증
- 의존성 매핑
- 리스크 평가
- TodoWrite 연동

## Agents 상세

### Implementer (범용 구현자)
**역할**: 기술 스택 무관 구현
- 모든 언어/프레임워크 대응
- 언어별 베스트 프랙티스 준수
- 타입 안전성, 테스트 작성

### Reviewer (범용 리뷰어)
**역할**: 보안/품질/성능 검토
- 언어 무관 SOLID 원칙 검증
- OWASP Top 10 보안 검사
- 성능 병목 분석

### Doc Writer (문서화 전문)
**역할**: 모든 프로젝트 문서화
- README, API 문서, 아키텍처
- 다국어 지원 (영어/한국어)
- 배포 가이드, 컨트리뷰션 가이드

## Progressive Disclosure 패턴

**문제**: 모든 스킬을 컨텍스트에 로드하면 50,000+ 토큰 소모

**해결**:
1. **Discovery**: 이름 + 설명만 (100 토큰)
2. **Activation**: 호출 시 전체 로드 (5,000 토큰)
3. **절감**: 10개 스킬 기준 90% 토큰 절약

## Boris Cherny 7가지 전략 적용

1. ✅ **병렬 처리**: Hooks에서 자동 린트 병렬 실행
2. ✅ **Opus 4.5**: 복잡한 작업은 상위 모델 권장
3. ✅ **CLAUDE.md 팀 공유**: Git 체크인
4. ✅ **Plan Mode**: /breakdown 스킬로 시작
5. ✅ **Slash Commands**: /wrap, /commit, /verify
6. ✅ **권한 공유**: hooks.json, settings.local.json
7. ✅ **검증 루프**: /verify 스킬

## 언어별 사용 예시

### Python 프로젝트
```bash
# FastAPI 프로젝트 예시
cp -r ~/claude-project-config/.claude .

# CLAUDE.md 수정
# Tech Stack: Python 3.11, FastAPI, PostgreSQL

# 자동으로 ruff 실행됨
claude
> (Python 파일 편집)
```

### TypeScript 프로젝트
```bash
# Next.js 프로젝트 예시
cp -r ~/claude-project-config/.claude .

# CLAUDE.md 수정
# Tech Stack: TypeScript, React, Next.js

# 자동으로 eslint 실행됨
claude
> (TS 파일 편집)
```

### Go 프로젝트
```bash
# Gin API 프로젝트 예시
cp -r ~/claude-project-config/.claude .

# CLAUDE.md 수정
# Tech Stack: Go 1.21, Gin, MongoDB

# 자동으로 gofmt 실행됨
claude
> (Go 파일 편집)
```

### 멀티 언어 프로젝트
```bash
# 풀스택 프로젝트 (Python 백엔드 + TypeScript 프론트)
cp -r ~/claude-project-config/.claude .

# CLAUDE.md 수정
# Tech Stack:
#   Backend: Python, FastAPI
#   Frontend: TypeScript, React

# 파일별로 자동 감지
claude
> (*.py 편집 → ruff)
> (*.tsx 편집 → eslint)
```

## 커스터마이징

### 새 언어 지원 추가
`hooks.json`에 케이스 추가:
```json
"command": "case \"$ext\" in
  py) ruff check --fix ;;
  ts|tsx) eslint --fix ;;
  java) google-java-format -i ;;
  cpp|cc) clang-format -i ;;
esac"
```

### 새 스킬 추가
```bash
mkdir -p .claude/skills/my-skill

cat > .claude/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: 내 스킬 설명
triggers: ["/my-skill"]
---

## What
[스킬 기능]

## Workflow
[실행 단계]
EOF
```

### Agent 추가
```bash
cat > .claude/agents/my-agent.md << 'EOF'
# My Agent - Universal

## Role
[역할]

## Expertise
[전문 분야]

## Responsibilities
[책임]
EOF
```

## 검증 방법

### 1. 구조 확인
```bash
ls -la .claude/
# CLAUDE.md, hooks.json, agents/, skills/ 존재 확인
```

### 2. Hook 테스트
```bash
# Python 파일 편집 시 ruff 자동 실행 확인
claude
> (Python 파일 수정)
> (ruff가 자동 실행되는지 확인)

# TypeScript 파일 편집 시 eslint 자동 실행 확인
> (TS 파일 수정)
> (eslint가 자동 실행되는지 확인)
```

### 3. Skill 테스트
```bash
claude
> /wrap
> (4개 관점 분석 출력 확인)

> /verify
> (언어별 검증 자동 실행)
```

### 4. Agent 테스트
```bash
claude
> @implementer "로그인 기능 구현해줘"
> (범용 구현 스타일 확인)
```

## 문제 해결

### Q: 린터가 실행되지 않아요
**A**:
1. 해당 언어 린터 설치 확인 (`ruff`, `eslint` 등)
2. `hooks.json`에서 확장자 케이스 확인
3. 린터 경로가 PATH에 있는지 확인

### Q: 스킬이 로드되지 않아요
**A**:
1. `.claude/skills/*/SKILL.md` 파일 존재 확인
2. YAML frontmatter 형식 검증 (name, description, triggers)

### Q: Agent 역할이 적용되지 않아요
**A**:
1. `@agent-name` 형식으로 호출
2. `.claude/agents/` 경로 확인

## 마이그레이션 가이드

### 기존 타입별 템플릿에서 범용 템플릿으로
```bash
# 백업
cp -r .claude .claude.backup

# 범용 템플릿 적용
rm -rf .claude
cp -r ~/claude-project-config/.claude .

# CLAUDE.md 프로젝트 정보 복원
vim .claude/CLAUDE.md
# (기존 .claude.backup/CLAUDE.md 참고하여 Tech Stack, Rules 복사)
```

## 예시 모음

프로젝트 타입별 CLAUDE.md 커스터마이징 예시는 `examples/` 디렉토리에 있습니다:
- `examples/CLAUDE.backend.md` - Python 백엔드 예시
- `examples/CLAUDE.frontend.md` - TypeScript 프론트엔드 예시
- `examples/CLAUDE.fullstack.md` - 풀스택 예시
- `examples/CLAUDE.cybersecurity.md` - 사이버보안 예시

새 프로젝트 시작 시 해당 예시를 참고하여 `.claude/CLAUDE.md`를 커스터마이징하세요.

## 📖 Skills vs Hooks vs Agents 구분 가이드

### 핵심 구분 원칙
> "실행 보장 → Hook, 사고 고정 → Skill, 상황 적용 → Agent"

| 개념 | 정의 | 언제 사용 |
|------|------|---------|
| **Skill** | 각 단계의 기준 정의 | 같은 지시 반복할 때 |
| **Hook** | 빠지면 안 되는 검사 강제 | 적어도 누락될 때 |
| **Agent** | 역할별 분리 | 대화 길어지면 산만할 때 |

### 판단 매트릭스
- "하면 좋은 것" → **Skill** (예: /wrap, /breakdown)
- "안 하면 안 되는 것" → **Hook** (예: 린트 자동 실행)
- "역할 충돌 발생" → **Agent** (예: implementer, reviewer 분리)

### 적용 예시
1. **코드 스타일 기준** → Skill (한번 정의, 매번 적용)
2. **린트 검사 누락** → Hook (자동 강제 실행)
3. **구현→리뷰→문서 역할 혼란** → Agent 3개 분리

## 🎯 Progressive Disclosure 패턴

### 문제
모든 스킬을 컨텍스트에 로드하면 50,000+ 토큰 소모

### 해결책
3단계 점진적 로드:

| 단계 | 로드 내용 | 토큰 |
|------|---------|------|
| Discovery | name, description만 | ~100 |
| Activation | 호출 시 전체 로드 | <5,000 |
| Execution | 필요한 reference만 | 동적 |

**효과**: 10개 스킬 기준 50,000+ → 초기 1,000 토큰 (95% 절감)

### 스킬 파일 구조
```
my-skill/
├── SKILL.md          # 500줄 이하, 메타데이터 + 핵심 지시
├── scripts/          # 실행 코드 (Python, Bash, JS)
├── references/       # 온디맨드 문서
└── assets/          # 템플릿, 데이터
```

## 🔒 MCP 격리 패턴 (Context Isolation)

### 문제점
MCP 직접 연결 시 결과가 메인 컨텍스트에 쌓임
- Context7: 라이브러리 3-4개 조회 → 20,000+ 토큰
- Tavily: 검색 2-3회 → 10,000+ 토큰
- Serena+Sequential: 분석 → 15,000+ 토큰

### 해결책
서브에이전트로 격리 실행 → 요약만 반환

| MCP 서버 | 스킬 | 에이전트 | 토큰 절감 |
|---------|------|---------|----------|
| Context7 | `/mcp-docs` | docs-researcher | 95% (15K→800) |
| Tavily | `/mcp-search` | web-researcher | 90% (12K→1.2K) |
| Serena+Sequential | `/mcp-analyze` | code-analyzer | 90% (15K→1.5K) |
| Playwright | `/mcp-test` | test-runner | 85% (8K→1.2K) |

### 사용 예시
```bash
# Before (직접 호출)
사용자: "React useEffect cleanup 사용법 알려줘"
→ Context7 직접 호출
→ 15,000 토큰 전체 로드
→ 메인 컨텍스트 압박

# After (격리 실행)
사용자: /docs react "useEffect cleanup"
→ docs-researcher 서브에이전트 (격리)
→ 800 토큰 요약만 반환
→ 메인 컨텍스트 효율적 사용
```

## 🚀 Boris Cherny 7가지 전략

### 1. 병렬 처리
- 터미널 5개 + 웹 5-10개 동시 실행
- `--teleport`로 세션 간 전환
- 각 탭은 별도 git checkout

### 2. Opus 4.5 선택
- "가장 큰 모델을 모든 작업에"
- 방향 수정 적고 툴 사용 뛰어남

### 3. CLAUDE.md 팀 공유
- 팀 전체가 하나의 CLAUDE.md Git 체크인
- 실수 발생 시 해당 파일에 추가

### 4. Plan Mode
- Shift+Tab 두 번으로 진입
- "좋은 계획이 성공의 90%"

### 5. Slash Commands와 Subagents
- 매일 수십 번 사용하는 워크플로우 → `.claude/commands/`
- 예: `/commit-push-pr`

### 6. 권한 관리
- `/permissions`로 안전한 명령어 사전 승인
- `.claude/settings.json`에 권한 설정 공유

### 7. 검증 루프
- "자신의 작업을 검증할 방법 제공이 가장 중요"
- 백그라운드 에이전트로 검증
- Agent Stop hook으로 결정론적 검증

## 🧪 검증 계획

### 1. 구조 검증
```bash
ls -la .claude/
# agents/ (7개), skills/ (8개), memory/, hooks.json 확인
```

### 2. Hook 테스트
```bash
claude
> (Python 파일 수정 → ruff 자동 실행 확인)
> (YAML 파일 수정 → yamllint 자동 실행 확인)
> (git add .env → 민감 파일 경고 확인)
```

### 3. MCP 격리 테스트
```bash
/docs react useEffect
/search "TypeScript 5.3 features"
/analyze auth.py dependency
/test login
```

### 4. 워크플로우 테스트
```bash
/breakdown "사용자 인증 구현"
# → planner 에이전트 활성화
# → 단계별 분해, 리스크 평가

구현 진행...

/verify
# → 린트/타입/테스트 자동 실행

/wrap
# → 5개 에이전트 (Phase 1: 4개 병렬 → Phase 2: duplicate-checker)
# → CLAUDE.md 업데이트 제안

/commit
# → Conventional Commits 형식 자동 생성
```

### 5. 토큰 효율 모니터링
세션 중 토큰 사용량 추적:
- MCP 격리 전후 비교
- 긴 세션(50+ 메시지)에서 성능 확인

## 📁 최종 디렉토리 구조

```
.claude/
├── CLAUDE.md                    # 프로젝트별 커스터마이징
├── hooks.json                   # 자동 린트 + 위험 명령 확인
├── settings.local.json          # 로컬 설정
├── agents/
│   ├── implementer.md           # 구현 전문
│   ├── reviewer.md              # 리뷰 전문
│   ├── doc-writer.md            # 문서화 전문
│   ├── planner.md               # ⭐ 계획 전문 (신규)
│   ├── docs-researcher.md       # ⭐ Context7 격리 (신규)
│   ├── web-researcher.md        # ⭐ Tavily 격리 (신규)
│   └── code-analyzer.md         # ⭐ Serena+Sequential 격리 (신규)
├── skills/
│   ├── breakdown/               # 작업 계획 수립
│   ├── verify/                  # 검증 루프
│   ├── wrap/                    # 세션 정리 (5개 에이전트)
│   ├── commit/                  # Git 커밋 자동화
│   ├── mcp-docs/                # ⭐ Context7 래핑 (신규)
│   ├── mcp-search/              # ⭐ Tavily 래핑 (신규)
│   ├── mcp-analyze/             # ⭐ Serena+Sequential 래핑 (신규)
│   └── mcp-test/                # ⭐ Playwright 래핑 (신규)
└── memory/                      # ⭐ 세션 메모리 (신규)
    └── (세션별 컨텍스트 저장)
```

## 라이선스

MIT

## 기여

이슈/PR 환영합니다!
