from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def _load_worker_module():
    path = ROOT / "workers" / "detect_signature_candidates_cv.py"
    spec = importlib.util.spec_from_file_location("signature_candidate_worker", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_failure_or_disabled_result_matches_stable_schema(tmp_path) -> None:
    worker = _load_worker_module()
    result = worker.detect_candidates(
        tmp_path / "missing.png",
        page_number=1,
        signature_rois=[],
    )
    schema = json.loads(
        (ROOT / "schemas" / "signature_candidates.schema.json").read_text(encoding="utf-8")
    )

    Draft202012Validator(schema).validate(result)
    assert result["status"] in {"failed", "disabled"}
    assert result["candidates"] == []
    assert result["count"] == 0
    assert result["metadata"]["authenticity_check"] is False


def test_worker_decodes_unicode_image_path_via_python_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    worker = _load_worker_module()
    image_path = tmp_path / "真实签章页.png"
    image_path.write_bytes(b"encoded-image")
    decoded = object()
    calls = {}

    def frombuffer(payload, *, dtype):
        calls["payload"] = payload
        calls["dtype"] = dtype
        return "encoded-array"

    def imdecode(payload, mode):
        calls["decoded_payload"] = payload
        calls["mode"] = mode
        return decoded

    fake_numpy = SimpleNamespace(uint8="uint8", frombuffer=frombuffer)
    fake_cv2 = SimpleNamespace(IMREAD_COLOR=7, imdecode=imdecode)
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    assert worker._read_image(image_path) is decoded
    assert calls == {
        "payload": b"encoded-image",
        "dtype": "uint8",
        "decoded_payload": "encoded-array",
        "mode": 7,
    }


def _seal_candidate(
    candidate_id: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    confidence: float = 0.8,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "kind": "seal",
        "page_number": 1,
        "bbox": {"x": x, "y": y, "w": w, "h": h},
        "confidence": confidence,
        "recognized_text": None,
        "quality_flags": [],
        "detector": "test-contour",
        "features": {
            "color": "red",
            "area": w * h * 0.4,
            "aspect": min(w, h) / max(w, h),
            "circularity": 0.5,
            "fill_ratio": 0.4,
        },
    }


def test_worker_merges_nearby_same_color_seal_fragments() -> None:
    worker = _load_worker_module()
    candidates = [
        _seal_candidate("fragment-1", x=100, y=100, w=35, h=30),
        _seal_candidate("fragment-2", x=142, y=108, w=30, h=34),
        _seal_candidate("fragment-3", x=115, y=150, w=40, h=30),
    ]

    merged = worker._consolidate_seal_candidates(
        candidates,
        page_number=1,
        width=1000,
        height=1400,
    )

    assert len(merged) == 1
    assert merged[0]["bbox"] == {"x": 100.0, "y": 100.0, "w": 72.0, "h": 80.0}
    assert merged[0]["features"]["component_count"] == 3
    assert merged[0]["detector"] == "opencv-hsv-red-component-cluster-v3"


def test_worker_filters_elongated_color_bars_after_consolidation() -> None:
    worker = _load_worker_module()
    candidates = [
        _seal_candidate("web-header", x=100, y=100, w=500, h=25, confidence=0.95),
        _seal_candidate("round-seal", x=200, y=300, w=100, h=105, confidence=0.8),
    ]

    consolidated = worker._consolidate_seal_candidates(
        candidates,
        page_number=1,
        width=1000,
        height=1400,
    )

    assert [item["candidate_id"] for item in consolidated] == ["seal-1-red-0000"]
    assert consolidated[0]["bbox"] == {"x": 200.0, "y": 300.0, "w": 100.0, "h": 105.0}


def test_worker_drops_elongated_components_before_they_bridge_fragments() -> None:
    worker = _load_worker_module()
    candidates = [
        _seal_candidate("fragment-1", x=100, y=300, w=40, h=40),
        _seal_candidate("fragment-2", x=148, y=305, w=40, h=42),
        _seal_candidate("vertical-border", x=80, y=50, w=20, h=400),
        _seal_candidate("horizontal-border", x=80, y=40, w=300, h=20),
    ]

    consolidated = worker._consolidate_seal_candidates(
        candidates,
        page_number=1,
        width=1000,
        height=1400,
    )

    assert len(consolidated) == 1
    assert consolidated[0]["bbox"] == {
        "x": 100.0,
        "y": 300.0,
        "w": 88.0,
        "h": 47.0,
    }
    assert consolidated[0]["features"]["component_count"] == 2


def test_worker_penalizes_implausible_seal_scale_without_dropping_candidates() -> None:
    worker = _load_worker_module()
    candidates = [
        _seal_candidate(
            "tiny-color-icon",
            x=100,
            y=100,
            w=20,
            h=20,
            confidence=0.95,
        ),
        _seal_candidate(
            "normal-seal",
            x=300,
            y=300,
            w=100,
            h=105,
            confidence=0.80,
        ),
        _seal_candidate(
            "large-color-panel",
            x=100,
            y=700,
            w=500,
            h=400,
            confidence=0.90,
        ),
    ]

    consolidated = worker._consolidate_seal_candidates(
        candidates,
        page_number=1,
        width=1000,
        height=1400,
    )

    by_y = {item["bbox"]["y"]: item for item in consolidated}
    assert len(consolidated) == 3
    assert by_y[100.0]["confidence"] == 0.3167
    assert by_y[300.0]["confidence"] == 0.80
    assert by_y[700.0]["confidence"] == 0.252
    assert by_y[100.0]["features"]["scale_confidence_factor"] == 0.3333
    assert by_y[300.0]["features"]["scale_confidence_factor"] == 1.0
    assert by_y[700.0]["features"]["scale_confidence_factor"] == 0.28

    relaxed = worker._consolidate_seal_candidates(
        candidates,
        page_number=1,
        width=1000,
        height=1400,
        preferred_min_dimension_ratio=0.02,
        preferred_max_area_ratio=0.20,
    )
    relaxed_by_y = {item["bbox"]["y"]: item for item in relaxed}
    assert relaxed_by_y[100.0]["confidence"] == 0.95
    assert relaxed_by_y[300.0]["confidence"] == 0.80
    assert relaxed_by_y[700.0]["confidence"] == 0.90
