from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from PIL import Image

from bid_compare_agent.vision.worker_client import (
    VisionWorkerClient,
    VisionWorkerUnavailable,
)


ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def test_candidate_requirements_are_isolated_from_full_ocr_stack() -> None:
    candidates = (ROOT / "requirements-vision-candidates.txt").read_text(encoding="utf-8")
    full = (ROOT / "requirements-vision-worker.txt").read_text(encoding="utf-8")

    assert "opencv-contrib-python==4.10.0.84" in candidates
    assert "numpy>=1.26,<3" in candidates
    assert "paddleocr" not in candidates
    assert "-r requirements-vision-candidates.txt" in full
    assert "paddleocr==3.7.0" in full
    assert "ujson==5.11.0" in full


def test_bootstrap_requires_explicit_dependency_source() -> None:
    script = (ROOT / "scripts" / "bootstrap_vision_worker.ps1").read_text(
        encoding="utf-8"
    )

    assert "-Wheelhouse or explicit -AllowNetwork" in script
    assert 'ValidateSet("candidates", "all")' in script
    assert 'workers\\vision_worker_health.py' in script
    assert 'scripts\\check_vision_worker.py' not in script


def test_health_worker_reports_real_runtime_without_exposing_executable_path() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "workers" / "vision_worker_health.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    jsonschema.validate(payload, _schema("vision_worker_health.schema.json"))
    assert payload["required_python"] == "3.12"
    assert payload["python_compatible"] is False
    assert payload["status"] == "unavailable"
    assert sys.executable not in result.stdout
    assert payload["capabilities"]["signature_candidates"] is False


def test_missing_worker_python_returns_stable_unavailable_health(tmp_path: Path) -> None:
    missing = tmp_path / "private-runtime" / "python.exe"
    client = VisionWorkerClient(missing, repo_root=ROOT)

    payload = client.probe()

    jsonschema.validate(payload, _schema("vision_worker_health.schema.json"))
    assert payload["status"] == "unavailable"
    assert payload["error"]["code"] == "python_executable_unavailable"
    assert str(missing) not in json.dumps(payload, ensure_ascii=False)
    with pytest.raises(VisionWorkerUnavailable):
        client.require_signature_capability()
    with pytest.raises(ValueError, match="health_timeout_seconds"):
        VisionWorkerClient(missing, repo_root=ROOT, health_timeout_seconds=0)
    with pytest.raises(ValueError, match="seal_preferred_min_dimension_ratio"):
        VisionWorkerClient(
            missing,
            repo_root=ROOT,
            seal_preferred_min_dimension_ratio=0,
        )
    with pytest.raises(ValueError, match="seal_preferred_max_area_ratio"):
        VisionWorkerClient(
            missing,
            repo_root=ROOT,
            seal_preferred_max_area_ratio=1.1,
        )


def test_candidate_worker_runs_through_subprocess_and_keeps_stable_schema(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (120, 160), "white").save(image_path)
    image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    client = VisionWorkerClient(sys.executable, repo_root=ROOT)

    payload = client.detect_signature_candidates(
        image_path,
        page_number=1,
        signature_rois=[(10, 90, 100, 50)],
    )

    jsonschema.validate(payload, _schema("signature_candidates.schema.json"))
    assert payload["status"] in {"ok", "disabled", "failed"}
    assert payload["image_sha256"] == image_hash
    assert payload["metadata"]["signature_roi_count"] == 1


def test_ocr_client_returns_normalized_disabled_evidence_without_models(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (120, 160), "white").save(image_path)
    image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    client = VisionWorkerClient(sys.executable, repo_root=ROOT)

    payload = client.ocr_page(image_path, document_id="doc-1", page_number=1)

    jsonschema.validate(payload, _schema("ocr_evidence.schema.json"))
    assert payload["status"] == "disabled"
    assert payload["image_sha256"] == image_hash
    assert payload["requires_human_review"] is True
    assert payload["error"] == "Offline PaddleOCR model directory is not configured."


def test_calibration_cli_refuses_to_import_worker_into_main_runtime(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "calibrate_signature_candidates.py"
    spec = importlib.util.spec_from_file_location("calibration_cli", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tmp_path / "vision-worker.yaml"
    config.write_text(
        "vision_worker:\n"
        "  python_executable: null\n"
        "  python_environment_variable: BID_COMPARE_TEST_WORKER_MISSING\n"
        "  required_python: '3.12'\n",
        encoding="utf-8",
    )

    with pytest.raises(module.SignatureCalibrationError, match="worker unavailable"):
        module._load_detector(config)


def test_default_worker_config_is_parseable_and_cli_reports_unavailable() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_vision_worker.py"),
            "--require",
            "all",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 3, result.stderr
    payload = json.loads(result.stdout)
    jsonschema.validate(payload, _schema("vision_worker_health.schema.json"))
    assert payload["status"] == "unavailable"
    assert payload["error"]["code"] == "python_executable_unavailable"
