#!/usr/bin/env python3
"""Report isolated vision-worker runtime readiness without loading model weights."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

WORKERS_DIRECTORY = Path(__file__).resolve().parent
if str(WORKERS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(WORKERS_DIRECTORY))

from offline_models import public_model_state


REQUIRED_PYTHON = (3, 12)
DEPENDENCIES = {
    "opencv": ("cv2", ("opencv-contrib-python", "opencv-python")),
    "numpy": ("numpy", ("numpy",)),
    "paddleocr": ("paddleocr", ("paddleocr",)),
    "paddlepaddle": ("paddle", ("paddlepaddle",)),
}
OFFLINE_MODEL_ENVIRONMENT_VARIABLE = "BID_COMPARE_PADDLEOCR_MODEL_DIR"


def _offline_models(directory: str | Path | None) -> dict[str, Any]:
    return public_model_state(directory)


def _dependency(import_name: str, distributions: tuple[str, ...]) -> dict[str, Any]:
    available = importlib.util.find_spec(import_name) is not None
    version = None
    if available:
        for distribution in distributions:
            try:
                version = importlib.metadata.version(distribution)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
    return {"available": available, "version": version}


def build_health() -> dict[str, Any]:
    python_compatible = sys.version_info[:2] == REQUIRED_PYTHON
    offline_models = _offline_models(os.environ.get(OFFLINE_MODEL_ENVIRONMENT_VARIABLE))
    dependencies = {
        name: _dependency(import_name, distributions)
        for name, (import_name, distributions) in DEPENDENCIES.items()
    }
    signature_ready = python_compatible and all(
        dependencies[name]["available"] for name in ("opencv", "numpy")
    )
    ocr_dependencies_ready = signature_ready and all(
        dependencies[name]["available"] for name in ("paddleocr", "paddlepaddle")
    )
    ocr_ready = ocr_dependencies_ready and offline_models["manifest_valid"]

    if ocr_ready:
        status = "ready"
        error = None
    elif not python_compatible:
        status = "unavailable"
        error = {
            "code": "python_version_incompatible",
            "message": "Vision worker requires CPython 3.12.",
        }
    elif not signature_ready:
        status = "unavailable"
        error = {
            "code": "candidate_dependencies_missing",
            "message": "OpenCV or NumPy is unavailable in the vision-worker runtime.",
        }
    elif not ocr_dependencies_ready:
        status = "degraded"
        error = {
            "code": "ocr_dependencies_missing",
            "message": "Signature candidates are available but OCR dependencies are incomplete.",
        }
    else:
        status = "degraded"
        error = {
            "code": "offline_models_unavailable",
            "message": "OCR dependencies exist but the offline model manifest is not valid.",
        }

    return {
        "schema_version": "1.0.0",
        "status": status,
        "required_python": "3.12",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_compatible": python_compatible,
        "capabilities": {
            "signature_candidates": signature_ready,
            "ocr": ocr_ready,
            "authenticity_check": False,
        },
        "dependencies": dependencies,
        "offline_models": offline_models,
        "error": error,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build_health(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
