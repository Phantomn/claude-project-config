from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .models import ResultCode, RunSession

if TYPE_CHECKING:
    from fpdf import FPDF as FPDFType


# Ubuntu/Windows 기본 경로 탐색 순서 (네트워크 불필요)
_SYSTEM_FONT_CANDIDATES: list[Path] = [
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"),
    Path("/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf"),
    Path("C:/Windows/Fonts/malgun.ttf"),   # Windows Malgun Gothic
    Path("C:/Windows/Fonts/gulim.ttc"),
]


def _get_font_path() -> Path | None:
    """한글 폰트 경로 반환. 없으면 None (내장 폰트 폴백)."""
    # 1. PyInstaller 번들
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "fonts" / "NotoSansKR.ttf"  # type: ignore[attr-defined]
        return p if p.exists() else None
    # 2. runner/fonts/ 로컬 배치 파일
    local = Path(__file__).parent / "fonts" / "NotoSansKR.ttf"
    if local.exists():
        return local
    # 3. 시스템 기본 경로 탐색
    for p in _SYSTEM_FONT_CANDIDATES:
        if p.exists():
            return p
    return None


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
    use_korean = font_path is not None and font_path.exists()
    font_name = "NotoSansKR" if use_korean else "Helvetica"

    pass_items = [r for r in session.results if r.code == ResultCode.PASS]
    fail_items = [r for r in session.results if r.code == ResultCode.FAIL]
    error_items = [r for r in session.results if r.code in (ResultCode.ERROR, ResultCode.TIMEOUT)]

    pdf = FPDF()
    if use_korean:
        pdf.add_font(font_name, fname=str(font_path))
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- 표지 ---
    pdf.add_page()
    if not use_korean:
        pdf.set_font(font_name, size=9)
        pdf.set_text_color(180, 0, 0)
        pdf.cell(0, 6, "[Korean font not found - Korean text may not render correctly]",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_name, size=20)
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
