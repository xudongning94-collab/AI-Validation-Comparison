from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .finding import Finding


@dataclass
class DocumentImageStats:
    document_id: str
    filename: str
    eligible_images: int
    repeated_images: int
    repeated_rate: float


@dataclass
class ImagePairSummary:
    document_a_id: str
    document_b_id: str
    document_a_filename: str
    document_b_filename: str
    exact_pairs: int
    high_similar_pairs: int
    max_similarity: float
    document_a: DocumentImageStats
    document_b: DocumentImageStats


@dataclass
class ImageComparisonResult:
    schema_version: str
    compare_type: str
    documents: list[dict[str, str]] = field(default_factory=list)
    pair_summaries: list[ImagePairSummary] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
