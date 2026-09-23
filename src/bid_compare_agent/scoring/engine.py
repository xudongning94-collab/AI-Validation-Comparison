from __future__ import annotations

import hashlib
from dataclasses import dataclass

from bid_compare_agent.check.format_check import FormatCheckResult
from bid_compare_agent.models.ai_likelihood import AILikelihoodResult
from bid_compare_agent.models.document_ir import DocumentIR
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.models.image_compare import ImageComparisonResult
from bid_compare_agent.models.scoring import (
    DimensionContribution,
    DocumentRiskScore,
    UnifiedScoringResult,
)
from bid_compare_agent.models.text_compare import TextComparisonResult


DIMENSION_NAMES = ("text_similarity", "image_similarity", "ai_likelihood", "format_similarity")
_SEVERITY_RISK = {"info": 0.0, "low": 0.25, "medium": 0.55, "high": 0.80, "critical": 1.0}


@dataclass(frozen=True)
class UnifiedScoreConfig:
    text_similarity_weight: float = 0.40
    image_similarity_weight: float = 0.20
    ai_likelihood_weight: float = 0.15
    format_similarity_weight: float = 0.25
    low_threshold: float = 0.20
    medium_threshold: float = 0.40
    high_threshold: float = 0.65
    critical_threshold: float = 0.85

    def __post_init__(self) -> None:
        weights = self.weights
        if any(value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
            raise ValueError("评分权重必须非负且总和大于 0")
        thresholds = (
            self.low_threshold,
            self.medium_threshold,
            self.high_threshold,
            self.critical_threshold,
        )
        if not (0 <= thresholds[0] < thresholds[1] < thresholds[2] < thresholds[3] <= 1):
            raise ValueError("风险阈值必须满足 0 <= low < medium < high < critical <= 1")

    @property
    def weights(self) -> dict[str, float]:
        return {
            "text_similarity": self.text_similarity_weight,
            "image_similarity": self.image_similarity_weight,
            "ai_likelihood": self.ai_likelihood_weight,
            "format_similarity": self.format_similarity_weight,
        }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def classify_risk(score: float, config: UnifiedScoreConfig | None = None) -> str:
    config = config or UnifiedScoreConfig()
    if score >= config.critical_threshold:
        return "critical"
    if score >= config.high_threshold:
        return "high"
    if score >= config.medium_threshold:
        return "medium"
    if score >= config.low_threshold:
        return "low"
    return "minimal"


def _text_dimension(
    document_id: str,
    result: TextComparisonResult | None,
) -> tuple[bool, float, dict[str, object]]:
    if result is None:
        return False, 0.0, {"reason": "result_missing"}
    rates: list[float] = []
    eligible: list[int] = []
    pair_count = 0
    for summary in result.pair_summaries:
        stats = None
        if summary.document_a_id == document_id:
            stats = summary.document_a
        elif summary.document_b_id == document_id:
            stats = summary.document_b
        if stats is None:
            continue
        pair_count += 1
        rates.append(stats.repeated_rate_high)
        eligible.append(stats.eligible_paragraphs)
    applicable = bool(eligible) and max(eligible) > 0
    return applicable, _clamp(max(rates, default=0.0)), {
        "pair_count": pair_count,
        "max_high_repeated_rate": round(max(rates, default=0.0), 6),
        "max_eligible_paragraphs": max(eligible, default=0),
    }


def _image_dimension(
    document_id: str,
    result: ImageComparisonResult | None,
) -> tuple[bool, float, dict[str, object]]:
    if result is None:
        return False, 0.0, {"reason": "result_missing"}
    rates: list[float] = []
    eligible: list[int] = []
    pair_count = 0
    for summary in result.pair_summaries:
        stats = None
        if summary.document_a_id == document_id:
            stats = summary.document_a
        elif summary.document_b_id == document_id:
            stats = summary.document_b
        if stats is None:
            continue
        pair_count += 1
        rates.append(stats.repeated_rate)
        eligible.append(stats.eligible_images)
    applicable = bool(eligible) and max(eligible) > 0
    return applicable, _clamp(max(rates, default=0.0)), {
        "pair_count": pair_count,
        "max_repeated_image_rate": round(max(rates, default=0.0), 6),
        "max_eligible_images": max(eligible, default=0),
    }


def _ai_dimension(
    document_id: str,
    result: AILikelihoodResult | None,
) -> tuple[bool, float, dict[str, object]]:
    if result is None:
        return False, 0.0, {"reason": "result_missing"}
    stats = next((item for item in result.documents if item.document_id == document_id), None)
    if stats is None:
        return False, 0.0, {"reason": "document_missing"}
    applicable = stats.eligible_paragraphs > 0
    return applicable, _clamp(stats.ai_likelihood), {
        "eligible_paragraphs": stats.eligible_paragraphs,
        "suspicious_paragraphs": stats.suspicious_paragraphs,
        "confidence": stats.confidence,
        "non_diagnostic": True,
    }


def _format_dimension(
    document_id: str,
    results: list[FormatCheckResult] | None,
) -> tuple[bool, float, dict[str, object]]:
    if not results:
        return False, 0.0, {"reason": "result_missing"}
    result = next((item for item in results if item.document_id == document_id), None)
    if result is None:
        return False, 0.0, {"reason": "document_missing"}

    comparable = int(result.summary.get("comparable_body_paragraphs", 0))
    outlier_count = sum(
        1 for finding in result.findings if finding.metadata.get("rule") == "body-style-outlier"
    )
    outlier_ratio = outlier_count / comparable if comparable else 0.0
    finding_risks = [
        max(finding.score or 0.0, _SEVERITY_RISK.get(finding.severity, 0.0))
        for finding in result.findings
    ]
    raw_score = _clamp(max([outlier_ratio, *finding_risks], default=0.0))
    applicable = comparable > 0 or bool(result.findings)
    return applicable, raw_score, {
        "comparable_body_paragraphs": comparable,
        "issue_count": len(result.findings),
        "style_outlier_ratio": round(outlier_ratio, 6),
    }


def _related_finding_ids(document_id: str, findings: list[Finding]) -> list[str]:
    related = {
        finding.finding_id
        for finding in findings
        if finding.document_id == document_id or finding.peer_document_id == document_id
    }
    return sorted(related)


def _score_id(documents: list[DocumentIR]) -> str:
    raw = "|".join(sorted(document.sha256 for document in documents)).encode("utf-8")
    return f"score-{hashlib.sha256(raw).hexdigest()[:24]}"


def score_document_set(
    documents: list[DocumentIR],
    *,
    text_result: TextComparisonResult | None = None,
    image_result: ImageComparisonResult | None = None,
    format_results: list[FormatCheckResult] | None = None,
    ai_result: AILikelihoodResult | None = None,
    config: UnifiedScoreConfig | None = None,
) -> UnifiedScoringResult:
    if not documents:
        raise ValueError("统一评分至少需要 1 份文档")
    config = config or UnifiedScoreConfig()
    weights = config.weights
    all_findings: list[Finding] = []
    if text_result:
        all_findings.extend(text_result.findings)
    if image_result:
        all_findings.extend(image_result.findings)
    if ai_result:
        all_findings.extend(ai_result.findings)
    for result in format_results or []:
        all_findings.extend(result.findings)

    document_scores: list[DocumentRiskScore] = []
    for document in documents:
        raw_dimensions = {
            "text_similarity": _text_dimension(document.document_id, text_result),
            "image_similarity": _image_dimension(document.document_id, image_result),
            "ai_likelihood": _ai_dimension(document.document_id, ai_result),
            "format_similarity": _format_dimension(document.document_id, format_results),
        }
        applicable_weight = sum(
            weights[name] for name, (applicable, _, _) in raw_dimensions.items() if applicable
        )
        dimensions: list[DimensionContribution] = []
        for name in DIMENSION_NAMES:
            applicable, raw_score, evidence = raw_dimensions[name]
            effective_weight = weights[name] / applicable_weight if applicable and applicable_weight else 0.0
            contribution = raw_score * effective_weight
            dimensions.append(
                DimensionContribution(
                    name=name,
                    applicable=applicable,
                    raw_score=round(raw_score, 6),
                    configured_weight=round(weights[name], 6),
                    effective_weight=round(effective_weight, 6),
                    contribution=round(contribution, 6),
                    evidence=evidence,
                )
            )

        score = _clamp(sum(item.contribution for item in dimensions))
        document_scores.append(
            DocumentRiskScore(
                document_id=document.document_id,
                filename=document.filename,
                score=round(score, 6),
                score_100=round(score * 100, 2),
                risk_level=classify_risk(score, config),
                dimensions=dimensions,
                finding_ids=_related_finding_ids(document.document_id, all_findings),
            )
        )

    aggregate_score = max((item.score for item in document_scores), default=0.0)
    average_score = sum(item.score for item in document_scores) / len(document_scores)
    return UnifiedScoringResult(
        schema_version="1.0.0",
        score_type="unified_risk",
        score_id=_score_id(documents),
        documents=document_scores,
        aggregate_score=round(aggregate_score, 6),
        aggregate_score_100=round(aggregate_score * 100, 2),
        aggregate_risk_level=classify_risk(aggregate_score, config),
        metadata={
            "aggregate_strategy": "max_document_risk",
            "average_document_score": round(average_score, 6),
            "missing_dimension_policy": "renormalize_applicable_weights",
            "weights": weights,
            "risk_thresholds": {
                "low": config.low_threshold,
                "medium": config.medium_threshold,
                "high": config.high_threshold,
                "critical": config.critical_threshold,
            },
            "ai_likelihood_non_diagnostic": True,
        },
    )
