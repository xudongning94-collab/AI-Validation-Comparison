from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from bid_compare_agent.models.document_ir import SourceLocator
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.models.scoring import (
    DimensionContribution,
    DocumentRiskScore,
    UnifiedScoringResult,
)
from bid_compare_agent.reporting import generate_deterministic_report


ROOT = Path(__file__).resolve().parents[2]


def _scoring() -> UnifiedScoringResult:
    dimensions = [
        DimensionContribution(
            name="text_similarity",
            applicable=True,
            raw_score=0.8,
            configured_weight=0.4,
            effective_weight=0.4,
            contribution=0.32,
        ),
        DimensionContribution(
            name="image_similarity",
            applicable=True,
            raw_score=0.5,
            configured_weight=0.2,
            effective_weight=0.2,
            contribution=0.1,
        ),
        DimensionContribution(
            name="ai_likelihood",
            applicable=True,
            raw_score=0.2,
            configured_weight=0.15,
            effective_weight=0.15,
            contribution=0.03,
        ),
        DimensionContribution(
            name="format_similarity",
            applicable=True,
            raw_score=0.4,
            configured_weight=0.25,
            effective_weight=0.25,
            contribution=0.1,
        ),
    ]
    document = DocumentRiskScore(
        document_id="doc-a",
        filename="a.docx",
        score=0.55,
        score_100=55.0,
        risk_level="medium",
        dimensions=dimensions,
        finding_ids=["finding-a"],
    )
    return UnifiedScoringResult(
        schema_version="1.0.0",
        score_type="unified_risk",
        score_id="score-a",
        documents=[document],
        aggregate_score=0.55,
        aggregate_score_100=55.0,
        aggregate_risk_level="medium",
    )


def test_deterministic_report_matches_schema_and_is_stable() -> None:
    finding = Finding(
        finding_id="finding-a",
        type="text_similarity",
        severity="high",
        document_id="doc-a",
        peer_document_id="doc-b",
        source_locator=SourceLocator(kind="docx_paragraph", paragraph_index=3),
        peer_source_locator=SourceLocator(kind="docx_paragraph", paragraph_index=5),
        summary="两份文件存在高相似段落，需核对共同来源。",
        score=0.92,
        evidence={"text": "不应进入确定性报告的完整原文"},
    )

    first = generate_deterministic_report(_scoring(), [finding])
    second = generate_deterministic_report(_scoring(), [finding])
    schema = json.loads((ROOT / "schemas" / "report.schema.json").read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(first)
    assert first == second
    assert first["report_id"].startswith("report-")
    assert first["requires_human_review"] is True
    assert "完整原文" not in json.dumps(first, ensure_ascii=False)
    assert first["findings"][0]["finding_id"] == "finding-a"
