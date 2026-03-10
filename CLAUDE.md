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
uv run python -m py_compile runner/models.py runner/detector.py runner/credentials.py \
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

## Lessons Learned

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

## Common Mistakes

- **`set -e` 스크립트에서 grep 무방비 사용**: `grep pattern file`이 매치 없을 때 exit 1을 반환하는 것을 간과하여 스크립트가 중단된다. `|| true`를 빠뜨리지 않는다.
- **PyInstaller 배포 전 라이브러리 로드 경로 미검증**: WSL2처럼 동일 `.so`가 두 경로에 공존하는 환경에서 빌드는 성공하나 실행이 실패한다. 배포 전 `ldd ./binary` 또는 `LD_DEBUG=libs ./binary 2>&1 | grep struct`로 경로를 검증한다.
- **에어갭 배포에 WeasyPrint 선택**: 시스템 패키지 의존성이 크므로 오프라인 환경에서 실패한다. 에어갭 배포는 fpdf2 또는 reportlab 등 순수 Python 라이브러리를 선택한다.
- **프로젝트 구조 설명 미동기화**: reporter_pdf.py를 WeasyPrint → fpdf2로 교체 후 CLAUDE.md 상단 구조 주석에 남은 `WeasyPrint` 언급을 갱신하지 않아 혼란 발생. 의존성 변경 시 문서 구조 설명도 함께 수정한다.
- **fpdf2 셀 색상 지정 후 초기화 누락**: `set_fill_color()`/`set_text_color()` 설정은 이후 모든 셀에 전파된다. 특정 셀에만 색상 적용 후 반드시 기본값(`set_text_color(0, 0, 0)`)으로 복원한다.
- **의존성 도구 교체 후 참조 잔류**: `requirements.txt` → `pyproject.toml/uv` 전환 시 build.sh, build.ps1, README.md, SKILL.md 등의 참조를 일괄 갱신하지 않으면 혼란이 발생한다. 도구 교체 후 `grep -r "requirements.txt" .`으로 잔류 참조를 전수 확인한다.
- **ruff 줄 길이 불일치**: ruff 기본값(88)과 `pyproject.toml [tool.ruff] line-length = 100` 설정이 다를 경우 CI/로컬 결과가 달라진다. `pyproject.toml`에 `line-length`를 명시하여 일관성을 유지한다.
- **`multi_cell` fill 전용 사용 시 테두리 누락**: `fill=True`만 설정하면 배경색만 적용되고 테두리가 없어 박스 구분이 어렵다. 내용 박스에는 `border=1`을 함께 지정한다.
