from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .document_ir import SourceLocator
from .finding import Finding


@dataclass
class ParagraphAILikelihood:
    document_id: str
    paragraph_id: str
    score: float
    confidence: float
    severity: str
    text_chars: int
    source_locator: SourceLocator
    signals: dict[str, float] = field(default_factory=dict)


@dataclass
class DocumentAILikelihoodStats:
    document_id: str
    filename: str
    eligible_paragraphs: int
    suspicious_paragraphs: int
    high_paragraphs: int
    analyzed_chars: int
    ai_likelihood: float
    confidence: float


@dataclass
class AILikelihoodResult:
    schema_version: str
    analysis_type: str
    method: str
    documents: list[DocumentAILikelihoodStats] = field(default_factory=list)
    paragraph_scores: list[ParagraphAILikelihood] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
