from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .models import ResultCode, RunSession

if TYPE_CHECKING:
    from fpdf import FPDF as FPDFType


def _get_font_path() -> Path:
    """PyInstaller --onefile 번들과 일반 실행 모두 대응."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "fonts" / "NotoSansKR.ttf"  # type: ignore[attr-defined]
    return Path(__file__).parent / "fonts" / "NotoSansKR.ttf"


def write_pdf(session: RunSession, out_dir: Path) -> Path:
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError as exc:
        raise RuntimeError(
            f"PDF 생성 의존성 오류: {exc}\n"
            "설치: pip install fpdf2"
        ) from exc

    font_path = _get_font_path()
    if not font_path.exists():
        raise RuntimeError(
            f"한글 폰트 없음: {font_path}\n"
            "빌드 시 build.sh가 자동으로 배치합니다.\n"
            "수동: runner/fonts/NotoSansKR.ttf 파일을 배치하세요."
        )

    pass_items = [r for r in session.results if r.code == ResultCode.PASS]
    fail_items = [r for r in session.results if r.code == ResultCode.FAIL]
    error_items = [r for r in session.results if r.code in (ResultCode.ERROR, ResultCode.TIMEOUT)]

    pdf = FPDF()
    pdf.add_font("NotoSansKR", fname=str(font_path))
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- 표지 ---
    pdf.add_page()
    pdf.set_font("NotoSansKR", size=20)
    pdf.cell(0, 15, "OS 하드닝 점검 보고서", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(5)

    pdf.set_font("NotoSansKR", size=11)
    for label, value in [
        ("점검 일시", session.started_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("대상 OS", session.os_kind),
        ("호스트명", session.hostname),
        ("총 점검 항목", f"{len(session.results)}개"),
    ]:
        pdf.cell(40, 8, f"{label}:", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(0, 8, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    # --- 요약표 ---
    pdf.set_font("NotoSansKR", size=13)
    pdf.cell(0, 10, "점검 요약", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("NotoSansKR", size=11)

    for label, count in [
        ("양호 (PASS)", len(pass_items)),
        ("취약 (FAIL)", len(fail_items)),
        ("오류/타임아웃", len(error_items)),
    ]:
        pdf.cell(50, 8, label, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(30, 8, str(count), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    # --- 사전 점검 경고 ---
    if session.preflight_warnings:
        pdf.set_font("NotoSansKR", size=13)
        pdf.cell(0, 10, "사전 점검 경고", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("NotoSansKR", size=10)
        for w in session.preflight_warnings:
            pdf.multi_cell(0, 7, f"  - {w}")
        pdf.ln(3)

    # --- 취약 항목 ---
    if fail_items:
        pdf.add_page()
        pdf.set_font("NotoSansKR", size=13)
        pdf.cell(0, 10, f"취약 항목 ({len(fail_items)}개)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("NotoSansKR", size=10)
        _write_result_table(pdf, fail_items)

    # --- 오류 항목 ---
    if error_items:
        pdf.add_page()
        pdf.set_font("NotoSansKR", size=13)
        pdf.cell(0, 10, f"오류/타임아웃 항목 ({len(error_items)}개)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("NotoSansKR", size=10)
        _write_result_table(pdf, error_items)

    # --- 전체 항목 상세 ---
    pdf.add_page()
    pdf.set_font("NotoSansKR", size=13)
    pdf.cell(0, 10, "전체 항목 상세", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("NotoSansKR", size=10)
    _write_result_table(pdf, session.results)

    # --- 면책 문구 ---
    pdf.ln(8)
    pdf.set_font("NotoSansKR", size=9)
    pdf.multi_cell(
        0, 6,
        "본 결과는 자동화 점검 참조용이며 최종 판정은 수동 검증이 필요합니다.\n"
        "자동화 점검은 설정 오류, 환경 차이, 스크립트 제한으로 인해 오탐/미탐이 발생할 수 있습니다.",
    )

    filename = session.started_at.strftime("%Y%m%d_%H%M%S") + ".pdf"
    out_path = out_dir / filename
    pdf.output(str(out_path))
    return out_path


def _write_result_table(pdf: "FPDFType", items: list) -> None:
    from fpdf.enums import XPos, YPos

    # 유효 너비: A4 210mm - 양쪽 여백 10mm*2 = 190mm
    usable_w = pdf.w - pdf.l_margin - pdf.r_margin
    col_id = 20
    col_code = 22
    col_val = 12
    col_elapsed = 20
    col_err = usable_w - col_id - col_code - col_val - col_elapsed  # 116mm

    # 헤더
    pdf.set_fill_color(220, 220, 220)
    for text, w in [("ID", col_id), ("결과", col_code), ("값", col_val), ("경과(s)", col_elapsed), ("오류", col_err)]:
        is_last = (text == "오류")
        pdf.cell(
            w, 7, text, border=1, fill=True,
            new_x=XPos.LMARGIN if is_last else XPos.RIGHT,
            new_y=YPos.NEXT if is_last else YPos.TOP,
        )

    for r in items:
        err_txt = r.error_message[:60] if r.error_message else ""
        for text, w in [
            (r.meta.script_id, col_id),
            (r.code.name, col_code),
            (str(r.parsed_value), col_val),
            (f"{r.elapsed_sec:.1f}", col_elapsed),
            (err_txt, col_err),
        ]:
            is_last = (w == col_err)
            pdf.cell(
                w, 6, text, border=1,
                new_x=XPos.LMARGIN if is_last else XPos.RIGHT,
                new_y=YPos.NEXT if is_last else YPos.TOP,
            )
