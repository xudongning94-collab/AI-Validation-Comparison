from pathlib import Path

import pymupdf

from bid_compare_agent.parser.pdf_parser import parse_pdf


def test_parse_pdf_uses_current_pymupdf_api(tmp_path: Path):
    path = tmp_path / "sample.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Project implementation plan")
    pdf.save(path)
    pdf.close()

    result = parse_pdf(path)

    assert result.file_type == "pdf"
    assert result.page_count == 1
    assert any("Project implementation plan" in paragraph.text for paragraph in result.paragraphs)
