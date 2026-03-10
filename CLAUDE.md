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
├── templates/
│   └── report.html.j2
├── main.py            # 진입점
└── requirements.txt

results/               # 출력 디렉토리 (.gitignore)
```

## 실행 방법

```bash
# 의존성 설치
pip install -r runner/requirements.txt
# PDF 라이브러리(fpdf2)는 순수 Python - 별도 시스템 패키지 불필요

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

## Lessons Learned

- **스크립트 버그 수정 전 Phase 0 완료 필수**: runner 구현 전 반드시 W-69/W-10/W-04 버그 수정
- **Windows 자격증명 MVP 제약**: v1은 현재 프로세스 컨텍스트 사용, v2에서 `CreateProcessWithLogonW` 구현 예정
- **`set -e` 스크립트에서 grep 은 `|| true` 필수**: grep이 매치 없음 시 exit code 1을 반환하므로 `set -e` 환경에서 스크립트가 즉시 종료된다. 의도적으로 "없을 수도 있는" grep은 반드시 `grep ... || true` 패턴을 사용한다.
- **PyInstaller + WSL2 공유 라이브러리 이중 경로 충돌**: `/usr/local/lib`(비표준 빌드)와 `/lib/x86_64-linux-gnu`(시스템) 두 곳에 `libpython3.X.so`가 공존하면 비표준 빌드가 먼저 로드되어 `_struct` 등 빌트인 모듈이 누락된다. `LD_LIBRARY_PATH=/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH`로 시스템 경로를 우선 지정한다.
- **fpdf2 collect_all 제거 시 PIL hook 연쇄 제거 주의**: fpdf2는 순수 Python이므로 `collect_all('fpdf2')`가 불필요하나, 해당 라인 제거 시 PIL 관련 hook도 함께 빠져 `_struct` 충돌이 발생할 수 있다. PIL/Pillow 사용 시 별도로 명시적 포함(`collect_all('PIL')`)이 필요하다.
- **에어갭 배포는 순수 Python PDF 라이브러리 선택**: WeasyPrint는 GTK·Cairo·Pango 등 시스템 라이브러리에 의존해 오프라인 환경에서 설치/실행이 실패한다. fpdf2(순수 Python) 사용 시 시스템 의존성 없이 PyInstaller 단일 바이너리 배포 가능하다.
- **에어갭 환경 폰트 탐색은 fc-list + 하드코딩 경로 조합**: 네트워크 없이 한글 폰트를 찾을 때 `fc-list` 명령과 `/usr/share/fonts`, `/usr/local/share/fonts` 경로를 조합한다. 폰트 미발견 시 내장 Helvetica 폴백으로 항상 실행 가능성을 보장한다.
- **WSL2 `find / -perm -4000` 타임아웃 처리**: WSL2 전체 파일시스템 SUID 탐색은 180초 이상 소요될 수 있다. `timeout 180 find / -perm -4000 ...` 래퍼를 적용하고 timeout 종료 코드(124)를 정상으로 처리한다.

## Common Mistakes

- **`set -e` 스크립트에서 grep 무방비 사용**: `grep pattern file`이 매치 없을 때 exit 1을 반환하는 것을 간과하여 스크립트가 중단된다. `|| true`를 빠뜨리지 않는다.
- **PyInstaller 배포 전 라이브러리 로드 경로 미검증**: WSL2처럼 동일 `.so`가 두 경로에 공존하는 환경에서 빌드는 성공하나 실행이 실패한다. 배포 전 `ldd ./binary` 또는 `LD_DEBUG=libs ./binary 2>&1 | grep struct`로 경로를 검증한다.
- **에어갭 배포에 WeasyPrint 선택**: 시스템 패키지 의존성이 크므로 오프라인 환경에서 실패한다. 에어갭 배포는 fpdf2 또는 reportlab 등 순수 Python 라이브러리를 선택한다.
- **프로젝트 구조 설명 미동기화**: reporter_pdf.py를 WeasyPrint → fpdf2로 교체 후 CLAUDE.md 상단 구조 주석에 남은 `WeasyPrint` 언급을 갱신하지 않아 혼란 발생. 의존성 변경 시 문서 구조 설명도 함께 수정한다.
