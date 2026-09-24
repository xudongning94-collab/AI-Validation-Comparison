from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from bid_compare_agent.vision import VisionContractError, normalize_ocr_worker_result


def _worker_payload(confidence: float = 0.91) -> dict:
    return {
        "engine": "paddleocr",
        "status": "ok",
        "requested_profile": "v6_medium",
        "selected_profile": "paddleocr_default",
        "selected_models": {"det": "PP-OCRv6_medium_det"},
        "items": [
            {
                "id": "ocr-text-0000",
                "text": "某某有限公司",
                "confidence": confidence,
                "polygon": [[10, 20], [110, 20], [110, 50], [10, 50]],
                "bbox": {"x": 10, "y": 20, "w": 100, "h": 30},
            }
        ],
    }


def test_ocr_worker_result_normalizes_and_validates_against_schema() -> None:
    result = normalize_ocr_worker_result(
        _worker_payload(),
        document_id="doc-a",
        page_number=3,
        image_sha256="a" * 64,
    )

    schema = json.loads(Path("schemas/ocr_evidence.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(result, schema)
    assert result["items"][0]["evidence_id"] == "doc-a:page-3:ocr-text-0000"
    assert result["items"][0]["review_status"] == "ok"
    assert result["requires_human_review"] is False


def test_low_confidence_is_forced_to_human_review() -> None:
    result = normalize_ocr_worker_result(
        _worker_payload(confidence=0.4),
        document_id="doc-a",
        page_number=1,
        image_sha256="b" * 64,
    )

    assert result["items"][0]["review_status"] == "low-confidence"
    assert result["requires_human_review"] is True


def test_failed_worker_is_explicit_not_an_empty_success() -> None:
    result = normalize_ocr_worker_result(
        {
            "engine": "paddleocr",
            "status": "failed",
            "error": "model files unavailable",
            "items": [],
        },
        document_id="doc-a",
        page_number=1,
        image_sha256="c" * 64,
    )

    assert result["status"] == "failed"
    assert result["requires_human_review"] is True
    assert result["error"] == "model files unavailable"


@pytest.mark.parametrize(
    "field,value",
    [("confidence", 1.1), ("confidence", -0.1), ("bbox_width", 0)],
)
def test_invalid_evidence_is_rejected(field: str, value: float) -> None:
    payload = _worker_payload()
    if field == "confidence":
        payload["items"][0]["confidence"] = value
    else:
        payload["items"][0]["bbox"]["w"] = value

    with pytest.raises(VisionContractError):
        normalize_ocr_worker_result(
            payload,
            document_id="doc-a",
            page_number=1,
            image_sha256="d" * 64,
        )
