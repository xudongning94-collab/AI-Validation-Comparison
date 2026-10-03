from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


SUPPORTED_KINDS = ("signature", "seal")
SUPPORTED_SPLITS = {"calibration", "validation"}


class SignatureCalibrationError(ValueError):
    """Raised when a signature calibration dataset or worker result is invalid."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        raise SignatureCalibrationError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SignatureCalibrationError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise SignatureCalibrationError(f"{field} must be a finite number")
    if minimum is not None and number < minimum:
        raise SignatureCalibrationError(f"{field} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise SignatureCalibrationError(f"{field} must be <= {maximum}")
    return number


def _bbox(value: Any, field: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {"x", "y", "w", "h"}:
        raise SignatureCalibrationError(f"{field} must contain only x/y/w/h")
    result = {
        key: _finite_number(value[key], f"{field}.{key}", minimum=0.0)
        for key in ("x", "y", "w", "h")
    }
    if result["w"] <= 0 or result["h"] <= 0:
        raise SignatureCalibrationError(f"{field} width and height must be positive")
    return result


def bbox_iou(left: dict[str, float], right: dict[str, float]) -> float:
    """Return intersection-over-union for two x/y/w/h boxes."""
    left_x2 = left["x"] + left["w"]
    left_y2 = left["y"] + left["h"]
    right_x2 = right["x"] + right["w"]
    right_y2 = right["y"] + right["h"]
    intersection_w = max(0.0, min(left_x2, right_x2) - max(left["x"], right["x"]))
    intersection_h = max(0.0, min(left_y2, right_y2) - max(left["y"], right["y"]))
    intersection = intersection_w * intersection_h
    union = left["w"] * left["h"] + right["w"] * right["h"] - intersection
    return intersection / union if union > 0 else 0.0


def load_signature_calibration_manifest(
    path: str | Path,
) -> tuple[dict[str, Any], Path]:
    manifest_path = Path(path).resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SignatureCalibrationError(f"cannot read calibration manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise SignatureCalibrationError("calibration manifest must be an object")
    return payload, manifest_path.parent


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("signature_calibration", config)
    if not isinstance(raw, dict):
        raise SignatureCalibrationError("signature_calibration config must be an object")
    iou_threshold = _finite_number(
        raw.get("iou_threshold", 0.30),
        "iou_threshold",
        minimum=0.0,
        maximum=1.0,
    )
    minimum_recall = _finite_number(
        raw.get("minimum_recall", 0.85),
        "minimum_recall",
        minimum=0.0,
        maximum=1.0,
    )
    raw_thresholds = raw.get("confidence_thresholds")
    if not isinstance(raw_thresholds, list) or not raw_thresholds:
        raise SignatureCalibrationError("confidence_thresholds must be a non-empty array")
    thresholds = sorted(
        {
            _finite_number(
                value,
                "confidence_thresholds[]",
                minimum=0.0,
                maximum=1.0,
            )
            for value in raw_thresholds
        }
    )
    raw_kinds = raw.get("required_kinds", list(SUPPORTED_KINDS))
    if not isinstance(raw_kinds, list) or not raw_kinds:
        raise SignatureCalibrationError("required_kinds must be a non-empty array")
    required_kinds = tuple(str(item) for item in raw_kinds)
    if len(required_kinds) != len(set(required_kinds)) or any(
        kind not in SUPPORTED_KINDS for kind in required_kinds
    ):
        raise SignatureCalibrationError(
            "required_kinds must contain unique signature/seal values"
        )
    return {
        "iou_threshold": iou_threshold,
        "minimum_recall": minimum_recall,
        "confidence_thresholds": thresholds,
        "required_kinds": required_kinds,
    }


def _normalize_manifest(
    manifest: dict[str, Any],
    manifest_dir: Path,
) -> tuple[str, list[dict[str, Any]]]:
    if manifest.get("schema_version") != "1.1.0":
        raise SignatureCalibrationError(
            "calibration manifest schema_version must be 1.1.0"
        )
    calibration_id = str(manifest.get("calibration_id") or "").strip()
    if not calibration_id:
        raise SignatureCalibrationError("calibration_id must not be empty")
    privacy = manifest.get("privacy") or {}
    if not isinstance(privacy, dict) or privacy.get("include_source_paths") is not False:
        raise SignatureCalibrationError("privacy.include_source_paths must be false")
    raw_samples = manifest.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise SignatureCalibrationError("samples must be a non-empty array")

    samples: list[dict[str, Any]] = []
    seen_sample_ids: set[str] = set()
    seen_annotation_ids: set[str] = set()
    document_group_splits: dict[str, str] = {}
    for sample_index, raw in enumerate(raw_samples):
        if not isinstance(raw, dict):
            raise SignatureCalibrationError(f"samples[{sample_index}] must be an object")
        sample_id = str(raw.get("id") or "").strip()
        if not sample_id or sample_id in seen_sample_ids:
            raise SignatureCalibrationError(
                f"sample id is empty or duplicated: {sample_id!r}"
            )
        seen_sample_ids.add(sample_id)
        split = str(raw.get("split") or "calibration")
        if split not in SUPPORTED_SPLITS:
            raise SignatureCalibrationError(f"unsupported sample split: {split!r}")
        document_group_id = str(raw.get("document_group_id") or "").strip()
        if not document_group_id:
            raise SignatureCalibrationError(
                f"{sample_id}.document_group_id must not be empty"
            )
        existing_split = document_group_splits.get(document_group_id)
        if existing_split is not None and existing_split != split:
            raise SignatureCalibrationError(
                "document group must not appear in both calibration and validation: "
                f"{document_group_id!r}"
            )
        document_group_splits[document_group_id] = split
        raw_path = str(raw.get("image") or "").strip()
        path = Path(raw_path)
        if not path.is_absolute():
            path = manifest_dir / path
        path = path.resolve()
        if not path.is_file():
            raise SignatureCalibrationError(f"sample image does not exist: {sample_id}")
        page_number = raw.get("page_number", 1)
        if (
            isinstance(page_number, bool)
            or not isinstance(page_number, int)
            or page_number < 1
        ):
            raise SignatureCalibrationError(
                f"{sample_id}.page_number must be a positive integer"
            )

        raw_rois = raw.get("signature_rois", [])
        if not isinstance(raw_rois, list):
            raise SignatureCalibrationError(
                f"{sample_id}.signature_rois must be an array"
            )
        signature_rois: list[tuple[int, int, int, int]] = []
        for roi_index, roi in enumerate(raw_rois):
            if (
                not isinstance(roi, list)
                or len(roi) != 4
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in roi
                )
                or roi[0] < 0
                or roi[1] < 0
                or roi[2] <= 0
                or roi[3] <= 0
            ):
                raise SignatureCalibrationError(
                    f"{sample_id}.signature_rois[{roi_index}] must be non-negative "
                    "x/y and positive w/h integers"
                )
            signature_rois.append(tuple(roi))

        raw_annotations = raw.get("annotations", [])
        if not isinstance(raw_annotations, list):
            raise SignatureCalibrationError(
                f"{sample_id}.annotations must be an array"
            )
        annotations: list[dict[str, Any]] = []
        for annotation_index, annotation in enumerate(raw_annotations):
            if not isinstance(annotation, dict):
                raise SignatureCalibrationError(
                    f"{sample_id}.annotations[{annotation_index}] must be an object"
                )
            annotation_id = str(annotation.get("id") or "").strip()
            if not annotation_id or annotation_id in seen_annotation_ids:
                raise SignatureCalibrationError(
                    f"annotation id is empty or duplicated: {annotation_id!r}"
                )
            seen_annotation_ids.add(annotation_id)
            kind = str(annotation.get("kind") or "")
            if kind not in SUPPORTED_KINDS:
                raise SignatureCalibrationError(
                    f"unsupported annotation kind: {kind!r}"
                )
            ignored = annotation.get("ignore", False)
            if not isinstance(ignored, bool):
                raise SignatureCalibrationError(f"{annotation_id}.ignore must be boolean")
            annotations.append(
                {
                    "id": annotation_id,
                    "kind": kind,
                    "bbox": _bbox(annotation.get("bbox"), f"{annotation_id}.bbox"),
                    "ignore": ignored,
                }
            )
        samples.append(
            {
                "id": sample_id,
                "document_group_id": document_group_id,
                "split": split,
                "path": path,
                "page_number": page_number,
                "signature_rois": signature_rois,
                "annotations": annotations,
            }
        )
    if not any(sample["split"] == "calibration" for sample in samples):
        raise SignatureCalibrationError("at least one calibration sample is required")
    return calibration_id, samples


def _normalize_candidates(
    result: Any,
    *,
    sample_id: str,
    page_number: int,
) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(result, dict):
        raise SignatureCalibrationError(f"worker result for {sample_id} must be an object")
    if result.get("status") != "ok":
        error = str(result.get("error") or result.get("status") or "unknown error")
        raise SignatureCalibrationError(f"worker failed for {sample_id}: {error}")
    image_sha256 = str(result.get("image_sha256") or "").lower()
    if len(image_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in image_sha256):
        raise SignatureCalibrationError(f"worker result for {sample_id} has invalid image_sha256")
    raw_candidates = result.get("candidates")
    if not isinstance(raw_candidates, list):
        raise SignatureCalibrationError(f"worker candidates for {sample_id} must be an array")
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict):
            raise SignatureCalibrationError(f"candidate {index} for {sample_id} must be an object")
        candidate_id = str(raw.get("candidate_id") or "").strip()
        if not candidate_id or candidate_id in seen_ids:
            raise SignatureCalibrationError(f"candidate id is empty or duplicated in {sample_id}")
        seen_ids.add(candidate_id)
        kind = str(raw.get("kind") or "")
        if kind not in SUPPORTED_KINDS:
            raise SignatureCalibrationError(f"unsupported candidate kind: {kind!r}")
        candidate_page = raw.get("page_number")
        if candidate_page != page_number:
            raise SignatureCalibrationError(f"candidate page does not match sample {sample_id}")
        candidates.append(
            {
                "id": candidate_id,
                "kind": kind,
                "bbox": _bbox(raw.get("bbox"), f"{candidate_id}.bbox"),
                "confidence": _finite_number(
                    raw.get("confidence"),
                    f"{candidate_id}.confidence",
                    minimum=0.0,
                    maximum=1.0,
                ),
            }
        )
    return candidates, image_sha256


def _match_sample(
    annotations: Iterable[dict[str, Any]],
    candidates: Iterable[dict[str, Any]],
    *,
    kind: str,
    confidence_threshold: float,
    iou_threshold: float,
) -> dict[str, int]:
    truth = [item for item in annotations if item["kind"] == kind and not item["ignore"]]
    ignored = [item for item in annotations if item["kind"] == kind and item["ignore"]]
    detected = [
        item
        for item in candidates
        if item["kind"] == kind and item["confidence"] >= confidence_threshold
    ]
    pairs: list[tuple[float, str, str, int, int]] = []
    for truth_index, truth_item in enumerate(truth):
        for candidate_index, candidate in enumerate(detected):
            overlap = bbox_iou(truth_item["bbox"], candidate["bbox"])
            if overlap >= iou_threshold:
                pairs.append(
                    (
                        overlap,
                        truth_item["id"],
                        candidate["id"],
                        truth_index,
                        candidate_index,
                    )
                )
    pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
    matched_truth: set[int] = set()
    matched_candidates: set[int] = set()
    for _overlap, _truth_id, _candidate_id, truth_index, candidate_index in pairs:
        if truth_index in matched_truth or candidate_index in matched_candidates:
            continue
        matched_truth.add(truth_index)
        matched_candidates.add(candidate_index)

    ignored_candidates = 0
    for candidate_index, candidate in enumerate(detected):
        if candidate_index in matched_candidates:
            continue
        if any(bbox_iou(item["bbox"], candidate["bbox"]) >= iou_threshold for item in ignored):
            ignored_candidates += 1

    false_positives = len(detected) - len(matched_candidates) - ignored_candidates
    return {
        "true_positives": len(matched_candidates),
        "false_positives": false_positives,
        "false_negatives": len(truth) - len(matched_truth),
        "ground_truth_count": len(truth),
        "candidate_count": len(detected),
        "ignored_candidate_count": ignored_candidates,
        "negative_page": int(len(truth) == 0),
        "false_positive_page": int(len(truth) == 0 and false_positives > 0),
    }


def _metrics(counts: dict[str, int]) -> dict[str, Any]:
    true_positives = counts["true_positives"]
    false_positives = counts["false_positives"]
    false_negatives = counts["false_negatives"]
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    precision = true_positives / precision_denominator if precision_denominator else 0.0
    recall = true_positives / recall_denominator if recall_denominator else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negative_pages = counts["negative_pages"]
    return {
        **counts,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "false_discovery_rate": round(1.0 - precision, 6) if precision_denominator else 0.0,
        "miss_rate": round(1.0 - recall, 6) if recall_denominator else 0.0,
        "false_positive_page_rate": round(
            counts["false_positive_pages"] / negative_pages,
            6,
        )
        if negative_pages
        else 0.0,
    }


def _evaluate(
    samples: Iterable[dict[str, Any]],
    *,
    kind: str,
    confidence_threshold: float,
    iou_threshold: float,
) -> dict[str, Any]:
    counts = {
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "ground_truth_count": 0,
        "candidate_count": 0,
        "ignored_candidate_count": 0,
        "negative_pages": 0,
        "false_positive_pages": 0,
    }
    sample_count = 0
    for sample in samples:
        sample_count += 1
        result = _match_sample(
            sample["annotations"],
            sample["candidates"],
            kind=kind,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
        )
        for key in (
            "true_positives",
            "false_positives",
            "false_negatives",
            "ground_truth_count",
            "candidate_count",
            "ignored_candidate_count",
        ):
            counts[key] += result[key]
        counts["negative_pages"] += result["negative_page"]
        counts["false_positive_pages"] += result["false_positive_page"]
    return {
        "sample_count": sample_count,
        "kind": kind,
        "confidence_threshold": round(confidence_threshold, 6),
        **_metrics(counts),
    }


def _recommend_threshold(
    rows: list[dict[str, Any]],
    *,
    minimum_recall: float,
) -> dict[str, Any] | None:
    if not rows or not any(row["ground_truth_count"] > 0 for row in rows):
        return None
    eligible = [row for row in rows if row["recall"] >= minimum_recall]
    pool = eligible or rows
    selected = max(
        pool,
        key=lambda row: (
            row["f1"],
            row["recall"],
            row["precision"],
            row["confidence_threshold"],
        ),
    )
    return {
        "confidence_threshold": selected["confidence_threshold"],
        "minimum_recall_target": minimum_recall,
        "meets_minimum_recall": selected["recall"] >= minimum_recall,
        "selection_metric": "max_f1_with_recall_floor",
    }


def calibrate_signature_candidates(
    manifest: dict[str, Any],
    *,
    manifest_dir: str | Path,
    config: dict[str, Any],
    detector: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run privacy-preserving threshold calibration against local human labels."""
    normalized_config = _normalize_config(config)
    calibration_id, samples = _normalize_manifest(manifest, Path(manifest_dir).resolve())
    before_hashes = {sample["id"]: _file_sha256(sample["path"]) for sample in samples}

    evaluated: list[dict[str, Any]] = []
    sample_summaries: list[dict[str, Any]] = []
    for sample in samples:
        worker_result = detector(
            sample["path"],
            page_number=sample["page_number"],
            signature_rois=sample["signature_rois"],
        )
        candidates, image_sha256 = _normalize_candidates(
            worker_result,
            sample_id=sample["id"],
            page_number=sample["page_number"],
        )
        if image_sha256 != before_hashes[sample["id"]]:
            raise SignatureCalibrationError(
                f"worker image hash does not match source for {sample['id']}"
            )
        evaluated.append({**sample, "candidates": candidates})
        sample_summaries.append(
            {
                "id": sample["id"],
                "split": sample["split"],
                "page_number": sample["page_number"],
                "image_sha256": image_sha256,
                "annotation_counts": {
                    kind: sum(
                        1
                        for item in sample["annotations"]
                        if item["kind"] == kind and not item["ignore"]
                    )
                    for kind in SUPPORTED_KINDS
                },
                "raw_candidate_counts": {
                    kind: sum(1 for item in candidates if item["kind"] == kind)
                    for kind in SUPPORTED_KINDS
                },
            }
        )

    after_hashes = {sample["id"]: _file_sha256(sample["path"]) for sample in samples}
    inputs_unchanged = before_hashes == after_hashes
    if not inputs_unchanged:
        raise SignatureCalibrationError("one or more calibration images changed during execution")

    calibration_samples = [item for item in evaluated if item["split"] == "calibration"]
    validation_samples = [item for item in evaluated if item["split"] == "validation"]
    calibration_groups = {
        item["document_group_id"] for item in calibration_samples
    }
    validation_groups = {
        item["document_group_id"] for item in validation_samples
    }
    sweep: list[dict[str, Any]] = []
    recommendations: dict[str, dict[str, Any] | None] = {}
    calibration_metrics: dict[str, dict[str, Any] | None] = {}
    validation_metrics: dict[str, dict[str, Any] | None] = {}
    for kind in normalized_config["required_kinds"]:
        rows = [
            _evaluate(
                calibration_samples,
                kind=kind,
                confidence_threshold=threshold,
                iou_threshold=normalized_config["iou_threshold"],
            )
            for threshold in normalized_config["confidence_thresholds"]
        ]
        sweep.extend(rows)
        recommendation = _recommend_threshold(
            rows,
            minimum_recall=normalized_config["minimum_recall"],
        )
        recommendations[kind] = recommendation
        if recommendation is None:
            calibration_metrics[kind] = None
            validation_metrics[kind] = None
            continue
        threshold = recommendation["confidence_threshold"]
        calibration_metrics[kind] = _evaluate(
            calibration_samples,
            kind=kind,
            confidence_threshold=threshold,
            iou_threshold=normalized_config["iou_threshold"],
        )
        validation_metrics[kind] = (
            _evaluate(
                validation_samples,
                kind=kind,
                confidence_threshold=threshold,
                iou_threshold=normalized_config["iou_threshold"],
            )
            if validation_samples
            else None
        )

    has_all_recommendations = all(
        recommendations[kind] is not None for kind in normalized_config["required_kinds"]
    )
    validation_has_all_truth = bool(validation_samples) and all(
        validation_metrics[kind] is not None
        and validation_metrics[kind]["ground_truth_count"] > 0
        for kind in normalized_config["required_kinds"]
    )
    status = (
        "validated"
        if validation_has_all_truth and has_all_recommendations
        else "calibration_only"
    )

    return {
        "schema_version": "1.0.0",
        "calibration_type": "signature_candidate_thresholds",
        "calibration_id": calibration_id,
        "status": status,
        "privacy": {
            "source_paths_included": False,
            "source_files_embedded": False,
            "raw_images_embedded": False,
            "sample_hashes_included": True,
        },
        "dataset": {
            "sample_count": len(evaluated),
            "calibration_sample_count": len(calibration_samples),
            "validation_sample_count": len(validation_samples),
            "document_group_count": len(calibration_groups | validation_groups),
            "calibration_document_group_count": len(calibration_groups),
            "validation_document_group_count": len(validation_groups),
            "samples": sample_summaries,
        },
        "configuration": {
            "iou_threshold": normalized_config["iou_threshold"],
            "minimum_recall": normalized_config["minimum_recall"],
            "confidence_thresholds": normalized_config["confidence_thresholds"],
            "required_kinds": list(normalized_config["required_kinds"]),
        },
        "threshold_sweep": sweep,
        "recommended_thresholds": recommendations,
        "calibration_metrics": calibration_metrics,
        "validation_metrics": validation_metrics,
        "integrity": {
            "inputs_unchanged": inputs_unchanged,
            "verified_file_count": len(evaluated),
        },
        "limitations": [
            "候选检测校准只衡量存在性与定位效果，不能鉴定签名或印章真伪。",
            "对象检测没有对象级真负例，误报以 false discovery rate 和负样本页误报率表达。",
            "未包含独立 validation 真值时状态为 calibration_only，推荐阈值不得视为已完成外部验证。",
            "同一源文档及其派生页面必须使用相同 document_group_id，且不得跨 calibration/validation。",
            "真实业务样本、标注清单和运行报告保持本地，不提交 Git。",
        ],
        "metadata": {
            "method": "signature-candidate-calibration-v1",
            "matching": "greedy-iou-one-to-one-v1",
            "authenticity_check": False,
        },
    }
