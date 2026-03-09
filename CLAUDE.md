# vuln-os - 주요정보통신기반시설 OS 하드닝 점검

주요정보통신기반시설 기술적 취약점 분석·평가 기준에 따른 OS 하드닝 자동화 점검 도구.

## 프로젝트 구조

```
scripts/
├── linux/          U-01~70.sh    (70개, bash)
├── windows_server/ W-01~82.ps1  (82개, PowerShell)
└── windows/        PC-01~18.ps1 (18개, PowerShell)

runner/
├── __init__.py
├── models.py          # ResultCode, OSKind, ScriptMeta, CheckResult, RunSession
├── detector.py        # OS 탐지 + preflight
├── credentials.py     # 자격증명 수집 (getpass)
├── executor.py        # subprocess 실행 + 파싱
├── reporter_json.py   # JSON 결과 직렬화
├── reporter_pdf.py    # Jinja2 + WeasyPrint PDF 생성
├── templates/
│   └── report.html.j2
├── main.py            # 진입점
└── requirements.txt

results/               # 출력 디렉토리 (.gitignore)
```

## 실행 방법

```bash
# 의존성 설치 (PDF 필요 시)
pip install -r runner/requirements.txt
# Ubuntu: sudo apt-get install libcairo2 libpango-1.0-0 libpangocairo-1.0-0

# 실행 (관리자 권한 필수)
python -m runner.main
```

## 결과 해석

| 상태 | 설명 |
|------|------|
| PASS | 양호 (점검 결과: 0) |
| FAIL | 취약 (점검 결과: N≥1) |
| ERROR | 스크립트 오류 또는 파싱 실패 |
| TIMEOUT | 제한 시간 초과 |

```bash
# 취약 항목 추출
jq '.items[] | select(.code=="FAIL") | {id, value}' results/최신.json

# 요약
jq '.summary' results/최신.json
```

## 타임아웃 설정

| 제한 | 대상 |
|------|------|
| 30s (기본) | 대부분 |
| 60s | W-04,05,15,16,40,46,47,48,49,50,51,54,55 (secedit) |
| 120s | PC-08 (Win32_Product WMI) |
| 180s | U-06,13,15,58 (find / 전체 탐색) |

## 알려진 버그 수정 이력 (Phase 0)

| 파일 | 버그 | 수정일 |
|------|------|--------|
| `W-69.ps1` | `elif` → `elseif` (11곳) | 2026-03-09 |
| `W-10.ps1` | `Invok-WebRequest` → `Invoke-WebRequest` | 2026-03-09 |
| `W-04.ps1` | `locskDuration` → `lockDuration` | 2026-03-09 |

## 주의사항

- **관리자 권한 필수**: Linux는 root/sudo, Windows는 Administrator
- **수동 검증 필수**: 자동화 점검은 참조용, 최종 판정은 수동 검증
- **자격증명 보안**: sudo 비밀번호는 stdin pipe만 사용, 로그/히스토리 미기록
- **Windows**: 반드시 관리자 권한 PowerShell에서 실행, `results/` 디렉토리 자동 생성

## 개발 워크플로우

```bash
# Python 구문 검증
python -m py_compile runner/models.py runner/detector.py runner/credentials.py \
    runner/executor.py runner/reporter_json.py runner/reporter_pdf.py runner/main.py

# Shell 스크립트 검증
shellcheck .claude/hooks/scripts/on-audit-completed.sh

# JSON 유효성
jq empty .claude/settings.json

# Phase 0 버그 수정 검증
grep 'elif' scripts/windows_server/W-69.ps1       # → 결과 없음
grep 'Invok-WebRequest' scripts/windows_server/W-10.ps1  # → 결과 없음
grep 'locskDuration' scripts/windows_server/W-04.ps1     # → 결과 없음
```

## 스크립트 공통 출력 규약

모든 스크립트는 마지막 줄에 아래 형식 출력:
```
echo "점검 결과: N"   # N=0: 양호, N≥1: 취약
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
- **대안**: 훅 스크립트는 `.claude/hooks/scripts/`에 배치, `settings.json`에서 `.claude/` 상대 경로로 참조

### 전역 settings.json 중복 설정
- **함정**: `~/.claude/settings.json`에 훅/권한을 정의하면 프로젝트 settings.json과 중복 적용
- **대안**: `~/.claude/settings.json`은 `{}`로 비워두고, 모든 훅/권한은 `.claude/settings.json`에만 정의

## Lessons Learned
- **외부 프롬프트 → 스킬 변환 시 MVP 먼저**: 복잡한 Phase는 사용자 확인 전에 구현하지 않는다. 초기 설계를 제시하고 피드백으로 범위를 확정한다.
- **passive 모드 vs active 스킬**: `extensions/modes/`는 자동 활성화 행동 변화, `skills/`는 명시적 호출 플로우. 동일 기능처럼 보여도 역할이 다르므로 두 파일에 상호 참조를 명시한다.
- **git worktree 기반 역할 분리**: 카테고리별 Claude 환경 분리 시 git worktree 사용. CLAUDE.md/skills는 git으로 공유, 세션 메모리는 경로별 자동 분리 (컨텍스트 오염 없음).
- **공통 업데이트 전파**: main 수정 후 각 worktree에서 `git rebase main` (merge 아닌 rebase로 선형 히스토리 유지).
- **훅 스크립트 경로는 프로젝트 로컬로**: `settings.json` 훅에서 `~/.claude/` 전역 경로 사용 시 다른 환경 복사 후 파일 없음 오류 발생. 훅 스크립트는 `.claude/hooks/scripts/`에 배치하고 `.claude/` 상대 경로로 참조한다.
- **`cp -r` 대신 `cp -rL`**: 심볼릭 링크를 포함한 디렉토리 복사 시 `cp -r`은 링크 자체를 복사해 dangling symlink를 유발한다. `cp -rL`로 링크를 실제 파일로 해소하여 복사한다.
- **UserPromptSubmit 훅 stdout → Claude 컨텍스트 주입**: UserPromptSubmit 훅에서 stdout으로 출력한 내용은 Claude 컨텍스트에 자동 주입된다. 스킬 추천, 자동 컨텍스트 로딩 등에 활용 가능하다.

- **스크립트 버그 수정 전 Phase 0 완료 필수**: runner 구현 전 반드시 W-69/W-10/W-04 버그 수정
- **Windows 자격증명 MVP 제약**: v1은 현재 프로세스 컨텍스트 사용, v2에서 `CreateProcessWithLogonW` 구현 예정
