#!/usr/bin/env python3
"""Run PaddleOCR with hash-verified local models and no implicit downloads."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable

WORKERS_DIRECTORY = Path(__file__).resolve().parent
if str(WORKERS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(WORKERS_DIRECTORY))

from offline_models import ModelManifestError, sha256_file, verify_model_package


def _selected_models(package: Any) -> dict[str, str]:
    return {kind: package.require(kind).model_id for kind in ("detection", "recognition")}


def _base_result(page_number: int, image_sha256: str | None) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "engine": "paddleocr",
        "status": "failed",
        "page_number": page_number,
        "image_sha256": image_sha256,
        "items": [],
        "count": 0,
        "error": None,
        "requested_profile": "offline-cpu",
        "selected_profile": None,
        "selected_models": {},
        "metadata": {
            "method": "paddleocr-offline-v1",
            "offline_only": True,
            "implicit_model_downloads": False,
        },
    }


def _failure(page_number: int, image_sha256: str | None, *, status: str, message: str) -> dict[str, Any]:
    result = _base_result(page_number, image_sha256)
    result["status"] = status
    result["error"] = message
    return result


def _default_engine_factory(**kwargs: Any) -> Any:
    from paddleocr import PaddleOCR  # type: ignore

    return PaddleOCR(**kwargs)


def _load_image(path: Path) -> Any:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("OCR input image cannot be decoded")
    return image


def _result_data(result: Any) -> dict[str, Any]:
    value = result if isinstance(result, dict) else getattr(result, "json", None)
    if not isinstance(value, dict):
        raise ValueError("PaddleOCR result is not JSON compatible")
    data = value.get("res", value)
    if not isinstance(data, dict):
        raise ValueError("PaddleOCR result payload is invalid")
    return data


def _sequence(value: Any) -> Any:
    to_list = getattr(value, "tolist", None)
    return to_list() if callable(to_list) else value


def _polygon(value: Any) -> list[list[float]]:
    value = _sequence(value)
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        raise ValueError("PaddleOCR polygon is invalid")
    points: list[list[float]] = []
    for point in value:
        point = _sequence(point)
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("PaddleOCR polygon point is invalid")
        x, y = float(point[0]), float(point[1])
        if not math.isfinite(x) or not math.isfinite(y) or x < 0 or y < 0:
            raise ValueError("PaddleOCR polygon coordinate is invalid")
        points.append([x, y])
    return points


def _box_polygon(value: Any) -> list[list[float]]:
    value = _sequence(value)
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("PaddleOCR box is invalid")
    left, top, right, bottom = (float(item) for item in value)
    if min(left, top, right, bottom) < 0 or right <= left or bottom <= top:
        raise ValueError("PaddleOCR box is invalid")
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def _items(results: Any) -> list[dict[str, Any]]:
    if not isinstance(results, (list, tuple)):
        raise ValueError("PaddleOCR predict result must be a list")
    items: list[dict[str, Any]] = []
    for result in results:
        data = _result_data(result)
        texts = data.get("rec_texts")
        scores = data.get("rec_scores")
        polygons = data.get("rec_polys")
        boxes = data.get("rec_boxes")
        if not isinstance(texts, (list, tuple)) or not isinstance(scores, (list, tuple)):
            raise ValueError("PaddleOCR text or score arrays are invalid")
        if len(texts) != len(scores):
            raise ValueError("PaddleOCR text and score arrays differ in length")
        shapes = polygons if isinstance(polygons, (list, tuple)) else boxes
        if not isinstance(shapes, (list, tuple)) or len(shapes) != len(texts):
            raise ValueError("PaddleOCR geometry array is invalid")
        use_boxes = shapes is boxes
        for text, score, shape in zip(texts, scores, shapes):
            normalized_text = str(text).strip()
            if not normalized_text:
                continue
            confidence = float(score)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("PaddleOCR confidence is invalid")
            polygon = _box_polygon(shape) if use_boxes else _polygon(shape)
            xs = [point[0] for point in polygon]
            ys = [point[1] for point in polygon]
            items.append(
                {
                    "id": f"ocr-text-{len(items):04d}",
                    "text": normalized_text,
                    "confidence": confidence,
                    "polygon": polygon,
                    "bbox": {"x": min(xs), "y": min(ys), "w": max(xs) - min(xs), "h": max(ys) - min(ys)},
                }
            )
    return items


def run_ocr(
    image_path: str | Path,
    *,
    page_number: int,
    model_directory: str | Path,
    engine_factory: Callable[..., Any] | None = None,
    image_loader: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    image = Path(image_path).resolve()
    try:
        image_hash = sha256_file(image)
    except OSError:
        return _failure(page_number, None, status="failed", message="OCR input image is unavailable.")
    try:
        package = verify_model_package(model_directory)
    except (ModelManifestError, OSError):
        return _failure(page_number, image_hash, status="disabled", message="Offline model package failed integrity validation.")

    detection = package.require("detection")
    recognition = package.require("recognition")
    detection_directory = detection.directory.relative_to(package.root)
    recognition_directory = recognition.directory.relative_to(package.root)
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    factory = engine_factory or _default_engine_factory
    loader = image_loader or _load_image
    previous_directory = Path.cwd()
    try:
        decoded_image = loader(image)
        os.chdir(package.root)
        engine = factory(
            text_detection_model_name=detection.model_name,
            text_detection_model_dir=str(detection_directory),
            text_recognition_model_name=recognition.model_name,
            text_recognition_model_dir=str(recognition_directory),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            enable_mkldnn=False,
        )
        predicted = engine.predict(
            decoded_image,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        if sha256_file(image) != image_hash:
            raise ValueError("OCR input image changed during inference")
        items = _items(predicted)
    except (ImportError, ModuleNotFoundError):
        return _failure(page_number, image_hash, status="disabled", message="PaddleOCR runtime is unavailable.")
    except Exception:
        return _failure(page_number, image_hash, status="failed", message="PaddleOCR inference failed.")
    finally:
        os.chdir(previous_directory)

    result = _base_result(page_number, image_hash)
    result.update(
        {
            "status": "ok",
            "items": items,
            "count": len(items),
            "selected_profile": "offline-cpu",
            "selected_models": _selected_models(package),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.page < 1:
        parser.error("--page must be >= 1")
    result = run_ocr(args.image, page_number=args.page, model_directory=args.model_dir)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
