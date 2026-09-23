from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bid_compare_agent.compare import ImageCompareConfig, TextCompareConfig


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
