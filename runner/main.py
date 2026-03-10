from __future__ import annotations

import socket
import sys
from datetime import datetime
from pathlib import Path

from .credentials import collect_credentials
from .detector import detect_os_kind, run_preflight
from .executor import build_script_meta, run_script
from .models import OSKind, ResultCode, RunSession
from .reporter_json import write_json
from .reporter_pdf import write_pdf

SCRIPT_EXT = {
    OSKind.LINUX: "*.sh",
    OSKind.WINDOWS_SERVER: "*.ps1",
    OSKind.WINDOWS: "*.ps1",
}


def _print_summary(session: RunSession) -> None:
    counts: dict[str, int] = {"PASS": 0, "FAIL": 0, "ERROR": 0, "TIMEOUT": 0}
    fail_ids: list[str] = []

    for r in session.results:
        counts[r.code.name] += 1
        if r.code == ResultCode.FAIL:
            fail_ids.append(r.meta.script_id)

    print("\n" + "=" * 50)
    print("점검 완료")
    print(f"  양호(PASS)  : {counts['PASS']}개")
    print(f"  취약(FAIL)  : {counts['FAIL']}개")
    print(f"  오류(ERROR) : {counts['ERROR']}개")
    print(f"  타임아웃    : {counts['TIMEOUT']}개")

    if fail_ids:
        print(f"\n취약 항목: {', '.join(fail_ids)}")

    print("\n※ 본 결과는 자동화 점검 참조용이며 최종 판정은 수동 검증이 필요합니다.")
    print("=" * 50)


def main() -> None:
    # [1] OS 탐지
    try:
        os_kind = detect_os_kind()
    except RuntimeError as exc:
        print(f"[오류] {exc}")
        sys.exit(1)

    print(f"[정보] 탐지된 OS: {os_kind}")

    # [2] Preflight (관리자 권한 없으면 exit(1))
    warnings = run_preflight(os_kind)
    for w in warnings:
        print(f"[경고] {w}")

    # [3] 자격증명 수집
    creds = collect_credentials(os_kind)

    # [4] 스크립트 목록
    # PyInstaller --onefile: 실행파일 위치 기준, 일반 실행: 소스 루트 기준
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent.parent

    scripts_dir = base_dir / "scripts" / os_kind
    if not scripts_dir.exists():
        print(f"[오류] 스크립트 디렉토리 없음: {scripts_dir}")
        sys.exit(1)

    ext = SCRIPT_EXT[os_kind]
    script_paths = sorted(scripts_dir.glob(ext))
    if not script_paths:
        print(f"[오류] 스크립트 없음: {scripts_dir / ext}")
        sys.exit(1)

    print(f"[정보] {len(script_paths)}개 스크립트 실행 예정")

    # [5] 세션 초기화
    session = RunSession(
        started_at=datetime.now(),
        os_kind=os_kind,
        hostname=socket.gethostname(),
        preflight_warnings=warnings,
    )

    # [6] 스크립트 순차 실행
    for script_path in script_paths:
        meta = build_script_meta(script_path, os_kind)
        result = run_script(meta, creds)
        session.results.append(result)
        status_icon = "✓" if result.code == ResultCode.PASS else "✗"
        print(f"  [{status_icon}] {meta.script_id:8s} {result.code.name:<8s}"
              f" ({result.elapsed_sec:.1f}s)")

    # [7] 터미널 요약
    _print_summary(session)

    # [8] 결과 파일 출력
    out_dir = base_dir / "results"
    out_dir.mkdir(exist_ok=True)

    json_path = write_json(session, out_dir)
    print(f"\nJSON: {json_path}")

    try:
        pdf_path = write_pdf(session, out_dir)
        print(f"PDF:  {pdf_path}")
    except RuntimeError as exc:
        print(f"[경고] PDF 생성 실패: {exc}")
        print("       JSON 결과는 정상 저장되었습니다.")


if __name__ == "__main__":
    main()
