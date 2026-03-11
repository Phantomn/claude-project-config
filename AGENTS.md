# Basic Instruction
- **MUST** 항상 한글로 응답
- MVP 우선, YAGNI/KISS 엄격 적용
- Over-Engineering/Mocking/Sample Code/임시 데이터 금지
- 실행 결과 기반 판단 (미리 짐작 금지)
- 문서는 제일 마지막에 작성
- 소스 코드는 Serena Find_Symbols를 사용하여 분석

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
- 동일 가설의 변형이 **3회 연속 같은 결과** 또는 **15분 경과**(진전 없음)하면 해당 가설을 **중단**한다
- 중단 시: 대안 가설 2개 이상 나열 후 전환, MEMORY.md에 `[DEAD END]` 기록
- Override: 명시적 사유를 기록하면 +3회 연장 가능. 연장 후에도 실패 시 **완전 폐기**
- "같은 가설의 변형" = 같은 접근법 + 같은 도구에서 파라미터만 변경

### 정보 수집 우선
- 핵심 사양을 **모르는 상태에서 조합 브루트포스 금지**
- 미확인 변수 2개 이상이면 문서, 에러 분석, 소스 탐색을 먼저 수행
- 조합 시도 전 **반증 조건** 명시: "X 결과가 나오면 이 가설은 폐기한다"
- 탐색 공간 **100개 초과** 시 시작 전 사용자 확인 필수

### 파일 증식 제한
- 동일 목적 스크립트는 **최대 3개**, 4번째부터는 기존 파일을 수정(Edit)
- 같은 접두사 파일(`impl_v1~N`, `test_v1~N`) 3개 초과 시 순환 경고
- 한 문제에 총 스크립트 **5개 초과** 시 전체 접근법 재평가

### 상황 보고 의무
- 아래 조건 충족 시 **즉시 사용자에게 보고**:
  - 동일 가설 3회 실패
  - 파일 5개 초과
  - 새 정보 없이 10회 시도
- 보고 형식: `시도 횟수 | 공통 결과 | 기각된 가정 | 대안 2-3개`

### 실패 기록
- 가설 폐기 시 MEMORY.md에 기록:
  `[DEAD END] 가설 | 시도 N회 | 구조적 불가 사유 | 날짜`
- 같은 가설의 재시도는 **새 외부 단서** 획득 시에만 허용

## 중요 (🟡)
- 3단계 이상 → TodoWrite 필수
- 시작한 구현은 완료까지
- 요청한 것만 구현
- 전문적 언어 사용
- 임시 파일 정리

## 권장 (🟢)
- 병렬 작업 우선
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
문맥 확인 → 필요 시 요구사항 탐색 → 계획 → 구현 → 검증 → 문서 작성 → 커밋
```

# Tool Selection
| 작업 | 최선 | 대안 |
|------|------|------|
| 3+ 파일 편집 | apply_patch + 배치 편집 | 개별 Edit |
| 복잡한 분석 | 네이티브 추론 | - |
| 공식 문서 | Context7 MCP | 웹 검색 |
| 웹 검색 | Tavily MCP | WebSearch |
| 심볼 작업 | Serena MCP | 수동 검색 |
| 바이너리 분석 | IDA Pro MCP | - |
| 문서/세션 검색 | QMD (`qmd search/vsearch/query`) | grep |

# Codex Project Layout
- Codex 프로젝트 설정: `.codex/config.toml`
- Codex 작업 규칙: 루트 `AGENTS.md`
- Codex 프로젝트 스킬 소스: `.codex/skills/`
- Codex 자동 인식 스킬 브리지: `.agents/skills -> ../.codex/skills`
- Claude 레거시 자산: `.claude/`
- Claude hook는 Codex에서 직접 실행되지 않으므로 `config.toml` 정책 + `AGENTS.md` 절차 + 독립 스크립트로 대체

## Hook Replacement
- `UserPromptSubmit` 대체: 작업 시작 시 이 문서의 Workflow를 먼저 따른다
- `PreToolUse` 대체: `.codex/config.toml`의 approval/sandbox/prefix rule을 따른다
- `PostToolUse` 대체: 파일 수정 후 `.codex/scripts/post-edit-check.sh <path>` 또는 언어별 검증 명령을 수동 실행한다
- `TaskCompleted` 대체: 팀 작업 정리 시 `.codex/scripts/task-complete.sh <task-id> [subject] [agent]`를 수동 실행한다
- `TeammateIdle` 대체: 팀원이 유휴가 되면 `.codex/scripts/teammate-idle.sh <agent> [task-id] [status]`를 수동 실행한다
- `Stop` 대체: 세션 종료 전 `.codex/scripts/session-stop.sh`를 수동 실행한다

# QMD 검색
- 프로젝트 문서/결정사항 참조 → `qmd query "<키워드>" -c <컬렉션> -n 5`
- 과거 세션 검색 → `qmd vsearch "<키워드>" -c sessions -n 5`
- 정확한 용어 검색 → `qmd search "<키워드>" -c <컬렉션> -n 5`

## 세션 인덱스 갱신
```bash
python3 .codex/skills/recall/scripts/extract-sessions.py --output ~/.codex/qmd-sessions --days 9999 && qmd update
```

# Git Safety
- `git status` 먼저
- Feature branch 사용
- 작은 단위 커밋
- `git diff` 확인 후 스테이징
- 위험 작업 전 커밋

# Validation
```bash
find .codex/skills -name "*.sh" -exec shellcheck {} \;
shellcheck .codex/hooks/scripts/*.sh
shellcheck .codex/scripts/*.sh
find .codex -name "*.py" -exec python -m py_compile {} \;
jq empty .claude/*.json
```

## Code Style
### We Use
- **Shell**: `set -euo pipefail`, 색상 변수, 함수 분리
- **Python**: 타입 힌트, pathlib, dataclass, 3.10+ 호환
- **SKILL.md**: YAML frontmatter (name, description, triggers) 필수

### We Avoid
- **Shell**: Bash 전용 문법
- **Python**: 3.12+ 전용 문법
- **하드코딩된 경로**

## Gotchas
- Skills/Agents 수정 전 다른 프로젝트 영향 고려
- Scripts: `shellcheck` / `python -m py_compile` 검증 필수
- JSON 수정 시 `jq empty` 검증
- **코드 참조는 Serena MCP 우선**
- 위험 명령은 `.codex/config.toml`의 prefix rule과 승인 정책을 따른다

## References
- 프로젝트 Codex 설정: `.codex/config.toml`
- 프로젝트 Codex 스킬: `.codex/skills/*/SKILL.md`
- 레거시 Claude 자산: `.claude/`
