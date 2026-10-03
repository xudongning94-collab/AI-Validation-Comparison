from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from bid_compare_agent.vision import (
    SignatureCalibrationError,
    bbox_iou,
    calibrate_signature_candidates,
)


ROOT = Path(__file__).resolve().parents[2]


def _annotation(annotation_id: str, kind: str, x: int) -> dict:
    return {
        "id": annotation_id,
        "kind": kind,
        "bbox": {"x": x, "y": 10, "w": 20, "h": 20},
        "ignore": False,
    }


def _candidate(candidate_id: str, kind: str, x: int, confidence: float, page: int) -> dict:
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "page_number": page,
        "bbox": {"x": x, "y": 10, "w": 20, "h": 20},
        "confidence": confidence,
    }


def _manifest(tmp_path: Path, *, include_validation: bool = True) -> dict:
    for name in ("cal-positive.png", "cal-negative.png", "validation.png"):
        (tmp_path / name).write_bytes(f"image:{name}".encode())
    samples = [
        {
            "id": "cal-positive",
            "document_group_id": "calibration-document",
            "split": "calibration",
            "image": "cal-positive.png",
            "page_number": 1,
            "signature_rois": [[0, 0, 100, 100]],
            "annotations": [
                _annotation("cal-signature", "signature", 10),
                _annotation("cal-seal", "seal", 50),
            ],
        },
        {
            "id": "cal-negative",
            "document_group_id": "calibration-document",
            "split": "calibration",
            "image": "cal-negative.png",
            "page_number": 2,
            "signature_rois": [[0, 0, 100, 100]],
            "annotations": [],
        },
    ]
    if include_validation:
        samples.append(
            {
                "id": "validation",
                "document_group_id": "validation-document",
                "split": "validation",
                "image": "validation.png",
                "page_number": 3,
                "signature_rois": [[0, 0, 100, 100]],
                "annotations": [
                    _annotation("validation-signature", "signature", 10),
                    _annotation("validation-seal", "seal", 50),
                ],
            }
        )
    return {
        "schema_version": "1.1.0",
        "calibration_id": "unit-calibration",
        "privacy": {"include_source_paths": False},
        "samples": samples,
    }


def _detector(path: Path, *, page_number: int, signature_rois: list[tuple[int, ...]]) -> dict:
    assert signature_rois == [(0, 0, 100, 100)]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.name == "cal-positive.png":
        candidates = [
            _candidate("signature-match", "signature", 10, 0.60, page_number),
            _candidate("seal-match", "seal", 50, 0.80, page_number),
            _candidate("seal-low-fp", "seal", 80, 0.40, page_number),
        ]
    elif path.name == "cal-negative.png":
        candidates = [
            _candidate("signature-low-fp", "signature", 70, 0.40, page_number),
        ]
    else:
        candidates = [
            _candidate("validation-signature-match", "signature", 10, 0.55, page_number),
            _candidate("validation-seal-match", "seal", 50, 0.75, page_number),
        ]
    return {
        "status": "ok",
        "image_sha256": digest,
        "candidates": candidates,
    }


def _config() -> dict:
    return {
        "signature_calibration": {
            "iou_threshold": 0.30,
            "minimum_recall": 0.85,
            "confidence_thresholds": [0.30, 0.50, 0.70],
            "required_kinds": ["signature", "seal"],
        }
    }


def test_calibration_selects_thresholds_and_validates_without_leaking_paths(tmp_path: Path):
    result = calibrate_signature_candidates(
        _manifest(tmp_path),
        manifest_dir=tmp_path,
        config=_config(),
        detector=_detector,
    )

    assert result["status"] == "validated"
    assert result["recommended_thresholds"]["signature"]["confidence_threshold"] == 0.5
    assert result["recommended_thresholds"]["seal"]["confidence_threshold"] == 0.7
    assert result["calibration_metrics"]["signature"]["false_positives"] == 0
    assert result["validation_metrics"]["signature"]["miss_rate"] == 0.0
    assert result["integrity"]["inputs_unchanged"] is True
    assert result["dataset"]["document_group_count"] == 2
    assert result["dataset"]["calibration_document_group_count"] == 1
    assert result["dataset"]["validation_document_group_count"] == 1
    encoded = json.dumps(result, ensure_ascii=False)
    assert str(tmp_path) not in encoded
    assert ".png" not in encoded

    schema = json.loads(
        (ROOT / "schemas" / "signature_calibration.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(result)


def test_calibration_without_validation_is_explicitly_calibration_only(tmp_path: Path):
    result = calibrate_signature_candidates(
        _manifest(tmp_path, include_validation=False),
        manifest_dir=tmp_path,
        config=_config(),
        detector=_detector,
    )

    assert result["status"] == "calibration_only"
    assert result["dataset"]["validation_sample_count"] == 0
    assert result["validation_metrics"] == {"signature": None, "seal": None}


def test_worker_hash_mismatch_is_rejected(tmp_path: Path):
    def wrong_hash_detector(path: Path, **kwargs) -> dict:
        result = _detector(path, **kwargs)
        result["image_sha256"] = "0" * 64
        return result

    with pytest.raises(SignatureCalibrationError, match="does not match"):
        calibrate_signature_candidates(
            _manifest(tmp_path),
            manifest_dir=tmp_path,
            config=_config(),
            detector=wrong_hash_detector,
        )


def test_manifest_requires_private_output_and_existing_images(tmp_path: Path):
    manifest = _manifest(tmp_path)
    manifest["privacy"]["include_source_paths"] = True
    with pytest.raises(SignatureCalibrationError, match="include_source_paths"):
        calibrate_signature_candidates(
            manifest,
            manifest_dir=tmp_path,
            config=_config(),
            detector=_detector,
        )


def test_manifest_rejects_document_group_split_leakage(tmp_path: Path):
    manifest = _manifest(tmp_path)
    manifest["samples"][-1]["document_group_id"] = "calibration-document"

    with pytest.raises(SignatureCalibrationError, match="document group.*both"):
        calibrate_signature_candidates(
            manifest,
            manifest_dir=tmp_path,
            config=_config(),
            detector=_detector,
        )


def test_manifest_requires_document_group_id(tmp_path: Path):
    manifest = _manifest(tmp_path)
    del manifest["samples"][0]["document_group_id"]

    with pytest.raises(SignatureCalibrationError, match="document_group_id"):
        calibrate_signature_candidates(
            manifest,
            manifest_dir=tmp_path,
            config=_config(),
            detector=_detector,
        )


def test_bbox_iou_handles_overlap_and_disjoint_boxes() -> None:
    left = {"x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0}
    assert bbox_iou(left, left) == 1.0
    assert bbox_iou(left, {"x": 20.0, "y": 20.0, "w": 5.0, "h": 5.0}) == 0.0
