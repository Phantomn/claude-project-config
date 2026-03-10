# vuln-os — 주요정보통신기반시설 OS 하드닝 점검

주요정보통신기반시설 기술적 취약점 분석·평가 기준에 따른 OS 하드닝 자동화 점검 도구.

## 개요

- **Linux**: U-01 ~ U-70 (70개 항목, Bash)
- **Windows Server**: W-01 ~ W-82 (82개 항목, PowerShell)
- **Windows PC**: PC-01 ~ PC-18 (18개 항목, PowerShell)

Python 오케스트레이터(`runner/`)가 스크립트를 순차 실행하고, 결과를 JSON/PDF로 출력합니다.

## 빠른 시작

### Python이 있는 환경

```bash
# 1. 의존성 설치
uv sync

# 2. 실행 (관리자 권한 필수)
sudo python -m runner.main          # Linux
# Windows: Administrator PowerShell에서
python -m runner.main
```

실행 중 `sudo 비밀번호:` 또는 `관리자 계정:` 프롬프트가 표시됩니다.

### Python이 없는 환경 (에어갭)

분석가 PC에서 단일 실행 파일로 빌드한 뒤 타겟에 전달합니다.

```bash
# 분석가 PC (타겟과 동일 OS/아키텍처에서 빌드)
bash build/build.sh          # Linux 바이너리 생성
# Windows: powershell -File build\build.ps1

# 타겟 서버에 USB 등으로 전달
os-check          ← 실행 파일 (Python 불필요)
scripts/linux/    ← 점검 스크립트

# 타겟 서버에서 실행
sudo ./os-check
```

> OS/아키텍처별로 별도 빌드 필요 (Linux ELF ≠ Windows EXE)

## 결과 확인

```bash
# 취약 항목 추출
jq '.items[] | select(.code=="FAIL") | {id, value}' results/최신.json

# 요약
jq '.summary' results/최신.json
```

결과 파일은 `results/YYYYMMDD_HHMMSS.{json,pdf}` 형식으로 저장됩니다.

## 구조

```
scripts/
├── linux/           U-01~70.sh    (Bash)
├── windows_server/  W-01~82.ps1   (PowerShell)
└── windows/         PC-01~18.ps1  (PowerShell)

runner/
├── models.py        ResultCode, RunSession 등 데이터 모델
├── detector.py      OS 자동 탐지 + 관리자 권한 확인
├── credentials.py   자격증명 수집 (getpass, echo 없음)
├── executor.py      스크립트 실행 + "점검 결과: N" 파싱
├── reporter_json.py JSON 결과 저장
├── reporter_pdf.py  fpdf2 PDF 생성 (순수 Python, 시스템 의존 없음)
├── fonts/
│   └── NotoSansKR.ttf  (build.sh이 자동 배치, .gitignore)
└── main.py          진입점

build/
├── os-check.spec    PyInstaller 스펙 (폰트 번들 포함)
├── build.sh         Linux 바이너리 빌드
├── build.ps1        Windows 바이너리 빌드
├── dist/            빌드 출력 (.gitignore)
└── work/            빌드 캐시 (.gitignore)

entrypoint.py        PyInstaller 진입점
results/             점검 결과 출력 디렉토리 (.gitignore)
```

## 스크립트 출력 규약

모든 스크립트는 마지막 줄에 아래 형식으로 결과를 출력합니다:

```
점검 결과: 0    # 양호 (PASS)
점검 결과: N    # 취약 (FAIL, N ≥ 1)
```

## 결과 코드

| 코드 | 의미 | 원인 |
|------|------|------|
| `PASS` | 양호 | 점검 결과: 0 |
| `FAIL` | 취약 | 점검 결과: N ≥ 1 |
| `ERROR` | 오류 | 스크립트 비정상 종료 또는 파싱 실패 |
| `TIMEOUT` | 타임아웃 | 제한 시간 초과 |

## 타임아웃 설정

| 제한 | 대상 |
|------|------|
| 30s (기본) | 대부분 항목 |
| 60s | W-04,05,15,16,40,46,47,48,49,50,51,54,55 (secedit) |
| 120s | PC-08 (Win32_Product WMI) |
| 180s | U-06,13,15,58 (find / 전체 탐색) |

## 주의사항

- **관리자 권한 필수**: Linux는 root/sudo, Windows는 Administrator
- **수동 검증 필수**: 자동화 점검은 참조용이며 최종 판정은 수동 검증 필요
- **자격증명 보안**: sudo 비밀번호는 stdin pipe만 사용, 로그·히스토리 미기록
- `results/` 디렉토리는 `.gitignore` 처리됨 (결과 파일 미커밋)

## 알려진 버그 수정 이력

| 파일 | 수정 내용 | 날짜 |
|------|-----------|------|
| `W-69.ps1` | `elif` → `elseif` (11곳) | 2026-03-09 |
| `W-10.ps1` | `Invok-WebRequest` → `Invoke-WebRequest` | 2026-03-09 |
| `W-04.ps1` | `locskDuration` → `lockDuration` | 2026-03-09 |
