from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = ROOT / "workers" / "offline_models.py"
    spec = importlib.util.spec_from_file_location("offline_models", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_builder_and_verifier_cover_every_staged_file(tmp_path: Path) -> None:
    module = _load_module()
    detection = tmp_path / "detection"
    recognition = tmp_path / "recognition"
    detection.mkdir()
    recognition.mkdir()
    (detection / "inference.json").write_text("det", encoding="utf-8")
    (detection / "inference.pdiparams").write_bytes(b"det-weights")
    (recognition / "inference.json").write_text("rec", encoding="utf-8")
    payload = module.build_manifest(
        tmp_path,
        [
            ("detector", "detection", "det-model", detection),
            ("recognizer", "recognition", "rec-model", recognition),
        ],
    )
    (tmp_path / "model_manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    schema = json.loads((ROOT / "schemas" / "vision_model_manifest.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    package = module.verify_model_package(tmp_path)

    assert [model.kind for model in package.models] == ["detection", "recognition"]
    assert package.require("detection").model_name == "det-model"
    assert len(package.require("detection").files) == 2


def test_manifest_rejects_parent_traversal(tmp_path: Path) -> None:
    module = _load_module()
    (tmp_path / "model_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0.0",
                "models": [
                    {
                        "id": "detector",
                        "kind": "detection",
                        "model_name": "det-model",
                        "relative_directory": "../outside",
                        "files": [{"relative_path": "model.bin", "sha256": "0" * 64}],
                    },
                    {
                        "id": "recognizer",
                        "kind": "recognition",
                        "model_name": "rec-model",
                        "relative_directory": "recognition",
                        "files": [{"relative_path": "model.bin", "sha256": "0" * 64}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(module.ModelManifestError, match="inside"):
        module.verify_model_package(tmp_path)


def test_manifest_rejects_non_ascii_runtime_paths(tmp_path: Path) -> None:
    module = _load_module()
    with pytest.raises(module.ModelManifestError, match="ASCII"):
        module._relative_path("检测/inference.json", "relative_path")
