from __future__ import annotations

from pathlib import Path

from .docx_parser import parse_docx
from .pdf_parser import parse_pdf


def parse_document(path: str | Path, schema_version: str = "1.0.0"):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(path, schema_version=schema_version)
    if suffix == ".pdf":
        return parse_pdf(path, schema_version=schema_version)
    raise ValueError(f"不支持的文件格式: {suffix}; 当前仅支持 .docx / .pdf")
