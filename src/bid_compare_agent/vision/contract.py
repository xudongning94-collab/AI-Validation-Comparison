from __future__ import annotations

import math
from typing import Any


ALLOWED_STATUSES = {"ok", "failed", "disabled"}
LOW_CONFIDENCE_THRESHOLD = 0.82


class VisionContractError(ValueError):
    """Raised when an OCR worker result cannot be used as traceable evidence."""


def _number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise VisionContractError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VisionContractError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise VisionContractError(f"{field} must be a finite number")
    if minimum is not None and number < minimum:
        raise VisionContractError(f"{field} must be >= {minimum}")
    return number


def _bbox(value: Any, item_id: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise VisionContractError(f"{item_id}.bbox must be an object")
    result = {
        key: _number(value.get(key), f"{item_id}.bbox.{key}", minimum=0.0)
        for key in ("x", "y", "w", "h")
    }
    if result["w"] == 0 or result["h"] == 0:
        raise VisionContractError(f"{item_id}.bbox must have positive width and height")
    return result


def _polygon(value: Any, item_id: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) < 4:
        raise VisionContractError(f"{item_id}.polygon must contain at least four points")
    points: list[list[float]] = []
    for index, point in enumerate(value):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise VisionContractError(f"{item_id}.polygon[{index}] must be an x/y pair")
        points.append(
            [
                _number(point[0], f"{item_id}.polygon[{index}].x", minimum=0.0),
                _number(point[1], f"{item_id}.polygon[{index}].y", minimum=0.0),
            ]
        )
    return points


def normalize_ocr_worker_result(
    payload: dict[str, Any],
    *,
    document_id: str,
    page_number: int,
    image_sha256: str,
) -> dict[str, Any]:
    """Normalize a PaddleOCR-compatible result into the product evidence contract.

    OCR is evidence only. Confidence and review status are retained so downstream
    compliance rules cannot silently treat uncertain text as ground truth.
    """
    if not isinstance(payload, dict):
        raise VisionContractError("worker payload must be an object")
    if not document_id.strip():
        raise VisionContractError("document_id must not be empty")
    if page_number < 1:
        raise VisionContractError("page_number must be >= 1")
    if len(image_sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in image_sha256):
        raise VisionContractError("image_sha256 must be a 64-character hexadecimal digest")

    status = str(payload.get("status", "")).strip()
    if status not in ALLOWED_STATUSES:
        raise VisionContractError(f"unsupported worker status: {status!r}")
    engine = str(payload.get("engine", "")).strip()
    if not engine:
        raise VisionContractError("worker engine must not be empty")

    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        raise VisionContractError("worker items must be an array")
    if status != "ok" and raw_items:
        raise VisionContractError("failed or disabled worker results cannot contain evidence items")

    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise VisionContractError(f"items[{index}] must be an object")
        item_id = str(raw.get("id") or f"ocr-text-{index:04d}")
        text = str(raw.get("text", "")).strip()
        if not text:
            raise VisionContractError(f"{item_id}.text must not be empty")
        confidence = _number(raw.get("confidence"), f"{item_id}.confidence", minimum=0.0)
        if confidence > 1.0:
            raise VisionContractError(f"{item_id}.confidence must be <= 1.0")
        items.append(
            {
                "evidence_id": f"{document_id}:page-{page_number}:{item_id}",
                "text": text,
                "confidence": confidence,
                "polygon": _polygon(raw.get("polygon"), item_id),
                "bbox": _bbox(raw.get("bbox"), item_id),
                "review_status": "ok" if confidence >= LOW_CONFIDENCE_THRESHOLD else "low-confidence",
            }
        )

    error = str(payload.get("error", "")).strip() or None
    return {
        "schema_version": "1.0.0",
        "evidence_type": "page_ocr",
        "document_id": document_id,
        "page_number": page_number,
        "image_sha256": image_sha256.lower(),
        "engine": engine,
        "status": status,
        "items": items,
        "requires_human_review": status != "ok" or any(
            item["review_status"] != "ok" for item in items
        ),
        "error": error,
        "metadata": {
            "requested_profile": payload.get("requested_profile"),
            "selected_profile": payload.get("selected_profile"),
            "selected_models": payload.get("selected_models") or {},
        },
    }
