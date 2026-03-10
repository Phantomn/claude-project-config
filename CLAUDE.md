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
├── executor.py        # subprocess 실행 + 파싱
├── reporter_json.py   # JSON 결과 직렬화
├── reporter_pdf.py    # fpdf2 PDF 생성 (순수 Python)
└── main.py            # 진입점

pyproject.toml         # 의존성 관리 (uv)
uv.lock                # 잠금 파일 (uv sync으로 갱신)

results/               # 출력 디렉토리 (.gitignore)
```

## 실행 방법

```bash
# 의존성 설치 (uv 사용)
uv sync
# PDF 라이브러리(fpdf2)는 순수 Python - 별도 시스템 패키지 불필요

# 실행 (관리자 권한 필수)
uv run python -m runner.main
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
uv run python -m py_compile runner/models.py runner/detector.py \
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
- **`set -e` 스크립트에서 grep 은 `|| true` 필수**: grep이 매치 없음 시 exit code 1을 반환하므로 `set -e` 환경에서 스크립트가 즉시 종료된다. 의도적으로 "없을 수도 있는" grep은 반드시 `grep ... || true` 패턴을 사용한다.
- **PyInstaller + WSL2 공유 라이브러리 이중 경로 충돌**: `/usr/local/lib`(비표준 빌드)와 `/lib/x86_64-linux-gnu`(시스템) 두 곳에 `libpython3.X.so`가 공존하면 비표준 빌드가 먼저 로드되어 `_struct` 등 빌트인 모듈이 누락된다. `LD_LIBRARY_PATH=/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH`로 시스템 경로를 우선 지정한다.
- **fpdf2 collect_all 제거 시 PIL hook 연쇄 제거 주의**: fpdf2는 순수 Python이므로 `collect_all('fpdf2')`가 불필요하나, 해당 라인 제거 시 PIL 관련 hook도 함께 빠져 `_struct` 충돌이 발생할 수 있다. PIL/Pillow 사용 시 별도로 명시적 포함(`collect_all('PIL')`)이 필요하다.
- **에어갭 배포는 순수 Python PDF 라이브러리 선택**: WeasyPrint는 GTK·Cairo·Pango 등 시스템 라이브러리에 의존해 오프라인 환경에서 설치/실행이 실패한다. fpdf2(순수 Python) 사용 시 시스템 의존성 없이 PyInstaller 단일 바이너리 배포 가능하다.
- **에어갭 환경 폰트 탐색은 fc-list + 하드코딩 경로 조합**: 네트워크 없이 한글 폰트를 찾을 때 `fc-list` 명령과 `/usr/share/fonts`, `/usr/local/share/fonts` 경로를 조합한다. 폰트 미발견 시 내장 Helvetica 폴백으로 항상 실행 가능성을 보장한다.
- **WSL2 `find / -perm -4000` 타임아웃 처리**: WSL2 전체 파일시스템 SUID 탐색은 180초 이상 소요될 수 있다. `timeout 180 find / -perm -4000 ...` 래퍼를 적용하고 timeout 종료 코드(124)를 정상으로 처리한다.
- **fpdf2 긴 텍스트는 `multi_cell` 사용**: 개행 포함 장문(raw_output 등)은 `cell` 대신 `multi_cell`로 출력해야 자동 줄바꿈 처리된다. `cell`은 단일 행 고정 높이로만 렌더링.
- **PDF 폰트명 하드코딩 금지**: `set_font("NotoSansKR", ...)` 직접 사용 시 Helvetica 폴백 환경에서 오류. 반드시 `font_name` 변수(= `"NotoSansKR" if use_korean else "Helvetica"`)를 사용한다.
- **fpdf2 글리프 누락은 조용한 실패**: 폰트에 없는 문자(예: `⚠` U+26A0)는 stdout 경고만 출력하고 PDF 생성은 계속된다. 특수문자 사용 전 해당 폰트의 글리프 포함 여부를 확인하고, 미포함 시 ASCII 대체(`⚠ → [!]`)를 명시적으로 처리한다.
- **fpdf2 테이블은 `pdf.table()` 컨텍스트 매니저 사용**: `cell()` 반복 대신 `with pdf.table() as table:` 패턴으로 열 너비·정렬·경계선을 선언적으로 제어한다. 셀별 색상은 `FontFace(color=..., fill_color=...)` 로 지정.
- **fpdf2 커스텀 헤더/푸터는 FPDF 서브클래스로 구현**: `header()`/`footer()` 오버라이드 + `page_no() == 1` 조건으로 표지를 제외한다. `footer()`에서 `self.set_y(-15)`로 하단 고정 위치 지정.
- **uv + pyproject.toml 마이그레이션 시 패키지 경로 명시**: `[tool.hatch.build.targets.wheel] packages = ["runner"]` 누락 시 `uv sync`/`uv build`가 패키지를 찾지 못한다. 빌드 스크립트(build.sh, build.ps1)는 venv + pip 기반이므로 `pip install fpdf2`로 직접 설치.
- **fpdf2 `table()` 가독성 옵션**: `repeat_headings=1` (페이지 넘김 시 헤더 반복), `padding=(상하, 좌우)` (셀 여백). 긴 텍스트는 표에 넣기 전 개행(`\n`)을 공백으로 치환 후 문자 수 제한 적용.
- **빌드 스크립트는 런타임 OS 탐지 분기 수만큼 스크립트 디렉토리를 모두 배포**: `build.ps1`이 `scripts\windows_server\`만 복사하면 Windows PC 탐지 시 경로 오류 발생. 런타임에서 `OSKind`별 분기가 N개라면 배포 패키지도 N개 디렉토리를 포함해야 한다. 매개변수화(`$Target`)로 선택 배포하면 탐지 결과와 불일치가 생긴다.
- **내부 상수 문자열을 사용자 노출 레이블로 직접 사용 금지**: `OSKind.WINDOWS_SERVER` 같은 내부 Enum 값을 `print()` 등 UI 출력에 직접 사용하면 가독성이 낮다. `{OSKind.LINUX: "Linux", OSKind.WINDOWS_SERVER: "Windows Server", ...}` dict 매핑을 별도 두고 레이블을 분리한다.
- **PDF 폰트 크기 상수화 (`FS_*` 패턴)**: `set_font(size=12)` 하드코딩이 여러 함수에 산재하면 일관성 유지가 어렵다. 파일 상단에 `FS_TITLE = 20; FS_SECTION = 13; FS_BODY = 10` 등 상수를 정의하고 모든 `set_font` 호출에서 참조한다. 불일치 발견 시 상수 값 하나만 수정하면 전체 반영된다.
- **관리자 쉘 전제 환경에서 자격증명 수집 불필요**: `sudo -s` / Administrator PowerShell로 실행하는 구조라면 `credentials.py` 모듈 자체가 불필요하다. 자격증명 수집 → stdin pipe 전달 구조는 비관리자 실행 경로가 있을 때만 의미 있다. 실행 컨텍스트 가정을 명확히 하고 불필요한 복잡도를 제거한다.
- **Windows 빌드에서 한글 폰트를 명시적으로 배포 패키지에 포함**: fpdf2 Helvetica 폴백 상태에서 한글 텍스트가 있으면 `FPDFUnicodeEncodingException` 발생. `build.ps1`에 `malgun.ttf` 등 시스템 한글 폰트를 `dist\` 하위로 복사하는 단계를 반드시 추가한다. Linux 빌드는 fc-list 탐색으로 런타임 해결하지만 Windows는 빌드 타임에 폰트를 패키징해야 한다.

## Common Mistakes

- **`set -e` 스크립트에서 grep 무방비 사용**: `grep pattern file`이 매치 없을 때 exit 1을 반환하는 것을 간과하여 스크립트가 중단된다. `|| true`를 빠뜨리지 않는다.
- **PyInstaller 배포 전 라이브러리 로드 경로 미검증**: WSL2처럼 동일 `.so`가 두 경로에 공존하는 환경에서 빌드는 성공하나 실행이 실패한다. 배포 전 `ldd ./binary` 또는 `LD_DEBUG=libs ./binary 2>&1 | grep struct`로 경로를 검증한다.
- **에어갭 배포에 WeasyPrint 선택**: 시스템 패키지 의존성이 크므로 오프라인 환경에서 실패한다. 에어갭 배포는 fpdf2 또는 reportlab 등 순수 Python 라이브러리를 선택한다.
- **프로젝트 구조 설명 미동기화**: reporter_pdf.py를 WeasyPrint → fpdf2로 교체 후 CLAUDE.md 상단 구조 주석에 남은 `WeasyPrint` 언급을 갱신하지 않아 혼란 발생. 의존성 변경 시 문서 구조 설명도 함께 수정한다.
- **fpdf2 셀 색상 지정 후 초기화 누락**: `set_fill_color()`/`set_text_color()` 설정은 이후 모든 셀에 전파된다. 특정 셀에만 색상 적용 후 반드시 기본값(`set_text_color(0, 0, 0)`)으로 복원한다.
- **의존성 도구 교체 후 참조 잔류**: `requirements.txt` → `pyproject.toml/uv` 전환 시 build.sh, build.ps1, README.md, SKILL.md 등의 참조를 일괄 갱신하지 않으면 혼란이 발생한다. 도구 교체 후 `grep -r "requirements.txt" .`으로 잔류 참조를 전수 확인한다.
- **ruff 줄 길이 불일치**: ruff 기본값(88)과 `pyproject.toml [tool.ruff] line-length = 100` 설정이 다를 경우 CI/로컬 결과가 달라진다. `pyproject.toml`에 `line-length`를 명시하여 일관성을 유지한다.
- **`multi_cell` fill 전용 사용 시 테두리 누락**: `fill=True`만 설정하면 배경색만 적용되고 테두리가 없어 박스 구분이 어렵다. 내용 박스에는 `border=1`을 함께 지정한다.
- **PowerShell `Copy-Item -Recurse` 대상 기존 디렉토리 존재 시 중첩 복사**: 대상 경로(`"build\dist\scripts\windows"`)가 이미 존재하면 소스 폴더 자체가 내부에 복사되어 `scripts\windows\windows\PC-01.ps1`처럼 중첩된다. `New-Item -ItemType Directory -Force` 로 대상 디렉토리를 먼저 생성한 뒤 `"scripts\windows\*"` 와일드카드로 내용물만 복사해야 한다.
