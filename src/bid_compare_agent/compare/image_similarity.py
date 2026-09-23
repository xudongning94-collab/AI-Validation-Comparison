from __future__ import annotations

import hashlib
from dataclasses import dataclass
from itertools import combinations

from bid_compare_agent.models.document_ir import DocumentIR, ImageIR, SourceLocator
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.models.image_compare import (
    DocumentImageStats,
    ImageComparisonResult,
    ImagePairSummary,
)
from bid_compare_agent.utils.image import aspect_ratio_delta, color_similarity, hamming_distance


@dataclass(frozen=True)
class ImageCompareConfig:
    phash_exact_max_distance: int = 5
    phash_high_max_distance: int = 15
    color_similarity_min: float = 0.55
    aspect_ratio_delta_max: float = 0.25
    min_side_px: int = 8

    def __post_init__(self) -> None:
        if self.phash_exact_max_distance < 0:
            raise ValueError("phash_exact_max_distance 必须 >= 0")
        if self.phash_high_max_distance < self.phash_exact_max_distance:
            raise ValueError("phash_high_max_distance 必须 >= phash_exact_max_distance")
        if not 0 <= self.color_similarity_min <= 1:
            raise ValueError("color_similarity_min 必须位于 0~1")
        if self.aspect_ratio_delta_max < 0:
            raise ValueError("aspect_ratio_delta_max 必须 >= 0")
        if self.min_side_px < 1:
            raise ValueError("min_side_px 必须 >= 1")


def _eligible(image: ImageIR, config: ImageCompareConfig) -> bool:
    if not image.phash:
        return False
    if image.width_px is not None and image.width_px < config.min_side_px:
        return False
    if image.height_px is not None and image.height_px < config.min_side_px:
        return False
    return True


def _stable_finding_id(doc_a: DocumentIR, img_a: ImageIR, doc_b: DocumentIR, img_b: ImageIR) -> str:
    raw = f"{doc_a.sha256}|{img_a.id}|{doc_b.sha256}|{img_b.id}".encode("utf-8")
    return f"img-{hashlib.sha256(raw).hexdigest()[:24]}"


def _image_similarity(
    left: ImageIR,
    right: ImageIR,
    config: ImageCompareConfig,
) -> tuple[str, int, float, float, float] | None:
    # 字节完全一致时无需走感知哈希，直接判定为完全重复。
    if left.sha256 and right.sha256 and left.sha256 == right.sha256:
        return "exact", 0, 1.0, 1.0, 0.0

    if not left.phash or not right.phash:
        return None

    ratio_delta = aspect_ratio_delta(
        left.width_px,
        left.height_px,
        right.width_px,
        right.height_px,
    )
    if ratio_delta > config.aspect_ratio_delta_max:
        return None

    distance = hamming_distance(left.phash, right.phash)
    if distance > config.phash_high_max_distance:
        return None

    color_score = color_similarity(left.mean_rgb, right.mean_rgb)
    if color_score < config.color_similarity_min:
        return None

    hash_bits = max(len(left.phash), len(right.phash)) * 4
    phash_score = max(0.0, 1.0 - distance / max(1, hash_bits))
    # pHash 是主判据，平均色只做轻量防误报辅助。
    similarity = max(0.0, min(1.0, phash_score * 0.85 + color_score * 0.15))
    match_class = "exact" if distance <= config.phash_exact_max_distance else "high_similar"
    return match_class, distance, round(similarity, 6), round(color_score, 6), round(ratio_delta, 6)


def _make_finding(
    doc_a: DocumentIR,
    img_a: ImageIR,
    doc_b: DocumentIR,
    img_b: ImageIR,
    match_class: str,
    distance: int,
    similarity: float,
    color_score: float,
    ratio_delta: float,
    config: ImageCompareConfig,
) -> Finding:
    source_locator = img_a.source_locator or SourceLocator(kind="unknown")
    peer_locator = img_b.source_locator or SourceLocator(kind="unknown")
    label = "完全重复" if match_class == "exact" else "高度相似"
    return Finding(
        finding_id=_stable_finding_id(doc_a, img_a, doc_b, img_b),
        type="image_similarity",
        severity="high",
        document_id=doc_a.document_id,
        peer_document_id=doc_b.document_id,
        source_locator=source_locator,
        peer_source_locator=peer_locator,
        score=similarity,
        summary=(
            f"{doc_a.filename} 与 {doc_b.filename} 检测到{label}图片，"
            f"相似度 {similarity * 100:.1f}%"
        ),
        evidence={
            "source_image_id": img_a.id,
            "peer_image_id": img_b.id,
            "source_filename": img_a.filename,
            "peer_filename": img_b.filename,
            "source_size": [img_a.width_px, img_a.height_px],
            "peer_size": [img_b.width_px, img_b.height_px],
            "source_sha256": img_a.sha256,
            "peer_sha256": img_b.sha256,
            "source_phash": img_a.phash,
            "peer_phash": img_b.phash,
            "match_class": match_class,
        },
        metadata={
            "algorithm": "phash-alpha-v1",
            "phash_hamming_distance": distance,
            "color_similarity": color_score,
            "aspect_ratio_delta": ratio_delta,
            "phash_exact_max_distance": config.phash_exact_max_distance,
            "phash_high_max_distance": config.phash_high_max_distance,
        },
    )


def compare_image_pair(
    doc_a: DocumentIR,
    doc_b: DocumentIR,
    config: ImageCompareConfig | None = None,
) -> tuple[list[Finding], ImagePairSummary]:
    config = config or ImageCompareConfig()
    left = [image for image in doc_a.images if _eligible(image, config)]
    right = [image for image in doc_b.images if _eligible(image, config)]

    findings: list[Finding] = []
    seen_pairs: set[tuple[str, str]] = set()
    for image_a in left:
        for image_b in right:
            result = _image_similarity(image_a, image_b, config)
            if result is None:
                continue
            key = (image_a.id, image_b.id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            match_class, distance, similarity, color_score, ratio_delta = result
            findings.append(
                _make_finding(
                    doc_a,
                    image_a,
                    doc_b,
                    image_b,
                    match_class,
                    distance,
                    similarity,
                    color_score,
                    ratio_delta,
                    config,
                )
            )

    findings.sort(
        key=lambda f: (
            -float(f.score or 0.0),
            str(f.evidence.get("source_image_id")),
            str(f.evidence.get("peer_image_id")),
        )
    )

    repeated_left = {str(f.evidence["source_image_id"]) for f in findings}
    repeated_right = {str(f.evidence["peer_image_id"]) for f in findings}
    left_stats = DocumentImageStats(
        document_id=doc_a.document_id,
        filename=doc_a.filename,
        eligible_images=len(left),
        repeated_images=len(repeated_left),
        repeated_rate=round(len(repeated_left) / len(left), 6) if left else 0.0,
    )
    right_stats = DocumentImageStats(
        document_id=doc_b.document_id,
        filename=doc_b.filename,
        eligible_images=len(right),
        repeated_images=len(repeated_right),
        repeated_rate=round(len(repeated_right) / len(right), 6) if right else 0.0,
    )
    summary = ImagePairSummary(
        document_a_id=doc_a.document_id,
        document_b_id=doc_b.document_id,
        document_a_filename=doc_a.filename,
        document_b_filename=doc_b.filename,
        exact_pairs=sum(1 for f in findings if f.evidence.get("match_class") == "exact"),
        high_similar_pairs=sum(
            1 for f in findings if f.evidence.get("match_class") == "high_similar"
        ),
        max_similarity=max((float(f.score or 0.0) for f in findings), default=0.0),
        document_a=left_stats,
        document_b=right_stats,
    )
    return findings, summary


def compare_image_set(
    documents: list[DocumentIR],
    config: ImageCompareConfig | None = None,
) -> ImageComparisonResult:
    if len(documents) < 2:
        raise ValueError("图片比对至少需要 2 份文档")
    if len(documents) > 5:
        raise ValueError("当前单批最多支持 5 份文档")

    config = config or ImageCompareConfig()
    all_findings: list[Finding] = []
    summaries: list[ImagePairSummary] = []
    for doc_a, doc_b in combinations(documents, 2):
        findings, summary = compare_image_pair(doc_a, doc_b, config=config)
        all_findings.extend(findings)
        summaries.append(summary)

    return ImageComparisonResult(
        schema_version="1.0.0",
        compare_type="image_similarity",
        documents=[
            {"document_id": doc.document_id, "filename": doc.filename, "sha256": doc.sha256}
            for doc in documents
        ],
        pair_summaries=summaries,
        findings=all_findings,
        metadata={
            "algorithm": "phash-alpha-v1",
            "phash_exact_max_distance": config.phash_exact_max_distance,
            "phash_high_max_distance": config.phash_high_max_distance,
            "color_similarity_min": config.color_similarity_min,
            "aspect_ratio_delta_max": config.aspect_ratio_delta_max,
        },
    )
