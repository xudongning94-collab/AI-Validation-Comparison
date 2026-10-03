from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.vision import (
    SignatureCalibrationError,
    VisionWorkerClient,
    VisionWorkerUnavailable,
    calibrate_signature_candidates,
    load_signature_calibration_manifest,
)


def _load_detector(worker_config_path: Path):
    payload = _load_config(worker_config_path)
    worker_config = payload.get("vision_worker")
    if not isinstance(worker_config, dict):
        raise SignatureCalibrationError("worker config must contain a vision_worker object")
    if str(worker_config.get("required_python")) != "3.12":
        raise SignatureCalibrationError("vision worker required_python must be 3.12")
    environment_name = str(
        worker_config.get("python_environment_variable")
        or "BID_COMPARE_VISION_PYTHON"
    )
    executable = os.environ.get(environment_name) or worker_config.get("python_executable")
    model_environment_name = str(
        worker_config.get("offline_model_directory_environment_variable")
        or "BID_COMPARE_PADDLEOCR_MODEL_DIR"
    )
    model_directory = os.environ.get(model_environment_name) or worker_config.get(
        "offline_model_directory"
    )
    client = VisionWorkerClient(
        executable,
        repo_root=ROOT,
        offline_model_directory=model_directory,
        health_timeout_seconds=int(worker_config.get("health_timeout_seconds", 20)),
        task_timeout_seconds=int(worker_config.get("task_timeout_seconds", 120)),
        seal_preferred_min_dimension_ratio=float(
            worker_config.get("seal_preferred_min_dimension_ratio", 0.06)
        ),
        seal_preferred_max_area_ratio=float(
            worker_config.get("seal_preferred_max_area_ratio", 0.04)
        ),
    )
    try:
        client.require_signature_capability()
    except (TypeError, ValueError, VisionWorkerUnavailable) as exc:
        raise SignatureCalibrationError(str(exc)) from exc
    return client.detect_signature_candidates


def _load_config(path: Path) -> dict:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SignatureCalibrationError(f"cannot read calibration config: {exc}") from exc
    if not isinstance(payload, dict):
        raise SignatureCalibrationError("calibration config must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="使用本地人工标注签署页校准签字/印章候选阈值"
    )
    parser.add_argument("manifest", help="本地标注 manifest JSON")
    parser.add_argument(
        "--config",
        default=str(ROOT / "configs" / "signature_calibration.yaml"),
        help="校准阈值扫描配置",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output/signature-calibration/report.json",
    )
    parser.add_argument(
        "--worker-config",
        type=Path,
        default=ROOT / "configs" / "vision_worker.yaml",
        help="isolated Python 3.12 vision-worker configuration",
    )
    args = parser.parse_args()

    try:
        manifest, manifest_dir = load_signature_calibration_manifest(args.manifest)
        result = calibrate_signature_candidates(
            manifest,
            manifest_dir=manifest_dir,
            config=_load_config(Path(args.config)),
            detector=_load_detector(args.worker_config),
        )
    except SignatureCalibrationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"OK calibration={result['calibration_id']} status={result['status']} "
        f"samples={result['dataset']['sample_count']}"
    )
    print(f"OUTPUT {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
