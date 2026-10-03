#!/usr/bin/env python3
"""Build a hash manifest for already staged local PaddleOCR model directories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKERS_DIRECTORY = ROOT / "workers"
if str(WORKERS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(WORKERS_DIRECTORY))

from offline_models import ModelManifestError, build_manifest, verify_model_package


def _model(value: str) -> tuple[str, str, str, str]:
    parts = value.split("=", 3)
    if len(parts) != 4 or not all(parts):
        raise argparse.ArgumentTypeError("model must be KIND=ID=MODEL_NAME=DIRECTORY")
    kind, model_id, model_name, directory = parts
    return model_id, kind, model_name, directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Offline model package root")
    parser.add_argument(
        "--model",
        action="append",
        type=_model,
        required=True,
        help="KIND=ID=MODEL_NAME=DIRECTORY (repeat for detection and recognition)",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        payload = build_manifest(root, args.model)
        target = root / "model_manifest.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verify_model_package(root)
    except (ModelManifestError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"schema_version": "1.0.0", "status": "ok", "model_count": len(args.model)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
