from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.vision.worker_client import VisionWorkerClient


def _load_config(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("vision_worker"), dict):
        raise ValueError("config must contain a vision_worker object")
    return payload["vision_worker"]


def build_client(config: dict) -> VisionWorkerClient:
    if str(config.get("required_python")) != "3.12":
        raise ValueError("vision worker required_python must be 3.12")
    environment_name = str(
        config.get("python_environment_variable") or "BID_COMPARE_VISION_PYTHON"
    )
    executable = os.environ.get(environment_name) or config.get("python_executable")
    model_environment_name = str(
        config.get("offline_model_directory_environment_variable")
        or "BID_COMPARE_PADDLEOCR_MODEL_DIR"
    )
    model_directory = os.environ.get(model_environment_name) or config.get(
        "offline_model_directory"
    )
    return VisionWorkerClient(
        executable,
        repo_root=ROOT,
        offline_model_directory=model_directory,
        health_timeout_seconds=int(config.get("health_timeout_seconds", 20)),
        task_timeout_seconds=int(config.get("task_timeout_seconds", 120)),
        seal_preferred_min_dimension_ratio=float(
            config.get("seal_preferred_min_dimension_ratio", 0.06)
        ),
        seal_preferred_max_area_ratio=float(
            config.get("seal_preferred_max_area_ratio", 0.04)
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the isolated Python 3.12 vision worker.")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "vision_worker.yaml",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require",
        choices=("signature", "ocr", "all"),
        default="all",
    )
    args = parser.parse_args()

    try:
        health = build_client(_load_config(args.config)).probe(refresh=True)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    encoded = json.dumps(health, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)

    capabilities = health["capabilities"]
    required = {
        "signature": capabilities["signature_candidates"],
        "ocr": capabilities["ocr"],
        "all": capabilities["signature_candidates"] and capabilities["ocr"],
    }
    return 0 if required[args.require] else 3


if __name__ == "__main__":
    raise SystemExit(main())
