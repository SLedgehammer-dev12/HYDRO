from __future__ import annotations

import importlib.util
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PAGE_SIZE = A4
UNICODE_FONT_NAME = "HidrostatikUnicode"
UNICODE_FONT_BOLD_NAME = "HidrostatikUnicode-Bold"
_FALLBACK_FONT_NAME = "Helvetica"
_FALLBACK_FONT_BOLD_NAME = "Helvetica-Bold"
FONT_FILENAME = "DejaVuSans.ttf"
FONT_BOLD_FILENAME = "DejaVuSans-Bold.ttf"

# Excel formula enjeksiyonuna karsi notrlenen oncul karakterler.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _dejavu_font_directories() -> list[Path]:
    directories: list[Path] = []
    env_dir = os.environ.get("HYDRO_PDF_FONT_DIR", "").strip()
    if env_dir:
        directories.append(Path(env_dir))
    directories.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/dejavu"),
            Path("/usr/local/share/fonts"),
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("C:/Windows/Fonts"),
            Path(__file__).resolve().parents[2] / "assets" / "fonts",
        ]
    )
    spec = importlib.util.find_spec("matplotlib")
    if spec is not None and spec.origin:
        directories.append(Path(spec.origin).parent / "mpl-data" / "fonts" / "ttf")
    return directories


def _find_font(filename: str) -> Path | None:
    for directory in _dejavu_font_directories():
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


_font_names: tuple[str, str] | None = None


def _report_fonts() -> tuple[str, str]:
    """DejaVuSans varsa kaydeder; yoksa Helvetica'ya duser."""
    global _font_names
    if _font_names is not None:
        return _font_names

    regular = _find_font(FONT_FILENAME)
    if regular is None:
        _font_names = (_FALLBACK_FONT_NAME, _FALLBACK_FONT_BOLD_NAME)
        return _font_names

    bold = _find_font(FONT_BOLD_FILENAME) or regular
    try:
        if UNICODE_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(UNICODE_FONT_NAME, str(regular)))
        if UNICODE_FONT_BOLD_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(UNICODE_FONT_BOLD_NAME, str(bold)))
    except Exception:  # bozuk/erisilemez font -> guvenli geri donus
        _font_names = (_FALLBACK_FONT_NAME, _FALLBACK_FONT_BOLD_NAME)
        return _font_names

    _font_names = (UNICODE_FONT_NAME, UNICODE_FONT_BOLD_NAME)
    return _font_names


def _escape_paragraph_text(value: Any) -> str:
    """Kullanici metnini ReportLab Paragraph markup'indan kacar.

    ``&``, ``<`` ve ``>`` karakterleri varlik olarak kodlanir; satir sonlari
    Paragraph icinde satir kirilmasina cevrilir.
    """
    text = str(value)
    escaped = escape(text)
    return escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")


def _neutralize_excel_text(value: str) -> str:
    """Excel/CSV formul enjeksiyonunu notrler (``=cmd`` -> ``'=cmd``)."""
    if value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _excel_value(value: Any) -> Any:
    """Sayisal degerleri sayi olarak, metinleri notrlenmis olarak dondurur."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value
    if value is None:
        return ""
    return _neutralize_excel_text(str(value))


def _atomic_target(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}-",
        suffix=output_path.suffix or ".tmp",
        dir=str(output_path.parent),
    )
    os.close(handle)
    return Path(temp_name)


def _table_paragraphs(
    data: dict[str, Any],
    key_style: ParagraphStyle,
    value_style: ParagraphStyle,
    empty_message: str,
) -> list[Any]:
    rows = [
        [
            Paragraph(f"<b>{_escape_paragraph_text(key)}:</b>", key_style),
            Paragraph(_escape_paragraph_text(value), value_style),
        ]
        for key, value in data.items()
    ]
    if not rows:
        return [Paragraph(_escape_paragraph_text(empty_message), value_style)]
    table = Table(rows, colWidths=[150, 350])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return [table]


def export_pdf_report(
    output_path: Path,
    report_title: str,
    metadata: dict[str, Any],
    geometry_data: dict[str, Any],
    test_results: dict[str, Any],
    checklist_data: list[dict[str, Any]],
) -> None:
    regular_font, bold_font = _report_fonts()
    temp_path = _atomic_target(output_path)
    try:
        doc = SimpleDocTemplate(
            str(temp_path),
            pagesize=PAGE_SIZE,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54,
        )
        story: list[Any] = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontName=bold_font,
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#16365D"),
            spaceAfter=12,
        )
        section_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontName=bold_font,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#243B73"),
            spaceBefore=12,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["Normal"],
            fontName=regular_font,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#333333"),
        )
        bold_body_style = ParagraphStyle(
            "ReportBodyBold",
            parent=body_style,
            fontName=bold_font,
        )

        # Title
        story.append(Paragraph(_escape_paragraph_text(report_title), title_style))
        story.append(Spacer(1, 10))

        # Metadata Section
        story.append(Paragraph("Metadata &amp; Context", section_style))
        story.extend(_table_paragraphs(metadata, body_style, body_style, "Kayit yok."))
        story.append(Spacer(1, 15))

        # Geometry Section
        story.append(Paragraph("Pipe Geometry Details", section_style))
        story.extend(_table_paragraphs(geometry_data, body_style, body_style, "Kayit yok."))
        story.append(Spacer(1, 15))

        # Test Results Section
        story.append(Paragraph("Hydrostatic Test Evaluation Results", section_style))
        value_style = bold_body_style
        rows = []
        for key, value in test_results.items():
            row_style = (
                bold_body_style if str(key).lower() in {"passed", "durum", "result"} else body_style
            )
            rows.append(
                [
                    Paragraph(f"<b>{_escape_paragraph_text(key)}:</b>", body_style),
                    Paragraph(_escape_paragraph_text(value), row_style),
                ]
            )
        if rows:
            results_table = Table(rows, colWidths=[150, 350])
            results_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(results_table)
        else:
            story.append(Paragraph(_escape_paragraph_text("Kayit yok."), value_style))
        story.append(Spacer(1, 15))

        # Checklist Section
        if checklist_data:
            story.append(Paragraph("Operation Field Checklist", section_style))
            checklist_rows = [
                [
                    Paragraph(
                        "<b>Status</b>",
                        bold_body_style,
                    ),
                    Paragraph(
                        "<b>Control Point / Requirement</b>",
                        bold_body_style,
                    ),
                ]
            ]
            for item in checklist_data:
                status_text = "[X]" if item.get("checked") else "[ ]"
                label = _escape_paragraph_text(item.get("label", ""))
                ref = _escape_paragraph_text(item.get("ref", ""))
                checklist_rows.append(
                    [
                        Paragraph(status_text, bold_body_style),
                        Paragraph(f"{label} ({ref})", body_style),
                    ]
                )
            checklist_table = Table(checklist_rows, colWidths=[60, 440])
            checklist_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                    ]
                )
            )
            story.append(checklist_table)

        doc.build(story)
        os.replace(temp_path, output_path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def export_excel_report(
    output_path: Path,
    report_title: str,
    metadata: dict[str, Any],
    geometry_data: dict[str, Any],
    test_results: dict[str, Any],
    checklist_data: list[dict[str, Any]],
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Hydrostatic Test Report"

    # Enable grid lines explicitly
    worksheet.views.sheetView[0].showGridLines = True

    # Styling
    title_font = Font(name="Arial", size=16, bold=True, color="16365D")
    section_font = Font(name="Arial", size=12, bold=True, color="243B73")
    header_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    bold_font = Font(name="Arial", size=10, bold=True, color="333333")
    regular_font = Font(name="Arial", size=10, color="333333")

    header_fill = PatternFill(start_color="16365D", end_color="16365D", fill_type="solid")
    section_fill = PatternFill(start_color="EAF2FF", end_color="EAF2FF", fill_type="solid")

    thin_border = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC"),
    )

    # Title
    worksheet["A1"] = _neutralize_excel_text(str(report_title))
    worksheet["A1"].font = title_font
    worksheet.row_dimensions[1].height = 30

    current_row = 3

    # Helper function to write simple dicts as table sections
    def write_section(section_title: str, data: dict[str, Any]) -> None:
        nonlocal current_row
        title_cell = worksheet.cell(
            row=current_row, column=1, value=_neutralize_excel_text(section_title)
        )
        title_cell.font = section_font
        title_cell.fill = section_fill
        worksheet.merge_cells(
            start_row=current_row, start_column=1, end_row=current_row, end_column=2
        )
        current_row += 1

        for key, value in data.items():
            cell_key = worksheet.cell(
                row=current_row, column=1, value=_neutralize_excel_text(str(key))
            )
            cell_value = worksheet.cell(row=current_row, column=2, value=_excel_value(value))
            cell_key.font = bold_font
            cell_value.font = regular_font
            cell_key.border = thin_border
            cell_value.border = thin_border
            current_row += 1
        current_row += 1  # blank space

    # Write Sections
    write_section("Metadata & Context", metadata)
    write_section("Pipe Geometry Details", geometry_data)
    write_section("Hydrostatic Test Evaluation Results", test_results)

    # Checklist Section
    if checklist_data:
        checklist_title = worksheet.cell(
            row=current_row,
            column=1,
            value=_neutralize_excel_text("Operation Field Checklist"),
        )
        checklist_title.font = section_font
        checklist_title.fill = section_fill
        worksheet.merge_cells(
            start_row=current_row, start_column=1, end_row=current_row, end_column=2
        )
        current_row += 1

        cell_h1 = worksheet.cell(row=current_row, column=1, value="Status")
        cell_h2 = worksheet.cell(row=current_row, column=2, value="Control Point / Requirement")
        cell_h1.font = header_font
        cell_h2.font = header_font
        cell_h1.fill = header_fill
        cell_h2.fill = header_fill
        current_row += 1

        for item in checklist_data:
            status_val = "Checked" if item.get("checked") else "Unchecked"
            cell_status = worksheet.cell(row=current_row, column=1, value=status_val)
            label = _neutralize_excel_text(str(item.get("label", "")))
            ref = _neutralize_excel_text(str(item.get("ref", "")))
            cell_label = worksheet.cell(row=current_row, column=2, value=f"{label} ({ref})")
            cell_status.font = bold_font
            cell_label.font = regular_font
            cell_status.border = thin_border
            cell_label.border = thin_border
            current_row += 1

    # Auto-adjust column widths
    for column in worksheet.columns:
        max_len = 0
        column_letter = column[0].column_letter
        for cell in column:
            if cell.value:
                # ignore merged cells/titles for width calculation
                if (
                    cell.row == 1
                    or "Checklist" in str(cell.value)
                    or "Metadata" in str(cell.value)
                    or "Results" in str(cell.value)
                    or "Details" in str(cell.value)
                ):
                    continue
                max_len = max(max_len, len(str(cell.value)))
        worksheet.column_dimensions[column_letter].width = max(max_len + 3, 12)

    temp_path = _atomic_target(output_path)
    try:
        workbook.save(str(temp_path))
        os.replace(temp_path, output_path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


__all__ = [
    "export_excel_report",
    "export_pdf_report",
]
