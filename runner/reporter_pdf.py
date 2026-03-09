from __future__ import annotations

import sys
from pathlib import Path

from .models import ResultCode, RunSession


def _get_template_dir() -> Path:
    """PyInstaller --onefile 번들과 일반 실행 모두 대응."""
    if getattr(sys, "frozen", False):
        # PyInstaller가 데이터 파일을 추출하는 임시 디렉토리
        return Path(sys._MEIPASS) / "templates"  # type: ignore[attr-defined]
    return Path(__file__).parent / "templates"


def write_pdf(session: RunSession, out_dir: Path) -> Path:
    try:
        from jinja2 import Environment, FileSystemLoader
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        # OSError: cffi가 libpango 등 시스템 공유 라이브러리를 동적 로드 실패 시 발생
        raise RuntimeError(
            f"PDF 생성 의존성 오류: {exc}\n"
            "시스템 패키지 설치 필요:\n"
            "  Ubuntu: sudo apt-get install libcairo2 libpango-1.0-0 libpangocairo-1.0-0 "
            "libgdk-pixbuf2.0-0 libffi-dev shared-mime-info\n"
            "에어갭 환경: JSON 결과(results/*.json)만 활용 가능합니다."
        ) from exc

    template_dir = _get_template_dir()
    template_name = "report.html.j2"

    pass_items = [r for r in session.results if r.code == ResultCode.PASS]
    fail_items = [r for r in session.results if r.code == ResultCode.FAIL]
    error_items = [r for r in session.results if r.code in (ResultCode.ERROR, ResultCode.TIMEOUT)]

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template(template_name)

    html_content = template.render(
        session=session,
        pass_items=pass_items,
        fail_items=fail_items,
        error_items=error_items,
        all_items=session.results,
        ResultCode=ResultCode,
    )

    filename = session.started_at.strftime("%Y%m%d_%H%M%S") + ".pdf"
    out_path = out_dir / filename
    HTML(string=html_content).write_pdf(str(out_path))
    return out_path
