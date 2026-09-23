from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourceLocator:
    kind: str
    index: int | None = None
    page: int | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None
    part: str | None = None


@dataclass
class RunStyle:
    text: str
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    font_name: str | None = None
    font_size_pt: float | None = None


@dataclass
class ParagraphIR:
    id: str
    text: str
    order: int
    style_name: str | None = None
    heading_level: int | None = None
    alignment: str | None = None
    line_spacing: float | str | None = None
    runs: list[RunStyle] = field(default_factory=list)
    source_locator: SourceLocator | None = None


@dataclass
class TableIR:
    id: str
    order: int
    rows: list[list[str]]
    source_locator: SourceLocator | None = None


@dataclass
class ImageIR:
    id: str
    order: int
    filename: str | None
    content_type: str | None
    width_px: int | None = None
    height_px: int | None = None
    sha256: str | None = None
    phash: str | None = None
    mean_rgb: list[int] | None = None
    source_locator: SourceLocator | None = None


@dataclass
class FormatMeta:
    section_count: int = 0
    page_width_cm: float | None = None
    page_height_cm: float | None = None
    margin_top_cm: float | None = None
    margin_bottom_cm: float | None = None
    margin_left_cm: float | None = None
    margin_right_cm: float | None = None
    header_texts: list[str] = field(default_factory=list)
    footer_texts: list[str] = field(default_factory=list)


@dataclass
class DocumentIR:
    schema_version: str
    document_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    sha256: str
    page_count: int | None
    paragraphs: list[ParagraphIR] = field(default_factory=list)
    tables: list[TableIR] = field(default_factory=list)
    images: list[ImageIR] = field(default_factory=list)
    format_meta: FormatMeta = field(default_factory=FormatMeta)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
