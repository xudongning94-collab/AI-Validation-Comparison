from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .finding import Finding


@dataclass
class DocumentTextStats:
    document_id: str
    filename: str
    eligible_paragraphs: int
    total_chars: int
    repeated_paragraphs_high: int = 0
    repeated_chars_high: int = 0
    repeated_rate_high: float = 0.0


@dataclass
class TextPairSummary:
    document_a_id: str
    document_b_id: str
    document_a_filename: str
    document_b_filename: str
    high_pairs: int
    medium_pairs: int
    max_similarity: float
    document_a: DocumentTextStats
    document_b: DocumentTextStats
    top_sections: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TextComparisonResult:
    schema_version: str
    compare_type: str
    documents: list[dict[str, str]]
    pair_summaries: list[TextPairSummary] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
