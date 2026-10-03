from __future__ import annotations

import importlib.util
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_stager():
    path = ROOT / "scripts" / "stage_official_vision_models.py"
    spec = importlib.util.spec_from_file_location("stage_official_vision_models", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_model_creates_missing_destination_parent(tmp_path: Path) -> None:
    module = _load_stager()
    source = tmp_path / "source" / "model"
    source.mkdir(parents=True)
    (source / "inference.json").write_text("{}", encoding="utf-8")
    (source / "inference.pdiparams").write_bytes(b"weights")
    archive = tmp_path / "model.tar"
    with tarfile.open(archive, "w") as bundle:
        bundle.add(source, arcname="model")

    extracted = module._extract_model(archive, tmp_path / "missing-parent")

    assert extracted.name == "model"
    assert (extracted / "inference.pdiparams").read_bytes() == b"weights"


def test_publish_package_copies_into_fresh_destination(tmp_path: Path) -> None:
    module = _load_stager()
    package = tmp_path / "private-temporary-package"
    package.mkdir()
    (package / "model_manifest.json").write_text("{}", encoding="utf-8")
    destination = tmp_path / "published-models"

    module._publish_package(package, destination)

    assert package.is_dir()
    assert (destination / "model_manifest.json").read_text(encoding="utf-8") == "{}"
