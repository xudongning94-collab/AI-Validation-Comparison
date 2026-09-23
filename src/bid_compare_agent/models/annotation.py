from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .document_ir import SourceLocator


@dataclass
class AnnotationRecord:
    finding_id: str
    finding_type: str
    severity: str
    target_role: str
    source_locator: SourceLocator
    comment_id: int
    comment_text: str


@dataclass
class AnnotationSkip:
    finding_id: str
    finding_type: str
    reason: str
    target_role: str | None = None
    source_locator: SourceLocator | None = None


@dataclass
class DocxAnnotationResult:
    schema_version: str
    annotation_type: str
    source_document_id: str
    source_filename: str
    output_filename: str
    annotations: list[AnnotationRecord] = field(default_factory=list)
    skipped: list[AnnotationSkip] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
