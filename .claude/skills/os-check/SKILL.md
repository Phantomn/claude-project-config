---
name: os-check
description: 주요정보통신기반시설 OS 하드닝 점검 실행 및 결과 해석
triggers: ["/os-check", "점검 실행", "os 점검", "하드닝 점검", "취약점 점검"]
---

# OS 하드닝 점검 스킬

주요정보통신기반시설 기술적 취약점 분석·평가 기준에 따른 OS 하드닝 점검을 실행하고 결과를 해석합니다.

## 사전 요건

- **Python 3.10+** 설치
- **관리자 권한**: Linux는 root/sudo, Windows는 Administrator
- PDF 출력 필요 시: `uv sync`

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python -m runner.main

# 또는
cd /path/to/vuln-os
python -m runner.main
```

## 결과 해석

| 상태 | 의미 | 조치 |
|------|------|------|
| PASS | 양호 (점검 결과: 0) | 없음 |
| FAIL | 취약 (점검 결과: N≥1) | 수동 검증 후 조치 |
| ERROR | 스크립트 오류/파싱 실패 | 스크립트 직접 확인 |
| TIMEOUT | 타임아웃 초과 | 수동 실행 후 확인 |

## 결과 파일 확인

```bash
# 취약 항목만 추출
jq '.items[] | select(.code=="FAIL") | {id, value}' results/최신.json

# 오류 항목 확인
jq '.items[] | select(.code=="ERROR" or .code=="TIMEOUT")' results/최신.json

# 요약 보기
jq '.summary' results/최신.json
```

## 알려진 오탐 항목

점검 환경에 따라 아래 항목은 오탐이 발생할 수 있으므로 수동 검증 필요:

| 항목 | 오탐 조건 |
|------|----------|
| U-06, U-13, U-15, U-58 | find / 탐색 시간 초과 (대용량 파일시스템) |
| PC-08 | WMI Win32_Product 쿼리 지연 |
| W-04~55 secedit 항목 | 도메인 정책 vs 로컬 정책 충돌 |

## Workflow

1. `python -m runner.main` 실행
2. 터미널 요약 확인 (PASS/FAIL/ERROR 카운트)
3. `results/*.json` 취약 항목 분석
4. FAIL 항목 수동 검증
5. `results/*.pdf` 보고서 배포

## 주의사항

- **자격증명 보안**: sudo 비밀번호는 stdin pipe로만 전달, 로그에 기록되지 않음
- **수동 검증 필수**: 자동화 점검은 참조용, 최종 판정은 수동 검증 필요
- **Windows**: 반드시 관리자 권한 PowerShell에서 실행
