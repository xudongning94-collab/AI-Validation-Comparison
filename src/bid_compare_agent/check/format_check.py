from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, asdict, field
from typing import Any

from bid_compare_agent.models.document_ir import DocumentIR, ParagraphIR, SourceLocator
from bid_compare_agent.models.finding import Finding


@dataclass(frozen=True)
class FormatCheckConfig:
    dominant_ratio_warn: float = 0.70
    font_size_tolerance_pt: float = 0.5
    margin_tolerance_cm: float = 0.3
    check_page_margins: bool = True


@dataclass
class FormatCheckResult:
    schema_version: str
    document_id: str
    filename: str
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_id(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return f"fmt-{hashlib.sha256(raw).hexdigest()[:24]}"


def _paragraph_font_signature(paragraph: ParagraphIR) -> tuple[str | None, float | None]:
    fonts = [r.font_name for r in paragraph.runs if r.font_name]
    sizes = [r.font_size_pt for r in paragraph.runs if r.font_size_pt is not None]
    font = Counter(fonts).most_common(1)[0][0] if fonts else None
    size = Counter(round(float(x), 2) for x in sizes).most_common(1)[0][0] if sizes else None
    return font, size


def check_document_format(
    document: DocumentIR,
    config: FormatCheckConfig | None = None,
) -> FormatCheckResult:
    config = config or FormatCheckConfig()
    findings: list[Finding] = []

    body = [p for p in document.paragraphs if p.text.strip() and p.heading_level is None]
    signatures = [_paragraph_font_signature(p) for p in body]
    comparable = [(p, sig) for p, sig in zip(body, signatures) if sig != (None, None)]
    dominant = Counter(sig for _, sig in comparable).most_common(1)
    dominant_sig = dominant[0][0] if dominant else (None, None)
    dominant_count = dominant[0][1] if dominant else 0
    dominant_ratio = dominant_count / len(comparable) if comparable else 0.0

    if comparable and dominant_ratio < config.dominant_ratio_warn:
        first = comparable[0][0]
        findings.append(
            Finding(
                finding_id=_stable_id(document.sha256, "mixed-body-style"),
                type="format_issue",
                severity="medium",
                document_id=document.document_id,
                source_locator=first.source_locator or SourceLocator(kind="unknown"),
                score=round(1.0 - dominant_ratio, 6),
                summary=f"{document.filename} 正文存在较多字体/字号混用，主样式占比 {dominant_ratio:.1%}",
                evidence={
                    "dominant_font": dominant_sig[0],
                    "dominant_size_pt": dominant_sig[1],
                    "dominant_ratio": round(dominant_ratio, 6),
                    "style_distribution": [
                        {"font": sig[0], "size_pt": sig[1], "count": count}
                        for sig, count in Counter(sig for _, sig in comparable).most_common(10)
                    ],
                },
                metadata={"rule": "body-style-dominance"},
            )
        )

    dominant_font, dominant_size = dominant_sig
    if dominant_font is not None or dominant_size is not None:
        for paragraph, (font, size) in comparable:
            mismatch = False
            if dominant_font and font and font != dominant_font:
                mismatch = True
            if dominant_size is not None and size is not None and abs(size - dominant_size) > config.font_size_tolerance_pt:
                mismatch = True
            if not mismatch:
                continue
            findings.append(
                Finding(
                    finding_id=_stable_id(document.sha256, paragraph.id, "body-style-outlier"),
                    type="format_issue",
                    severity="low",
                    document_id=document.document_id,
                    source_locator=paragraph.source_locator or SourceLocator(kind="unknown"),
                    score=None,
                    summary=f"{document.filename} 存在正文格式离群段落",
                    evidence={
                        "paragraph_id": paragraph.id,
                        "text": paragraph.text,
                        "font": font,
                        "size_pt": size,
                        "expected_font": dominant_font,
                        "expected_size_pt": dominant_size,
                    },
                    metadata={"rule": "body-style-outlier"},
                )
            )

    fm = document.format_meta
    margin_values = {
        "top": fm.margin_top_cm,
        "bottom": fm.margin_bottom_cm,
        "left": fm.margin_left_cm,
        "right": fm.margin_right_cm,
    }
    if config.check_page_margins and all(v is not None for v in margin_values.values()):
        left = float(margin_values["left"])
        right = float(margin_values["right"])
        if abs(left - right) > config.margin_tolerance_cm:
            locator = body[0].source_locator if body and body[0].source_locator else SourceLocator(kind="document")
            findings.append(
                Finding(
                    finding_id=_stable_id(document.sha256, "asymmetric-margins"),
                    type="format_issue",
                    severity="low",
                    document_id=document.document_id,
                    source_locator=locator,
                    summary=f"{document.filename} 左右页边距差异较大",
                    evidence={"margins_cm": margin_values},
                    metadata={"rule": "page-margin-symmetry"},
                )
            )

    return FormatCheckResult(
        schema_version="1.0.0",
        document_id=document.document_id,
        filename=document.filename,
        findings=findings,
        summary={
            "eligible_body_paragraphs": len(body),
            "comparable_body_paragraphs": len(comparable),
            "dominant_font": dominant_font,
            "dominant_size_pt": dominant_size,
            "dominant_ratio": round(dominant_ratio, 6),
            "issue_count": len(findings),
        },
    )
