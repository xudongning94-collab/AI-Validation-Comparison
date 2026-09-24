from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from typing import Iterable

from bid_compare_agent.models.finding import Finding
from bid_compare_agent.models.scoring import UnifiedScoringResult


METHOD = "deterministic-report-v1"
SEVERITY_ORDER = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
RISK_LABELS = {
    "minimal": "最低",
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "严重",
}
DIMENSION_LABELS = {
    "text_similarity": "文本相似度",
    "image_similarity": "图片相似度",
    "ai_likelihood": "AI 风格辅助信号",
    "format_similarity": "格式异常",
}
ACTION_TEXT = {
    "text_similarity": "核对高相似文本是否来自招标文件、统一模板或其他允许复用来源。",
    "image_similarity": "核对重复或近似图片的来源、版本、授权范围及是否存在局部修改。",
    "format_issue": "打开定位结果复核格式异常，并按招标文件格式要求修订。",
    "ai_likelihood": "结合版本历史和来源记录人工复核风格异常，不得据此直接判定 AI 生成。",
    "interference": "确认模板、页眉页脚等干扰内容是否应排除或降权。",
    "signature_compliance": "复核签字、签章、主体名称、日期和位置要求。",
}
LIMITATIONS = [
    "风险分数用于筛查优先级，不构成抄袭、串标、违规或投标有效性的确定结论。",
    "AI 疑似度是非诊断性风格辅助信号，不能证明文本由 AI 生成。",
    "图片哈希只能识别相同或近似视觉内容，不能替代 OCR、签章识别和人工验真。",
    "所有高风险结果均需结合招标要求、原始文件、版本记录和人工复核。",
]


def _stable_report_id(scoring: UnifiedScoringResult, findings: list[Finding]) -> str:
    raw = json.dumps(
        {
            "method": METHOD,
            "score_id": scoring.score_id,
            "finding_ids": sorted(finding.finding_id for finding in findings),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"report-{hashlib.sha256(raw).hexdigest()[:24]}"


def _sorted_findings(findings: Iterable[Finding]) -> list[Finding]:
    unique: dict[str, Finding] = {}
    for finding in findings:
        unique.setdefault(finding.finding_id, finding)
    return sorted(
        unique.values(),
        key=lambda item: (
            -SEVERITY_ORDER.get(item.severity, 0),
            -float(item.score or 0.0),
            item.finding_id,
        ),
    )


def _report_finding(finding: Finding) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "type": finding.type,
        "severity": finding.severity,
        "document_id": finding.document_id,
        "peer_document_id": finding.peer_document_id,
        "summary": finding.summary,
        "source_locator": asdict(finding.source_locator),
        "peer_source_locator": (
            asdict(finding.peer_source_locator)
            if finding.peer_source_locator is not None
            else None
        ),
    }


def _dimension_summary(scoring: UnifiedScoringResult) -> list[dict[str, object]]:
    if not scoring.documents:
        return []
    # 聚合分采用最高文档风险，因此报告维度也取最高风险文档，避免再次计算分数。
    representative = max(scoring.documents, key=lambda item: (item.score, item.document_id))
    return [
        {
            "name": item.name,
            "applicable": item.applicable,
            "contribution": item.contribution,
        }
        for item in representative.dimensions
    ]


def _summary(scoring: UnifiedScoringResult, dimensions: list[dict[str, object]], findings: list[Finding]) -> str:
    applicable = [item for item in dimensions if item["applicable"]]
    ranked = sorted(applicable, key=lambda item: float(item["contribution"]), reverse=True)
    dimension_text = "、".join(
        DIMENSION_LABELS.get(str(item["name"]), str(item["name"])) for item in ranked[:2]
    ) or "暂无适用风险维度"
    urgent_count = sum(1 for item in findings if item.severity in {"critical", "high"})
    return (
        f"本次分析 {len(scoring.documents)} 份文件，总体风险等级为"
        f"{RISK_LABELS.get(scoring.aggregate_risk_level, scoring.aggregate_risk_level)}"
        f"（{scoring.aggregate_score_100:.2f}/100）。"
        f"主要风险维度为{dimension_text}。"
        f"共有 {urgent_count} 项高等级问题需要优先人工复核。"
    )


def _recommended_actions(findings: list[Finding]) -> list[dict[str, object]]:
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.type].append(finding)

    actions: list[dict[str, object]] = []
    for finding_type, items in sorted(
        grouped.items(),
        key=lambda pair: -max(SEVERITY_ORDER.get(item.severity, 0) for item in pair[1]),
    ):
        max_level = max(SEVERITY_ORDER.get(item.severity, 0) for item in items)
        priority = "immediate" if max_level >= 5 else "high" if max_level >= 4 else "normal"
        actions.append(
            {
                "priority": priority,
                "action": ACTION_TEXT.get(finding_type, "根据定位信息人工复核该类问题。"),
                "related_finding_ids": [item.finding_id for item in items[:5]],
            }
        )
        if len(actions) >= 10:
            break
    if not actions:
        actions.append(
            {
                "priority": "normal",
                "action": "保留本次分析记录，并对关键章节进行抽样人工复核。",
                "related_finding_ids": [],
            }
        )
    return actions


def generate_deterministic_report(
    scoring: UnifiedScoringResult,
    findings: Iterable[Finding],
) -> dict[str, object]:
    """从确定性分析结果生成可校验报告，不调用 LLM，也不复制原文证据。"""
    ordered = _sorted_findings(findings)
    dimensions = _dimension_summary(scoring)
    return {
        "report_id": _stable_report_id(scoring, ordered),
        "schema_version": "1.0.0",
        "language": "zh-CN",
        "summary": _summary(scoring, dimensions, ordered),
        "risk_level": scoring.aggregate_risk_level,
        "requires_human_review": True,
        "documents": [
            {
                "document_id": document.document_id,
                "filename": document.filename,
                "score_100": document.score_100,
                "risk_level": document.risk_level,
            }
            for document in scoring.documents
        ],
        "findings": [_report_finding(item) for item in ordered[:20]],
        "scores": {
            "aggregate_score_100": scoring.aggregate_score_100,
            "aggregate_risk_level": scoring.aggregate_risk_level,
            "dimensions": dimensions,
        },
        "recommended_actions": _recommended_actions(ordered),
        "limitations": list(LIMITATIONS),
    }
