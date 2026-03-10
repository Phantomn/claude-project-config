# vuln-os Reviewer Memory

## 프로젝트 컨텍스트
- 주요정보통신기반시설 OS 하드닝 자동화 점검 도구
- Linux(U-01~70.sh) + Windows Server(W-01~82.ps1) + Windows PC(PC-01~18.ps1)
- PDF 리포터: fpdf2(순수 Python), PyInstaller 단일 바이너리 에어갭 배포

## 확인된 수정 완료 사항
- reporter_pdf.py:53 `font_path is not None and font_path.exists()` - 버그 수정 완료
- W-69.ps1 elif→elseif, W-10.ps1 Invok-WebRequest 오타, W-04.ps1 locskDuration 오타 수정 완료
- build.sh: LD_LIBRARY_PATH 우선순위, 폰트 탐색(fc-list + 하드코딩 경로) 구현됨

## 리뷰 포인트 (이 프로젝트 특화)
- set -e 스크립트에서 grep 사용 시 `|| true` 누락 여부
- PyInstaller 배포 전 LD_LIBRARY_PATH 검증 여부 (WSL2 이중 libpython 위험)
- fpdf2 API: XPos/YPos 열거형 필수 (fpdf2 2.7+), 문자열 "LMARGIN" 사용 불가
- Windows 폰트는 런타임 탐색(_SYSTEM_FONT_CANDIDATES)으로 커버, 빌드 시 번들 불필요

## CLAUDE.md 미반영 신규 항목
- fpdf2 2.7+ API: `new_x=XPos.LMARGIN`, `new_y=YPos.NEXT` 열거형 사용 필수. 구 버전 문자열 인자 불가.
