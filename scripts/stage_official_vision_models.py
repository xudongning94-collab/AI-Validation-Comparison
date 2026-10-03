#!/usr/bin/env python3
"""Explicitly download, verify, and stage the pinned PaddleOCR model pair."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKERS_DIRECTORY = ROOT / "workers"
if str(WORKERS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(WORKERS_DIRECTORY))

from offline_models import build_manifest, sha256_file, verify_model_package


MODEL_SOURCE_ROOT = (
    "https://paddle-model-ecology.bj.bcebos.com/"
    "paddlex/official_inference_model/paddle3.0.0"
)
MODELS = (
    {
        "id": "paddleocr-v5-server-det",
        "kind": "detection",
        "name": "PP-OCRv5_server_det",
        "archive": "PP-OCRv5_server_det_infer.tar",
    },
    {
        "id": "paddleocr-v5-server-rec",
        "kind": "recognition",
        "name": "PP-OCRv5_server_rec",
        "archive": "PP-OCRv5_server_rec_infer.tar",
    },
)


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "bid-compare-agent-model-stager/1"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)


def _extract_model(archive: Path, destination: Path) -> Path:
    extract_root = destination / "extracted"
    extract_root.mkdir(parents=True)
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            target = (extract_root / member.name).resolve()
            try:
                target.relative_to(extract_root.resolve())
            except ValueError as exc:
                raise ValueError("model archive contains a path outside its root") from exc
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("model archive contains an unsupported link or device")
        bundle.extractall(extract_root, filter="data")
    candidates = sorted(
        path.parent for path in extract_root.rglob("inference.json") if path.parent.is_dir()
    )
    if len(candidates) != 1:
        raise ValueError("model archive must contain exactly one inference model directory")
    if not (candidates[0] / "inference.pdiparams").is_file():
        raise ValueError("model archive is missing inference.pdiparams")
    return candidates[0]


def _publish_package(package_root: Path, destination: Path) -> None:
    """Copy into a fresh destination so it inherits the destination parent ACL."""
    shutil.copytree(package_root, destination)


def stage_models(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("destination already exists; refusing to overwrite staged models")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vision-model-stage-", dir=destination.parent) as temporary:
        temporary_root = Path(temporary)
        package_root = temporary_root / "package"
        package_root.mkdir()
        manifest_models: list[tuple[str, str, str, Path]] = []
        provenance: list[dict[str, str]] = []
        for model in MODELS:
            url = f"{MODEL_SOURCE_ROOT}/{model['archive']}"
            archive = temporary_root / model["archive"]
            _download(url, archive)
            extracted = _extract_model(archive, temporary_root / f"extract-{model['kind']}")
            final_directory = package_root / model["kind"]
            shutil.move(str(extracted), final_directory)
            manifest_models.append(
                (model["id"], model["kind"], model["name"], final_directory)
            )
            provenance.append(
                {
                    "model_id": model["id"],
                    "source_url": url,
                    "archive_sha256": sha256_file(archive),
                }
            )

        manifest = build_manifest(package_root, manifest_models)
        (package_root / "model_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (package_root / "model_sources.json").write_text(
            json.dumps({"schema_version": "1.0.0", "sources": provenance}, indent=2) + "\n",
            encoding="utf-8",
        )
        package = verify_model_package(package_root)
        _publish_package(package_root, destination)
    return {
        "schema_version": "1.0.0",
        "status": "ok",
        "model_count": len(package.models),
        "manifest_valid": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        type=Path,
        default=ROOT / "workers" / "models",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required acknowledgement that official model archives will be downloaded.",
    )
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("explicit --allow-network is required")
    try:
        result = stage_models(args.destination)
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(json.dumps({"schema_version": "1.0.0", "status": "failed", "error": str(exc)}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
