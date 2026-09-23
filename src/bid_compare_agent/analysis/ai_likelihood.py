from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from statistics import mean, pstdev

from bid_compare_agent.models.ai_likelihood import (
    AILikelihoodResult,
    DocumentAILikelihoodStats,
    ParagraphAILikelihood,
)
from bid_compare_agent.models.document_ir import DocumentIR, ParagraphIR, SourceLocator
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.preprocess.interference import classify_interference


METHOD = "stylometry-heuristic-alpha-v1"
LIMITATIONS = (
    "结果仅表示文本风格与规则库的相似程度，不能证明文本由 AI 生成。",
    "短文本、模板化招标语言、人工润色和翻译文本都可能造成误判。",
    "正式结论必须结合来源记录、版本历史和人工复核。",
)

_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_NORMALIZE_RE = re.compile(r"\s+")
_TRANSITIONS = (
    "首先",
    "其次",
    "再次",
    "此外",
    "同时",
    "最后",
    "综上",
    "一方面",
    "另一方面",
    "总而言之",
    "值得注意的是",
)
_GENERIC_PHRASES = (
    "全面提升",
    "有效提升",
    "全面保障",
    "持续优化",
    "显著提高",
    "确保项目",
    "通过统一",
    "实现协同",
    "形成闭环",
    "赋能业务",
    "提高效率",
    "降低风险",
)


@dataclass(frozen=True)
class AILikelihoodConfig:
    min_chars: int = 80
    medium_threshold: float = 0.55
    high_threshold: float = 0.75
    min_confidence: float = 0.35
    interference_downweight_factor: float = 0.70
    sentence_uniformity_weight: float = 0.30
    transition_density_weight: float = 0.25
    generic_phrase_weight: float = 0.20
    repeated_phrase_weight: float = 0.15
    punctuation_uniformity_weight: float = 0.10

    def __post_init__(self) -> None:
        if self.min_chars < 20:
            raise ValueError("min_chars 不能小于 20")
        if not 0 <= self.medium_threshold < self.high_threshold <= 1:
            raise ValueError("AI 疑似度阈值必须满足 0 <= medium < high <= 1")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence 必须位于 [0, 1]")
        if not 0 < self.interference_downweight_factor <= 1:
            raise ValueError("interference_downweight_factor 必须位于 (0, 1]")
        if self.total_weight <= 0:
            raise ValueError("特征权重之和必须大于 0")

    @property
    def total_weight(self) -> float:
        return sum(
            (
                self.sentence_uniformity_weight,
                self.transition_density_weight,
                self.generic_phrase_weight,
                self.repeated_phrase_weight,
                self.punctuation_uniformity_weight,
            )
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _coefficient_uniformity(values: list[int], scale: float) -> float:
    if len(values) < 3 or mean(values) <= 0:
        return 0.0
    coefficient = pstdev(values) / mean(values)
    return _clamp(1.0 - coefficient / scale)


def _repeated_phrase_score(text: str, n: int = 4) -> float:
    compact = re.sub(r"[^\w\u4e00-\u9fff]", "", text.lower())
    if len(compact) < n * 3:
        return 0.0
    grams = [compact[index : index + n] for index in range(len(compact) - n + 1)]
    counts = Counter(grams)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return _clamp((repeated / len(grams)) / 0.12)


def _feature_scores(text: str) -> tuple[dict[str, float], int]:
    normalized = _NORMALIZE_RE.sub(" ", text.strip())
    sentences = [part.strip() for part in _SENTENCE_SPLIT_RE.split(normalized) if part.strip()]
    sentence_lengths = [len(part) for part in sentences]
    comma_counts = [part.count("，") + part.count(",") for part in sentences]
    transition_hits = sum(normalized.count(phrase) for phrase in _TRANSITIONS)
    generic_hits = sum(normalized.count(phrase) for phrase in _GENERIC_PHRASES)
    generic_units = max(1.0, len(normalized) / 100.0)

    signals = {
        "sentence_uniformity": _coefficient_uniformity(sentence_lengths, 0.75),
        "transition_density": _clamp(transition_hits / max(1.0, len(sentences) * 0.75)),
        "generic_phrase_density": _clamp(generic_hits / (generic_units * 2.0)),
        "repeated_phrase_ratio": _repeated_phrase_score(normalized),
        "punctuation_uniformity": (
            _coefficient_uniformity(comma_counts, 1.0) if any(comma_counts) else 0.0
        ),
    }
    return signals, len(sentences)


def _weighted_score(signals: dict[str, float], config: AILikelihoodConfig) -> float:
    weighted = (
        signals["sentence_uniformity"] * config.sentence_uniformity_weight
        + signals["transition_density"] * config.transition_density_weight
        + signals["generic_phrase_density"] * config.generic_phrase_weight
        + signals["repeated_phrase_ratio"] * config.repeated_phrase_weight
        + signals["punctuation_uniformity"] * config.punctuation_uniformity_weight
    )
    return _clamp(weighted / config.total_weight)


def _confidence(text_chars: int, sentence_count: int) -> float:
    return _clamp(
        min(1.0, text_chars / 400.0) * 0.60
        + min(1.0, sentence_count / 6.0) * 0.40
    )


def _severity(score: float, config: AILikelihoodConfig) -> str:
    if score >= config.high_threshold:
        return "high"
    if score >= config.medium_threshold:
        return "medium"
    return "info"


def _stable_finding_id(document: DocumentIR, paragraph: ParagraphIR) -> str:
    raw = f"{document.sha256}|{paragraph.id}|{METHOD}".encode("utf-8")
    return f"ai-{hashlib.sha256(raw).hexdigest()[:24]}"


def analyze_document_ai_likelihood(
    document: DocumentIR,
    config: AILikelihoodConfig | None = None,
) -> tuple[DocumentAILikelihoodStats, list[ParagraphAILikelihood], list[Finding], dict[str, int]]:
    config = config or AILikelihoodConfig()
    interference = {item.paragraph_id: item for item in classify_interference(document).items}
    paragraph_scores: list[ParagraphAILikelihood] = []
    findings: list[Finding] = []
    excluded = 0
    downweighted = 0

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        interference_item = interference.get(paragraph.id)
        if interference_item and interference_item.action == "exclude":
            excluded += 1
            continue
        if len(text) < config.min_chars:
            excluded += 1
            continue

        signals, sentence_count = _feature_scores(text)
        score = _weighted_score(signals, config)
        confidence = _confidence(len(text), sentence_count)
        if interference_item and interference_item.action == "downweight":
            score *= config.interference_downweight_factor
            confidence *= config.interference_downweight_factor
            downweighted += 1

        score = round(_clamp(score), 6)
        confidence = round(_clamp(confidence), 6)
        severity = _severity(score, config)
        locator = paragraph.source_locator or SourceLocator(kind="unknown")
        paragraph_score = ParagraphAILikelihood(
            document_id=document.document_id,
            paragraph_id=paragraph.id,
            score=score,
            confidence=confidence,
            severity=severity,
            text_chars=len(text),
            source_locator=locator,
            signals={key: round(value, 6) for key, value in signals.items()},
        )
        paragraph_scores.append(paragraph_score)

        if severity not in {"medium", "high"} or confidence < config.min_confidence:
            continue
        findings.append(
            Finding(
                finding_id=_stable_finding_id(document, paragraph),
                type="ai_likelihood",
                severity=severity,
                document_id=document.document_id,
                source_locator=locator,
                score=score,
                summary=(
                    f"{document.filename} 存在风格高度规则化的段落，"
                    f"AI 疑似辅助分 {score:.1%}，置信度 {confidence:.1%}"
                ),
                evidence={
                    "paragraph_id": paragraph.id,
                    "text": paragraph.text,
                    "signals": paragraph_score.signals,
                    "confidence": confidence,
                },
                metadata={
                    "method": METHOD,
                    "non_diagnostic": True,
                    "requires_human_review": True,
                },
            )
        )

    if paragraph_scores:
        weights = [max(1.0, item.text_chars * item.confidence) for item in paragraph_scores]
        weighted_score = sum(item.score * weight for item, weight in zip(paragraph_scores, weights)) / sum(weights)
        weighted_confidence = sum(
            item.confidence * item.text_chars for item in paragraph_scores
        ) / sum(item.text_chars for item in paragraph_scores)
    else:
        weighted_score = 0.0
        weighted_confidence = 0.0

    stats = DocumentAILikelihoodStats(
        document_id=document.document_id,
        filename=document.filename,
        eligible_paragraphs=len(paragraph_scores),
        suspicious_paragraphs=sum(1 for item in paragraph_scores if item.severity in {"medium", "high"}),
        high_paragraphs=sum(1 for item in paragraph_scores if item.severity == "high"),
        analyzed_chars=sum(item.text_chars for item in paragraph_scores),
        ai_likelihood=round(weighted_score, 6),
        confidence=round(weighted_confidence, 6),
    )
    return stats, paragraph_scores, findings, {"excluded": excluded, "downweighted": downweighted}


def analyze_ai_likelihood(
    documents: list[DocumentIR],
    config: AILikelihoodConfig | None = None,
) -> AILikelihoodResult:
    if not documents:
        raise ValueError("AI 疑似度分析至少需要 1 份文档")
    config = config or AILikelihoodConfig()
    document_stats: list[DocumentAILikelihoodStats] = []
    paragraph_scores: list[ParagraphAILikelihood] = []
    findings: list[Finding] = []
    excluded = 0
    downweighted = 0

    for document in documents:
        stats, scores, document_findings, counters = analyze_document_ai_likelihood(document, config)
        document_stats.append(stats)
        paragraph_scores.extend(scores)
        findings.extend(document_findings)
        excluded += counters["excluded"]
        downweighted += counters["downweighted"]

    findings.sort(key=lambda finding: (finding.score or 0.0, finding.finding_id), reverse=True)
    return AILikelihoodResult(
        schema_version="1.0.0",
        analysis_type="ai_likelihood",
        method=METHOD,
        documents=document_stats,
        paragraph_scores=paragraph_scores,
        findings=findings,
        metadata={
            "limitations": list(LIMITATIONS),
            "non_diagnostic": True,
            "excluded_paragraphs": excluded,
            "downweighted_paragraphs": downweighted,
            "thresholds": {
                "medium": config.medium_threshold,
                "high": config.high_threshold,
                "min_confidence": config.min_confidence,
            },
        },
    )
