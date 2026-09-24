from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from bid_compare_agent.models.finding import Finding


ALLOWED_CANDIDATE_KINDS = {"signature", "seal"}
ALLOWED_QUALITY_FLAGS = {"clipped", "low_opacity", "blurred", "unreadable", "occluded"}


@dataclass(frozen=True)
class SignatureRequirement:
    rule_id: str
    title: str
    expected_company_names: tuple[str, ...] = ()
    expected_signer_names: tuple[str, ...] = ()
    signer_role: str | None = None
    require_signature: bool = True
    require_seal: bool = True
    require_date: bool = True
    allowed_pages: tuple[int, ...] = ()
    anchor_terms: tuple[str, ...] = ()
    date_not_before: date | None = None
    date_not_after: date | None = None
    minimum_candidate_confidence: float = 0.65
    minimum_text_confidence: float = 0.82

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("rule_id 不能为空")
        if not self.title.strip():
            raise ValueError("title 不能为空")
        if any(page < 1 for page in self.allowed_pages):
            raise ValueError("allowed_pages 必须是正整数")
        if not 0 <= self.minimum_candidate_confidence <= 1:
            raise ValueError("minimum_candidate_confidence 必须在 0 到 1 之间")
        if not 0 <= self.minimum_text_confidence <= 1:
            raise ValueError("minimum_text_confidence 必须在 0 到 1 之间")
        if (
            self.date_not_before is not None
            and self.date_not_after is not None
            and self.date_not_before > self.date_not_after
        ):
            raise ValueError("date_not_before 不能晚于 date_not_after")


@dataclass(frozen=True)
class VisualCandidate:
    candidate_id: str
    kind: str
    page_number: int
    bbox: dict[str, float]
    confidence: float
    recognized_text: str | None = None
    quality_flags: tuple[str, ...] = ()
    detector: str = "unknown"

    def __post_init__(self) -> None:
        if self.kind not in ALLOWED_CANDIDATE_KINDS:
            raise ValueError(f"不支持的候选类型: {self.kind}")
        if self.page_number < 1:
            raise ValueError("候选页码必须是正整数")
        if not 0 <= self.confidence <= 1:
            raise ValueError("候选置信度必须在 0 到 1 之间")
        if set(self.quality_flags) - ALLOWED_QUALITY_FLAGS:
            raise ValueError("候选包含未知质量标志")
        if set(self.bbox) != {"x", "y", "w", "h"}:
            raise ValueError("候选 bbox 必须包含 x/y/w/h")
        if any(float(value) < 0 for value in self.bbox.values()):
            raise ValueError("候选 bbox 不能包含负数")
        if float(self.bbox["w"]) <= 0 or float(self.bbox["h"]) <= 0:
            raise ValueError("候选 bbox 宽高必须大于 0")


@dataclass(frozen=True)
class PageEvidence:
    page_number: int
    native_text: str = ""
    ocr_items: tuple[dict[str, Any], ...] = ()
    candidates: tuple[VisualCandidate, ...] = ()
    company_names: tuple[str, ...] = ()
    person_names: tuple[str, ...] = ()
    ocr_status: str = "not_run"
    vision_status: str = "not_run"
    date_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("证据页码必须是正整数")
        allowed_statuses = {"ok", "failed", "disabled", "not_run"}
        if self.ocr_status not in allowed_statuses or self.vision_status not in allowed_statuses:
            raise ValueError("证据状态必须是 ok/failed/disabled/not_run")
        if any(candidate.page_number != self.page_number for candidate in self.candidates):
            raise ValueError("候选页码必须与 PageEvidence 页码一致")


@dataclass
class SignatureRuleEvaluation:
    rule_id: str
    title: str
    status: str
    relevant_pages: list[int]
    matched_company_name: str | None = None
    matched_signer_name: str | None = None
    matched_date: str | None = None
    signature_candidate_ids: list[str] = field(default_factory=list)
    seal_candidate_ids: list[str] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)


@dataclass
class SignatureComplianceResult:
    schema_version: str
    check_type: str
    document_id: str
    rules: list[SignatureRuleEvaluation]
    findings: list[Finding]
    summary: dict[str, int]
    limitations: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
