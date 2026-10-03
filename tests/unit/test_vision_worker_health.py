from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_health_module():
    path = ROOT / "workers" / "vision_worker_health.py"
    spec = importlib.util.spec_from_file_location("vision_worker_health", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(root: Path, content: bytes, digest: str) -> None:
    detection = root / "detection" / "model.bin"
    recognition = root / "recognition" / "model.bin"
    detection.parent.mkdir(parents=True)
    recognition.parent.mkdir(parents=True)
    detection.write_bytes(content)
    recognition.write_bytes(content)
    (root / "model_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0.0",
                "models": [
                    {
                        "id": "detector",
                        "kind": "detection",
                        "model_name": "detector-name",
                        "relative_directory": "detection",
                        "files": [{"relative_path": "model.bin", "sha256": digest}],
                    },
                    {
                        "id": "recognizer",
                        "kind": "recognition",
                        "model_name": "recognizer-name",
                        "relative_directory": "recognition",
                        "files": [{"relative_path": "model.bin", "sha256": digest}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_offline_model_manifest_verifies_relative_files_and_hashes(tmp_path: Path) -> None:
    module = _load_health_module()
    content = b"offline-model"
    _write_manifest(tmp_path, content, hashlib.sha256(content).hexdigest())

    result = module._offline_models(tmp_path)

    assert result == {"configured": True, "manifest_valid": True, "model_count": 2}


def test_offline_model_manifest_rejects_hash_mismatch_without_leaking_paths(tmp_path: Path) -> None:
    module = _load_health_module()
    _write_manifest(tmp_path, b"offline-model", "0" * 64)

    result = module._offline_models(tmp_path)

    assert result == {"configured": True, "manifest_valid": False, "model_count": 0}
    assert str(tmp_path) not in json.dumps(result)

    (tmp_path / "model_manifest.json").write_text("[]", encoding="utf-8")
    assert module._offline_models(tmp_path)["manifest_valid"] is False


def test_offline_model_manifest_rejects_undeclared_files(tmp_path: Path) -> None:
    module = _load_health_module()
    content = b"offline-model"
    _write_manifest(tmp_path, content, hashlib.sha256(content).hexdigest())
    (tmp_path / "detection" / "unexpected.bin").write_bytes(b"not-declared")

    assert module._offline_models(tmp_path) == {
        "configured": True,
        "manifest_valid": False,
        "model_count": 0,
    }
