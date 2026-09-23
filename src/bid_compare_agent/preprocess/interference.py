from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from bid_compare_agent.models.document_ir import DocumentIR, ParagraphIR, SourceLocator
from bid_compare_agent.models.finding import Finding


@dataclass(frozen=True)
class InterferenceConfig:
    exclude_headings: bool = True
    min_chars: int = 8
    response_patterns: tuple[str, ...] = (
        r"招标文件第\s*[一二三四五六七八九十百千万0-9]+\s*条",
        r"我方承诺",
        r"我方完全响应",
        r"完全满足招标要求",
        r"法定代表人身份证明",
        r"授权委托书",
        r"投标函",
        r"资格声明",
    )


@dataclass
class InterferenceItem:
    paragraph_id: str
    category: str
    action: str
    reason: str
    source_locator: SourceLocator


@dataclass
class InterferenceResult:
    schema_version: str
    document_id: str
    items: list[InterferenceItem] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_id(document: DocumentIR, paragraph: ParagraphIR, category: str) -> str:
    raw = f"{document.sha256}|{paragraph.id}|{category}".encode("utf-8")
    return f"int-{hashlib.sha256(raw).hexdigest()[:24]}"


def classify_interference(
    document: DocumentIR,
    config: InterferenceConfig | None = None,
) -> InterferenceResult:
    config = config or InterferenceConfig()
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in config.response_patterns]
    items: list[InterferenceItem] = []
    findings: list[Finding] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        locator = paragraph.source_locator or SourceLocator(kind="unknown")
        category: str | None = None
        action = "exclude"
        reason = ""

        if config.exclude_headings and paragraph.heading_level is not None:
            category = "heading"
            reason = "标题用于章节定位，不计入正文重复率"
        elif len(text) < config.min_chars:
            category = "short_noise"
            reason = "文本过短，作为低信息量噪声排除"
        elif any(pattern.search(text) for pattern in compiled):
            category = "standard_response"
            action = "downweight"
            reason = "命中招标响应/法定模板类规则，建议降权而非直接判定为方案重复"

        if category is None:
            continue

        item = InterferenceItem(
            paragraph_id=paragraph.id,
            category=category,
            action=action,
            reason=reason,
            source_locator=locator,
        )
        items.append(item)
        findings.append(
            Finding(
                finding_id=_stable_id(document, paragraph, category),
                type="interference",
                severity="info",
                document_id=document.document_id,
                source_locator=locator,
                summary=f"{document.filename} 段落被识别为干扰项：{category}",
                evidence={
                    "paragraph_id": paragraph.id,
                    "text": paragraph.text,
                    "category": category,
                    "action": action,
                    "reason": reason,
                },
                metadata={"rule_engine": "interference-alpha-v1"},
            )
        )

    return InterferenceResult(
        schema_version="1.0.0",
        document_id=document.document_id,
        items=items,
        findings=findings,
        summary={
            "paragraphs": len(document.paragraphs),
            "interference_items": len(items),
            "exclude_count": sum(1 for item in items if item.action == "exclude"),
            "downweight_count": sum(1 for item in items if item.action == "downweight"),
        },
    )
