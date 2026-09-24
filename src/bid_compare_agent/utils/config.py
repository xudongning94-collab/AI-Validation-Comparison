from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bid_compare_agent.analysis import AILikelihoodConfig
from bid_compare_agent.annotate import DocxAnnotationConfig
from bid_compare_agent.compare import ImageCompareConfig, TextCompareConfig
from bid_compare_agent.scoring import UnifiedScoreConfig


def load_yaml(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data or {}


def load_text_compare_config(path: str | Path) -> TextCompareConfig:
    data = load_yaml(path)
    text = data.get("text_similarity", {})
    return TextCompareConfig(
        medium_threshold=float(text.get("medium", 0.60)),
        high_threshold=float(text.get("high", 0.85)),
        min_chars=int(text.get("min_chars", 20)),
        max_chars=int(text.get("max_chars", 6000)),
        ngram_min=int(text.get("ngram_min", 2)),
        ngram_max=int(text.get("ngram_max", 4)),
        recall_ngram=int(text.get("recall_ngram", 2)),
        max_candidates_per_paragraph=int(text.get("max_candidates_per_paragraph", 30)),
        min_shared_recall_tokens=int(text.get("min_shared_recall_tokens", 2)),
        top_matches_per_paragraph=int(text.get("top_matches_per_paragraph", 3)),
        apply_interference=bool(text.get("apply_interference", True)),
        interference_downweight_factor=float(text.get("interference_downweight_factor", 0.70)),
    )


def load_image_compare_config(path: str | Path) -> ImageCompareConfig:
    data = load_yaml(path)
    image = data.get("image_similarity", {})
    return ImageCompareConfig(
        phash_exact_max_distance=int(image.get("phash_exact_max_distance", 5)),
        phash_high_max_distance=int(image.get("phash_high_max_distance", 15)),
        color_similarity_min=float(image.get("color_similarity_min", 0.55)),
        aspect_ratio_delta_max=float(image.get("aspect_ratio_delta_max", 0.25)),
        min_side_px=int(image.get("min_side_px", 8)),
    )


def load_ai_likelihood_config(path: str | Path) -> AILikelihoodConfig:
    data = load_yaml(path)
    ai = data.get("ai_likelihood", {})
    weights = ai.get("weights", {})
    return AILikelihoodConfig(
        min_chars=int(ai.get("min_chars", 80)),
        medium_threshold=float(ai.get("medium", 0.55)),
        high_threshold=float(ai.get("high", 0.75)),
        min_confidence=float(ai.get("min_confidence", 0.35)),
        interference_downweight_factor=float(ai.get("interference_downweight_factor", 0.70)),
        sentence_uniformity_weight=float(weights.get("sentence_uniformity", 0.30)),
        transition_density_weight=float(weights.get("transition_density", 0.25)),
        generic_phrase_weight=float(weights.get("generic_phrase", 0.20)),
        repeated_phrase_weight=float(weights.get("repeated_phrase", 0.15)),
        punctuation_uniformity_weight=float(weights.get("punctuation_uniformity", 0.10)),
    )


def load_unified_scoring_config(path: str | Path) -> UnifiedScoreConfig:
    data = load_yaml(path)
    weights = data.get("weights", {})
    thresholds = data.get("risk_thresholds", {})
    return UnifiedScoreConfig(
        text_similarity_weight=float(weights.get("text_similarity", 0.40)),
        image_similarity_weight=float(weights.get("image_similarity", 0.20)),
        ai_likelihood_weight=float(weights.get("ai_likelihood", 0.15)),
        format_similarity_weight=float(weights.get("format_similarity", 0.25)),
        low_threshold=float(thresholds.get("low", 0.20)),
        medium_threshold=float(thresholds.get("medium", 0.40)),
        high_threshold=float(thresholds.get("high", 0.65)),
        critical_threshold=float(thresholds.get("critical", 0.85)),
    )


def load_docx_annotation_config(path: str | Path) -> DocxAnnotationConfig:
    data = load_yaml(path)
    comments = data.get("docx_comments", {})
    return DocxAnnotationConfig(
        author=str(comments.get("author", "Bid Compare Agent")),
        initials=str(comments.get("initials", "BCA")),
        min_severity=str(comments.get("min_severity", "low")),
        max_comments=int(comments.get("max_comments", 500)),
        include_evidence=bool(comments.get("include_evidence", True)),
        max_evidence_chars=int(comments.get("max_evidence_chars", 500)),
    )
