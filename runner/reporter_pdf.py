from __future__ import annotations

import logging
import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# fonttools 폰트 서브셋팅 경고 억제 (MERG NOT subset 등 노이즈 방지)
logging.getLogger("fontTools").setLevel(logging.ERROR)

from .models import ResultCode, RunSession

# ── Design System 색상 상수 (RGB tuple) ──────────────────────────────────────
NAVY   = (30, 55, 100)
RED    = (200, 50, 50)
GREEN  = (50, 150, 80)
ORANGE = (210, 120, 30)
LGRAY  = (245, 247, 250)
MGRAY  = (180, 180, 180)
DGRAY  = (80, 80, 80)

# ── Typography 상수 (pt) ──────────────────────────────────────────────────────
FS_COVER_TITLE = 26   # 표지 메인 제목
FS_COVER_SUB   = 11   # 표지 부제 / 정보 블록
FS_SECTION     = 13   # 섹션 제목 (모든 섹션 동일)
FS_ITEM_TITLE  = 11   # 상세 섹션 항목 헤더
FS_CARD_NUM    = 18   # 대시보드 카드 숫자
FS_BODY        = 10   # 본문 텍스트
FS_SMALL       =  9   # 보조 텍스트 (헤더, 서브텍스트, 비고, 카드 레이블)
FS_FOOTER      =  8   # 푸터 면책 문구

MAX_OUTPUT_CHARS = 4000

CODE_COLORS: dict[str, tuple[int, int, int]] = {
    "PASS":    GREEN,
    "FAIL":    RED,
    "ERROR":   ORANGE,
    "TIMEOUT": ORANGE,
}

# ── 한글 폰트 탐색 ────────────────────────────────────────────────────────────
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


# ── AuditPDF ──────────────────────────────────────────────────────────────────

class AuditPDF(FPDF):
    """FPDF 서브클래스. 공통 헤더/푸터를 포함한 감사 보고서 기반 클래스."""

    def __init__(self, font_name: str, report_title: str) -> None:
        super().__init__()
        self.font_name = font_name
        self.report_title = report_title

    def header(self) -> None:
        """전 페이지: 보고서명(좌) + 페이지 번호(우) + 하단 구분선.

        표지(page_no() == 1)는 헤더 출력 안 함.
        """
        if self.page_no() == 1:
            return

        self.set_font(self.font_name, size=FS_SMALL)
        self.set_text_color(*DGRAY)
        self.cell(0, 8, self.report_title, new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.cell(0, 8, f"{self.page_no()}", align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*MGRAY)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_text_color(0, 0, 0)
        self.set_draw_color(0, 0, 0)
        self.ln(2)

    def footer(self) -> None:
        """전 페이지: 상단 구분선 + 면책 단문(중앙).

        표지(page_no() == 1)는 footer 없음.
        """
        if self.page_no() == 1:
            return

        self.set_y(-15)
        self.set_draw_color(*MGRAY)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1)
        self.set_font(self.font_name, size=FS_FOOTER)
        self.set_text_color(*DGRAY)
        self.cell(
            0, 5,
            "본 결과는 자동화 점검 참조용이며 수동 검증이 필요합니다.",
            align="C",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        self.set_text_color(0, 0, 0)
        self.set_draw_color(0, 0, 0)


# ── 섹션 제목 헬퍼 ────────────────────────────────────────────────────────────

def _section_title(pdf: AuditPDF, title: str) -> None:
    """섹션 제목 출력 (FS_SECTION, 좌측 정렬)."""
    pdf.set_font(pdf.font_name, size=FS_SECTION)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ── 표지 ──────────────────────────────────────────────────────────────────────

def _write_cover(pdf: AuditPDF, session: RunSession) -> None:
    """표지: 네이비 헤더 블록(0~65mm) + 정보 블록(82mm~)."""
    font_name = pdf.font_name

    # 네이비 헤더 블록
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 65, style="F")

    # 제목 (흰색, FS_COVER_TITLE)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(22)
    pdf.set_font(font_name, size=FS_COVER_TITLE)
    pdf.cell(0, 14, "OS 하드닝 점검 보고서", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # 부제 (흰색, FS_COVER_SUB)
    pdf.set_font(font_name, size=FS_COVER_SUB)
    pdf.cell(0, 8, "주요정보통신기반시설 기술적 취약점 분석·평가", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # 정보 블록 (FS_COVER_SUB)
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(82)
    pdf.set_font(font_name, size=FS_COVER_SUB)

    info_rows = [
        ("점검 일시",    session.started_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("대상 OS",      str(session.os_kind)),
        ("호스트명",     session.hostname),
        ("총 점검 항목", f"{len(session.results)}개"),
    ]
    for label, value in info_rows:
        pdf.set_text_color(*DGRAY)
        pdf.cell(45, 9, f"{label} :", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 9, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ── 요약 대시보드 ─────────────────────────────────────────────────────────────

def _write_dashboard(
    pdf: AuditPDF,
    pass_n: int,
    fail_n: int,
    error_n: int,
    warnings: list[str],
) -> None:
    """요약 대시보드: 상태 카드 3개 + PASS 비율 바 + preflight warnings."""
    font_name = pdf.font_name
    usable_w = pdf.w - pdf.l_margin - pdf.r_margin
    total = pass_n + fail_n + error_n

    # 섹션 제목 (FS_SECTION — _section_title()과 동일)
    pdf.set_font(font_name, size=FS_SECTION)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 12, "점검 결과 요약", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # 카드 3개
    card_w = usable_w / 3
    card_h = 32
    cards = [
        (pass_n,  "PASS",  "양호", GREEN),
        (fail_n,  "FAIL",  "취약", RED),
        (error_n, "ERROR", "오류", ORANGE),
    ]
    start_x = pdf.l_margin
    card_y = pdf.get_y()

    for i, (cnt, code_label, kor_label, color) in enumerate(cards):
        x = start_x + i * card_w

        pdf.set_draw_color(*MGRAY)
        pdf.rect(x, card_y, card_w - 2, card_h, style="D")

        # 숫자 (FS_CARD_NUM, 코드 색상)
        pdf.set_text_color(*color)
        pdf.set_font(font_name, size=FS_CARD_NUM)
        pdf.set_xy(x, card_y + 5)
        pdf.cell(card_w - 2, 9, str(cnt), align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        # 코드 레이블 (FS_SMALL)
        pdf.set_font(font_name, size=FS_SMALL)
        pdf.set_xy(x, card_y + 15)
        pdf.cell(card_w - 2, 6, code_label, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        # 한글 레이블 (FS_SMALL, DGRAY)
        pdf.set_text_color(*DGRAY)
        pdf.set_xy(x, card_y + 22)
        pdf.cell(card_w - 2, 6, kor_label, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

    # PASS 비율 바
    bar_y = card_y + card_h + 6
    bar_h = 7
    pass_ratio = pass_n / total if total > 0 else 0
    pass_w = usable_w * pass_ratio
    rest_w = usable_w - pass_w

    pdf.set_fill_color(*GREEN)
    if pass_w > 0:
        pdf.rect(pdf.l_margin, bar_y, pass_w, bar_h, style="F")
    pdf.set_fill_color(*LGRAY)
    if rest_w > 0:
        pdf.rect(pdf.l_margin + pass_w, bar_y, rest_w, bar_h, style="F")

    pdf.set_y(bar_y + bar_h + 3)
    pdf.set_text_color(*DGRAY)
    pdf.set_font(font_name, size=FS_SMALL)
    pct = int(pass_ratio * 100)
    pdf.cell(0, 6, f"양호 {pass_n}건 / 전체 {total}건 ({pct}%)",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # preflight warnings (FS_BODY)
    if warnings:
        pdf.set_font(font_name, size=FS_BODY)
        pdf.set_text_color(*ORANGE)
        for w in warnings:
            pdf.multi_cell(0, 6, f"  [!] {w}")
        pdf.set_text_color(0, 0, 0)


# ── 취약 항목 목록 (테이블) ───────────────────────────────────────────────────

def _write_fail_table(pdf: AuditPDF, items: list) -> None:
    """취약 항목 목록 테이블 (pdf.table() 사용).

    열: ID(20mm), 값(15mm), 경과(s)(20mm), 비고(125mm)
    비고는 개행을 공백으로 치환 후 60자 제한.
    페이지 넘김 시 헤더 반복(repeat_headings=1).
    """
    from fpdf.enums import TableCellFillMode
    from fpdf.fonts import FontFace

    headings_style = FontFace(color=(255, 255, 255), fill_color=NAVY)
    col_widths = (20, 15, 20, 125)

    with pdf.table(
        headings_style=headings_style,
        cell_fill_color=LGRAY,
        cell_fill_mode=TableCellFillMode.ROWS,
        borders_layout="MINIMAL",
        col_widths=col_widths,
        line_height=6,
        padding=(2, 2),
        repeat_headings=1,
    ) as table:
        hrow = table.row()
        for h in ["ID", "값", "경과(s)", "비고"]:
            hrow.cell(h)
        for r in items:
            row = table.row()
            raw = r.error_message or (r.raw_output or "")
            note = raw.replace("\n", " ").strip()[:60]
            row.cell(r.meta.script_id)
            row.cell(str(r.parsed_value))
            row.cell(f"{r.elapsed_sec:.1f}")
            row.cell(note)


# ── 취약 항목 상세 ────────────────────────────────────────────────────────────

def _write_fail_details(pdf: AuditPDF, items: list) -> None:
    """취약 항목 상세: LGRAY 헤더 블록 + 흰 배경 raw_output 박스 + 항목 간 구분선."""
    font_name = pdf.font_name
    usable_w = pdf.w - pdf.l_margin - pdf.r_margin
    header_h = 20  # 헤더 영역 고정 높이 (제목 10 + 서브텍스트 6 + 여백 4)

    for idx, r in enumerate(items):
        # 헤더가 들어갈 최소 공간 확보 (header_h + 최소 raw 10mm)
        if pdf.get_y() > pdf.h - pdf.b_margin - (header_h + 10):
            pdf.add_page()

        current_y = pdf.get_y()

        # 헤더 배경 (LGRAY)
        pdf.set_fill_color(*LGRAY)
        pdf.rect(pdf.l_margin, current_y, usable_w, header_h, style="F")

        # 좌측 네이비 강조 바 (헤더 전체 높이)
        pdf.set_fill_color(*NAVY)
        pdf.rect(pdf.l_margin, current_y, 4, header_h, style="F")

        # 제목 ([U-01] FAIL) — FS_ITEM_TITLE
        pdf.set_font(font_name, size=FS_ITEM_TITLE)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(pdf.l_margin + 7, current_y + 2)
        pdf.cell(usable_w - 7, 9, f"[{r.meta.script_id}] {r.code.name}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # 서브텍스트 (결과값 + 경과) — FS_SMALL
        pdf.set_font(font_name, size=FS_SMALL)
        pdf.set_text_color(*DGRAY)
        pdf.set_x(pdf.l_margin + 7)
        pdf.cell(usable_w - 7, 6, f"결과값: {r.parsed_value} | 경과: {r.elapsed_sec:.1f}s",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

        # 헤더 하단 여백
        pdf.ln(3)

        # raw_output 박스 (흰 배경 + MGRAY 테두리) — FS_SMALL
        output = r.raw_output or "(출력 없음)"
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (이하 생략 — 전체 내용은 JSON 참조)"
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(*MGRAY)
        pdf.set_line_width(0.3)
        pdf.set_font(font_name, size=FS_SMALL)
        pdf.multi_cell(usable_w, 5, output, fill=True, border=1)

        # 항목 간 구분선 (마지막 항목 제외)
        pdf.ln(3)
        if idx < len(items) - 1:
            pdf.set_draw_color(*MGRAY)
            pdf.set_line_width(0.5)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(5)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.2)


# ── 전체 항목 테이블 ──────────────────────────────────────────────────────────

def _write_all_items(pdf: AuditPDF, items: list) -> None:
    """전체 항목 테이블. ResultCode별 결과 셀 색상 적용."""
    from fpdf.enums import TableCellFillMode
    from fpdf.fonts import FontFace

    headings_style = FontFace(color=(255, 255, 255), fill_color=NAVY)
    col_widths = (20, 22, 15, 20, 103)

    with pdf.table(
        headings_style=headings_style,
        cell_fill_color=LGRAY,
        cell_fill_mode=TableCellFillMode.ROWS,
        borders_layout="MINIMAL",
        col_widths=col_widths,
        line_height=6,
    ) as table:
        hrow = table.row()
        for h in ["ID", "결과", "값", "경과(s)", "비고"]:
            hrow.cell(h)
        for r in items:
            row = table.row()
            code_color = CODE_COLORS.get(r.code.name, (0, 0, 0))
            code_style = FontFace(color=code_color)
            row.cell(r.meta.script_id)
            row.cell(r.code.name, style=code_style)
            row.cell(str(r.parsed_value))
            row.cell(f"{r.elapsed_sec:.1f}")
            row.cell((r.error_message or "")[:80])


# ── 진입점 ────────────────────────────────────────────────────────────────────

def write_pdf(session: RunSession, out_dir: Path) -> Path:
    try:
        from fpdf import FPDF as _check  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            f"PDF 생성 의존성 오류: {exc}\n설치: pip install fpdf2"
        ) from exc

    font_path = _get_font_path()
    use_korean = font_path is not None and font_path.exists()
    font_name  = "NotoSansKR" if use_korean else "Helvetica"

    pass_items  = [r for r in session.results if r.code == ResultCode.PASS]
    fail_items  = [r for r in session.results if r.code == ResultCode.FAIL]
    error_items = [r for r in session.results if r.code in (ResultCode.ERROR, ResultCode.TIMEOUT)]

    pdf = AuditPDF(font_name=font_name, report_title="OS 하드닝 점검 보고서")
    if use_korean:
        pdf.add_font(font_name, fname=str(font_path))
    pdf.set_auto_page_break(auto=True, margin=20)

    # 표지
    pdf.add_page()
    _write_cover(pdf, session)

    # 요약 대시보드
    pdf.add_page()
    _write_dashboard(pdf, len(pass_items), len(fail_items), len(error_items),
                     session.preflight_warnings or [])

    # 취약 항목 목록
    if fail_items:
        pdf.add_page()
        _section_title(pdf, f"취약 항목 ({len(fail_items)}개)")
        _write_fail_table(pdf, fail_items)

    # 취약 항목 상세
    if fail_items:
        pdf.add_page()
        _section_title(pdf, f"취약 항목 상세 출력 ({len(fail_items)}개)")
        _write_fail_details(pdf, fail_items)

    # 전체 항목
    pdf.add_page()
    _section_title(pdf, f"전체 항목 ({len(session.results)}개)")
    _write_all_items(pdf, session.results)

    filename = session.started_at.strftime("%Y%m%d_%H%M%S") + ".pdf"
    out_path  = out_dir / filename
    pdf.output(str(out_path))
    return out_path
