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

## Lessons Learned

- **스크립트 버그 수정 전 Phase 0 완료 필수**: runner 구현 전 반드시 W-69/W-10/W-04 버그 수정
- **Windows 자격증명 MVP 제약**: v1은 현재 프로세스 컨텍스트 사용, v2에서 `CreateProcessWithLogonW` 구현 예정
