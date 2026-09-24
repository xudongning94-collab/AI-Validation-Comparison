#!/usr/bin/env python3
"""OpenCV worker for seal candidates and signature ink inside configured regions.

This worker locates evidence candidates only. It does not authenticate a seal or
signature and must not be used as the sole basis for a compliance conclusion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_sha256(path: Path) -> str | None:
    try:
        return _sha256(path)
    except OSError:
        return None


def _quality_flags(
    x: int,
    y: int,
    w: int,
    h: int,
    width: int,
    height: int,
    *,
    fill_ratio: float,
) -> list[str]:
    flags: list[str] = []
    margin = 3
    if x <= margin or y <= margin or x + w >= width - margin or y + h >= height - margin:
        flags.append("clipped")
    if fill_ratio < 0.10:
        flags.append("low_opacity")
    return flags


def _seal_candidates(image: Any, page_number: int) -> list[dict[str, Any]]:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    masks = {
        "red": cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 55, 60]), np.array([12, 255, 255])),
            cv2.inRange(hsv, np.array([165, 55, 60]), np.array([179, 255, 255])),
        ),
        "blue": cv2.inRange(
            hsv,
            np.array([90, 55, 45]),
            np.array([140, 255, 255]),
        ),
    }
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    candidates: list[dict[str, Any]] = []
    canvas_area = float(width * height)
    for color, mask in masks.items():
        cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
        contours, _hierarchy = cv2.findContours(
            cleaned,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < max(100.0, canvas_area * 0.00004) or area > canvas_area * 0.12:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if min(w, h) < 16:
                continue
            aspect = min(w, h) / max(w, h)
            perimeter = float(cv2.arcLength(contour, True))
            circularity = 4.0 * math.pi * area / (perimeter * perimeter) if perimeter else 0.0
            fill_ratio = area / float(w * h)
            confidence = min(
                0.98,
                max(
                    0.25,
                    0.35
                    + 0.25 * aspect
                    + 0.25 * min(1.0, circularity)
                    + 0.15 * min(1.0, fill_ratio / 0.35),
                ),
            )
            candidates.append(
                {
                    "candidate_id": f"seal-{page_number}-{color}-{len(candidates):04d}",
                    "kind": "seal",
                    "page_number": page_number,
                    "bbox": {"x": float(x), "y": float(y), "w": float(w), "h": float(h)},
                    "confidence": round(confidence, 4),
                    "recognized_text": None,
                    "quality_flags": _quality_flags(
                        x,
                        y,
                        w,
                        h,
                        width,
                        height,
                        fill_ratio=fill_ratio,
                    ),
                    "detector": f"opencv-hsv-{color}-contour-v1",
                    "features": {
                        "color": color,
                        "area": round(area, 2),
                        "aspect": round(aspect, 4),
                        "circularity": round(circularity, 4),
                        "fill_ratio": round(fill_ratio, 4),
                    },
                }
            )
    return candidates


def _signature_candidate(
    image: Any,
    page_number: int,
    roi: tuple[int, int, int, int],
    index: int,
) -> dict[str, Any] | None:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    height, width = image.shape[:2]
    x, y, w, h = roi
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError(f"signature ROI outside image: {roi}")
    crop = image[y : y + h, x : x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)),
    )
    ink_pixels = int(cv2.countNonZero(binary))
    ink_ratio = ink_pixels / float(w * h)
    if ink_ratio < 0.002 or ink_ratio > 0.45:
        return None
    contours, _hierarchy = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    meaningful = [contour for contour in contours if cv2.contourArea(contour) >= 3.0]
    if not meaningful:
        return None
    points = np.vstack(meaningful)
    bx, by, bw, bh = cv2.boundingRect(points)
    spread = min(1.0, (bw * bh) / float(w * h) / 0.45)
    if spread < 0.03:
        return None
    component_score = min(1.0, len(meaningful) / 8.0)
    density_score = 1.0 - min(1.0, abs(ink_ratio - 0.08) / 0.20)
    confidence = max(0.25, min(0.92, 0.35 + 0.25 * spread + 0.2 * component_score + 0.2 * density_score))
    fill_ratio = ink_pixels / float(max(1, bw * bh))
    return {
        "candidate_id": f"signature-{page_number}-{index:04d}",
        "kind": "signature",
        "page_number": page_number,
        "bbox": {
            "x": float(x + bx),
            "y": float(y + by),
            "w": float(bw),
            "h": float(bh),
        },
        "confidence": round(confidence, 4),
        "recognized_text": None,
        "quality_flags": _quality_flags(
            x + bx,
            y + by,
            bw,
            bh,
            width,
            height,
            fill_ratio=fill_ratio,
        ),
        "detector": "opencv-signature-roi-ink-v1",
        "features": {
            "roi": [x, y, w, h],
            "ink_ratio": round(ink_ratio, 5),
            "component_count": len(meaningful),
            "spread": round(spread, 4),
        },
    }


def detect_candidates(
    image_path: Path,
    *,
    page_number: int,
    signature_rois: list[tuple[int, int, int, int]],
) -> dict[str, Any]:
    try:
        import cv2  # type: ignore
    except Exception as exc:
        return {
            "schema_version": "1.0.0",
            "engine": "opencv",
            "status": "disabled",
            "page_number": page_number,
            "image_sha256": _safe_sha256(image_path),
            "canvas": None,
            "candidates": [],
            "count": 0,
            "error": f"OpenCV import failed: {exc}",
            "metadata": {
                "method": "signature-seal-candidates-cv-v1",
                "authenticity_check": False,
                "signature_roi_count": len(signature_rois),
            },
        }

    try:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"cannot read image: {image_path}")
        height, width = image.shape[:2]
        candidates = _seal_candidates(image, page_number)
        for index, roi in enumerate(signature_rois):
            candidate = _signature_candidate(image, page_number, roi, index)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda item: (item["kind"], item["candidate_id"]))
        return {
            "schema_version": "1.0.0",
            "engine": "opencv",
            "status": "ok",
            "page_number": page_number,
            "image_sha256": _safe_sha256(image_path),
            "canvas": {"width": width, "height": height},
            "candidates": candidates,
            "count": len(candidates),
            "error": None,
            "metadata": {
                "method": "signature-seal-candidates-cv-v1",
                "authenticity_check": False,
                "signature_roi_count": len(signature_rois),
            },
        }
    except Exception as exc:
        return {
            "schema_version": "1.0.0",
            "engine": "opencv",
            "status": "failed",
            "page_number": page_number,
            "image_sha256": _safe_sha256(image_path),
            "canvas": None,
            "candidates": [],
            "count": 0,
            "error": repr(exc),
            "metadata": {
                "method": "signature-seal-candidates-cv-v1",
                "authenticity_check": False,
                "signature_roi_count": len(signature_rois),
            },
        }


def _parse_roi(value: str) -> tuple[int, int, int, int]:
    try:
        values = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ROI must be x,y,w,h integers") from exc
    if len(values) != 4:
        raise argparse.ArgumentTypeError("ROI must be x,y,w,h integers")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--signature-roi", action="append", type=_parse_roi, default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.page < 1:
        parser.error("--page must be >= 1")

    result = detect_candidates(
        args.image,
        page_number=args.page,
        signature_rois=args.signature_roi,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "count": len(result["candidates"])}, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
