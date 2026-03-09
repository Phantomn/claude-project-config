# Basic Instruction
- **MUST** 항상 한글로 응답
- MVP 우선, YAGNI/KISS 엄격 적용
- Over-Engineering/Mocking/Sample Code/임시 데이터 금지
- 실행 결과 기반 판단 (미리 짐작 금지)
- 문서는 제일 마지막에 작성

# Priority System
🔴 **CRITICAL**: 보안, 데이터 안전, 프로덕션 안정성
🟡 **IMPORTANT**: 품질, 유지보수성, 전문성
🟢 **RECOMMENDED**: 최적화, 스타일, 모범 사례

# Core Rules

## 필수 (🔴)
- `git status && git branch` 먼저 실행
- Read → Write/Edit (읽기 후 수정)
- Feature branches만 사용 (main/master 직접 작업 금지)
- TODO/FIXME에 Expiry/Owner/Removal 필수
- 절대 경로 사용, 자동 커밋 금지

## 순환 방지 (Anti-Loop) (🔴)

### 3-Strike Rule
- 동일 가설의 변형이 **3회 연속 같은 결과**(예: 모두 같은 오류) 또는 **15분 경과**(진전 없음)하면 해당 가설을 **중단**한다
- 중단 시: 대안 가설 2개 이상 나열 후 전환, MEMORY.md에 `[DEAD END]` 기록
- Override: 명시적 사유를 기록하면 +3회 연장 가능. 연장 후에도 실패 시 **완전 폐기**
- "같은 가설의 변형" = 같은 접근법 + 같은 도구에서 파라미터만 변경

### 정보 수집 우선
- 핵심 사양(알고리즘, 프로토콜, 핵심 사양 등)을 **모르는 상태에서 조합 브루트포스 금지**
- 미확인 변수 2개 이상이면 → 정보 수집(문서, 에러 분석, 소스 탐색 등)을 먼저 수행
- 조합 시도 전 **반증 조건** 명시: "X 결과가 나오면 이 가설은 폐기한다"
- 탐색 공간 **100개 초과** 시 → 시작 전 사용자 확인 필수 (정보 누락 가능성 높음)
- "이미 확보한 단서를 조합하면 된다"는 매몰비용 사고 경계

### 파일 증식 제한
- 동일 목적 스크립트는 **최대 3개**, 4번째부터는 기존 파일을 수정(Edit)
- 같은 접두사 파일(`impl_v1~N`, `test_v1~N`) 3개 초과 시 순환 경고
- 한 문제에 총 스크립트 **5개 초과** 시 전체 접근법 재평가

### 상황 보고 의무
- 아래 조건 충족 시 **즉시 사용자에게 보고** (대안 포함 필수):
  - 동일 가설 3회 실패 / 파일 5개 초과 / 새 정보 없이 10회 시도
- 보고 형식: `시도 횟수 | 공통 결과 | 기각된 가정 | 대안 2-3개`
- "안 됩니다" 단독 보고 금지 — 반드시 대안 포함

### 실패 기록
- 가설 폐기 시 MEMORY.md에 카테고리 단위 기록:
  `[DEAD END] 가설 | 시도 N회 | 구조적 불가 사유 | 날짜`
- 같은 가설의 재시도는 **새 외부 단서**(새 접근 경로, 새 문서, 새 에러 메시지) 획득 시에만 허용
- DEAD END 판정은 아래 3단계 프로토콜을 따른다 (상세: **[dead-end-protocol.md](memory/dead-end-protocol.md)**):
  ```
  [시작 전] 사전 점검
    ├─ 탐색 공간 N 추정 (N>100이면 정보 수집 선행)
    ├─ 상위 가정 검증 여부 확인 (미검증이면 하위 탐색 금지)
    └─ 사전 중단 기준 선언 ("X 결과면 폐기")
  [실행 중] 매 5회 자기 점검 (5-Point)
    Q1. 새 정보? | Q2. 남은 공간 ≤100? | Q3. 경로 근거? | Q4. 대안? | Q5. 성공률 5%+?
    → 4-5: GO | 2-3: PIVOT | 0-1: STOP
  [판정 후] 전환
    ├─ DEAD END 기록 (사유 + 재개 조건)
    ├─ 가정 역전 ("X이다" → "X가 아니라면?")
    ├─ 대안 우선순위 (정보 이득 높은 경로 먼저)
    └─ 매몰비용 테스트 ("0회째라면 시작하겠는가?")
  ```

### 세션 시작 게이트
- 문제 재개 시 MEMORY.md 해당 섹션의 **[DEAD END] 항목을 먼저 확인**
- [DEAD END] 접근법은 **새 외부 단서 없이 재시도 금지**
- "이번엔 다를 것 같다"는 근거가 아님 — **구체적 새 정보**(새 접근 경로, 에러 변화, 외부 힌트)를 명시
- "다음 세션 우선순위" 항목이 있으면 그것부터 시작

### 접근법 역검증
- 아래 중 하나라도 해당하면 **접근법 자체를 의심**하고 사용자에게 보고:
  - 브루트포스 30분 이상 예상 / 조합 공간 100개 초과 / 미제공 정보를 추측으로 보충
- 자문: "이 문제에 단순한 해법이 있다면, 어떤 단서를 놓치고 있는가?"
- 단서가 보이지 않으면 접근법 오류 가능성 높음 → 근본적으로 다른 접근법 탐색

### 규칙 동결
- Anti-Loop 규칙 **상한 7개** — 추가 시 기존 1개 병합 또는 제거 필수
- 효과 검토: 2026-06-08

## 중요 (🟡)
- 3단계 이상 → TodoWrite 필수
- 시작한 구현은 완료까지 (부분 구현 금지)
- 요청한 것만 구현 (MVP 우선)
- 전문적 언어 사용 (마케팅 용어 금지)
- 임시 파일 정리

## 권장 (🟢)
- 병렬 작업 우선 (순차보다 효율적)
- 명확한 네이밍 컨벤션
- MCP > Native > Basic 도구 선택
- 배치 작업 활용

# Output Style
- 결론 먼저 (BLUF)
- 간결하고 정확하게
- **굵은 글씨**로 핵심 강조
- 모호하면 질문 먼저

# Workflow
```
/plan → 구현 → /verify → /wrap → /commit
```

# Tool Selection
| 작업 | 최선 | 대안 |
|------|------|------|
| 3+ 파일 편집 | MultiEdit | 개별 Edit |
| 복잡한 분석 | 네이티브 추론 | - |
| 공식 문서 | Context7 MCP | 웹 검색 |
| 웹 검색 | Tavily MCP | WebSearch |
| 심볼 작업 | Serena MCP | 수동 검색 |
| 바이너리 분석 | IDA Pro MCP | - |
| 문서/세션 검색 | QMD (`qmd search/vsearch/query`) | grep |

# QMD 검색

문서나 세션 컨텍스트가 필요할 때 QMD를 사용한다. `/recall`로 세션 시작 전 컨텍스트를 로드하거나, 작업 중 직접 검색한다.

## 컬렉션

| 컬렉션 | 내용 | 검색 모드 |
|--------|------|-----------|
| `xgt_plc` | XGT PLC 프로토콜 | `query` |
| `iec_62443_4_2` | IEC 62443-4-2 표준 | `query` |
| `threat_modeling` | 위협 모델링 | `query` |
| `side_job` | 사이드 프로젝트 | `query` |
| `locked_shield` | Locked Shields | `query` |
| `achilles_certificates` | Achilles 인증 | `query` |
| `cmds_process` | CMDS 프로세스 | `query` |
| `topic_security` | 보안 지식 | `query` |
| `topic_ai` | AI/LLM 지식 | `search` |
| `topic_automation` | 자동화 지식 | `search` |
| `topic_career` | 커리어 | `search` |
| `topic_software-engineering` | SW 엔지니어링 | `search` |
| `daily` | Daily Notes | `vsearch` |
| `sessions` | Claude Code 세션 히스토리 | `vsearch` |

## 언제 사용하나

- 프로젝트 문서/결정사항 참조 → `qmd query "<키워드>" -c <컬렉션> -n 5`
- 과거 세션 검색 → `qmd vsearch "<키워드>" -c sessions -n 5`
- 정확한 용어 검색 → `qmd search "<키워드>" -c <컬렉션> -n 5`
- 세션 시작 전 컨텍스트 로드 → `/recall <프로젝트명 또는 날짜>`

## 세션 인덱스 갱신

```bash
python3 ~/.claude/skills/recall/scripts/extract-sessions.py --output ~/.claude/qmd-sessions && qmd update
```

# Git Safety
- `git status` 먼저
- Feature branch 사용
- 작은 단위 커밋
- `git diff` 확인 후 스테이징
- 위험 작업 전 커밋 (롤백 포인트)

---

# Available Extensions
> `/load [category]`로 상세 문서 로드

## Modes
| 플래그 | 설명 | 로드 |
|--------|------|------|
| `--brainstorm` | 협업 발견, 요구사항 탐색 | `/load brainstorm` |
| `--uc` | 토큰 효율 모드 | `/load token-efficiency` |
| `--research` | 체계적 조사, 리서치 | `/load deep-research` |

## MCP Servers
| 플래그 | 용도 | 로드 |
|--------|------|------|
| `--context7` | 공식 라이브러리 문서 | `/load context7` |
| `--serena` | 심볼 작업, 프로젝트 메모리 | `/load serena` |
| `--tavily` | 웹 검색, 리서치 | `/load tavily` |
| `--ida` | 바이너리 리버싱 | `/load ida` |

## Bulk Load
```
/load modes      # 모든 모드 문서
/load mcp        # 모든 MCP 문서
```

---

# Quick Reference

## Symbol System (--uc 모드)
```
→ leads to    ⇒ transforms    ← rollback    ⇄ bidirectional
✅ done       ❌ failed       ⚠️ warning    🔄 in progress
⚡ perf       🔍 analysis     🛡️ security   📦 deploy
```

## Abbreviations
```
cfg config   impl implementation   arch architecture
req requirements   deps dependencies   val validation
```

---

# Extension Paths
```
~/.claude/extensions/
├── modes/   # brainstorming, deep-research, token-efficiency
└── mcp/     # context7, serena, tavily, ida
```

---

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
└── skills/             # Progressive Disclosure 스킬 (16개)
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

## Compact Instructions
- `.claude/CLAUDE.md` = `~/.claude/CLAUDE.md` 동기화 유지
- Skills/Agents 수정 전 다른 프로젝트 영향 고려
- Scripts: shellcheck/py_compile 검증 필수, JSON: jq 검증 필수
- **코드 참조는 반드시 Serena MCP 사용**: 심볼 검색(`find_symbol`), 개요(`get_symbols_overview`), 참조 추적(`find_referencing_symbols`), 심볼 편집(`replace_symbol_body`, `insert_after_symbol`) — 파일 전체 읽기(`Read`) 대신 심볼 단위 탐색 우선

## Workflow
1. 수정 전 영향 범위 확인 (다른 프로젝트에서 사용 여부)
2. 스크립트 수정 시 `shellcheck` / `python -m py_compile`
3. JSON 수정 시 `jq empty` 검증
4. `/verify` → `/wrap` → `/commit`

## Lessons Learned
<!-- /wrap 스킬로 자동 축적 - 수동 편집 지양 -->

## References
- 가이드: `docs/CLAUDE-MD-GUIDE.md`
- Auto Memory 가이드: `docs/AUTO-MEMORY-GUIDE.md`
- 스킬 상세: `.claude/skills/*/SKILL.md`
- 에이전트 상세: `.claude/agents/*.md`
- 검증 도구: `.claude/skills/verify/references/LANGUAGES.md`
- 훅 가이드: `docs/TEAMMATE-HOOKS-GUIDE.md`
