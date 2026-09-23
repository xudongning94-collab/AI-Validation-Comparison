from __future__ import annotations

from pathlib import Path

import fitz

from bid_compare_agent.models.document_ir import DocumentIR, FormatMeta, ImageIR, ParagraphIR, SourceLocator
from bid_compare_agent.utils.io import bytes_sha256, file_sha256
from bid_compare_agent.utils.image import extract_image_features
from bid_compare_agent.utils.text import normalize_text


def parse_pdf(path: str | Path, schema_version: str = "1.0.0") -> DocumentIR:
    path = Path(path)
    pdf = fitz.open(path)
    paragraphs: list[ParagraphIR] = []
    images: list[ImageIR] = []
    warnings: list[str] = []

    for page_idx, page in enumerate(pdf):
        blocks = page.get_text("blocks")
        for block_idx, block in enumerate(blocks):
            text = normalize_text(block[4] if len(block) > 4 else "")
            if not text:
                continue
            paragraphs.append(
                ParagraphIR(
                    id=f"p-{len(paragraphs)+1:06d}",
                    text=text,
                    order=len(paragraphs),
                    source_locator=SourceLocator(
                        kind="pdf_block",
                        page=page_idx + 1,
                        index=block_idx,
                        paragraph_index=block_idx,
                    ),
                )
            )

        for img_idx, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                meta = pdf.extract_image(xref)
                blob = meta.get("image")
                if not blob:
                    raise ValueError("PDF 图片字节为空")
                features = extract_image_features(blob)
                images.append(
                    ImageIR(
                        id=f"img-{len(images)+1:05d}",
                        order=len(images),
                        filename=f"page-{page_idx+1}-xref-{xref}.{meta.get('ext','bin')}",
                        content_type=f"image/{meta.get('ext','unknown')}",
                        width_px=features.width_px,
                        height_px=features.height_px,
                        sha256=bytes_sha256(blob),
                        phash=features.phash,
                        mean_rgb=features.mean_rgb,
                        source_locator=SourceLocator(kind="pdf_image", page=page_idx + 1, index=img_idx),
                    )
                )
            except Exception as exc:
                warnings.append(f"PDF 图片提取失败 page={page_idx+1}, xref={xref}: {exc}")

    fm = FormatMeta(section_count=0)
    metadata = dict(pdf.metadata or {})
    page_count = pdf.page_count
    pdf.close()

    file_hash = file_sha256(path)

    return DocumentIR(
        schema_version=schema_version,
        document_id=f"doc-{file_hash[:24]}",
        filename=path.name,
        file_type="pdf",
        file_size_bytes=path.stat().st_size,
        sha256=file_hash,
        page_count=page_count,
        paragraphs=paragraphs,
        tables=[],
        images=images,
        format_meta=fm,
        warnings=warnings,
        metadata=metadata,
    )
