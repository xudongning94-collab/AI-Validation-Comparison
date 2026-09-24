from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DimensionContribution:
    name: str
    applicable: bool
    raw_score: float
    configured_weight: float
    effective_weight: float
    contribution: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentRiskScore:
    document_id: str
    filename: str
    score: float
    score_100: float
    risk_level: str
    dimensions: list[DimensionContribution] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)


@dataclass
class UnifiedScoringResult:
    schema_version: str
    score_type: str
    score_id: str
    documents: list[DocumentRiskScore] = field(default_factory=list)
    aggregate_score: float = 0.0
    aggregate_score_100: float = 0.0
    aggregate_risk_level: str = "minimal"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
