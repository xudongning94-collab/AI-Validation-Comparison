from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def _load_worker():
    workers = ROOT / "workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))
    path = workers / "run_paddleocr.py"
    spec = importlib.util.spec_from_file_location("run_paddleocr", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _models(module, root: Path) -> None:
    from offline_models import build_manifest

    detection = root / "detection"
    recognition = root / "recognition"
    detection.mkdir(parents=True)
    recognition.mkdir(parents=True)
    (detection / "inference.json").write_text("det", encoding="utf-8")
    (recognition / "inference.json").write_text("rec", encoding="utf-8")
    payload = build_manifest(
        root,
        [
            ("detector-id", "detection", "detector-name", detection),
            ("recognizer-id", "recognition", "recognizer-name", recognition),
        ],
    )
    (root / "model_manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_worker_uses_only_verified_local_models_and_normalizes_geometry(tmp_path: Path) -> None:
    module = _load_worker()
    model_root = tmp_path / "models"
    _models(module, model_root)
    image = tmp_path / "page.png"
    image.write_bytes(b"stable-image")
    observed: dict = {}

    class FakeArray:
        def __init__(self, value):
            self.value = value

        def tolist(self):
            return self.value

    class FakeResult:
        json = {
            "res": {
                "rec_texts": ["供应商名称"],
                "rec_scores": [0.91],
                "rec_polys": [FakeArray([[10, 20], [110, 20], [110, 50], [10, 50]])],
                "rec_boxes": [[10, 20, 110, 50]],
            }
        }

    class FakeEngine:
        def predict(self, source, **kwargs):
            observed["source"] = source
            observed["inference_directory"] = Path.cwd()
            observed["predict"] = kwargs
            return [FakeResult()]

    def factory(**kwargs):
        observed["constructor"] = kwargs
        return FakeEngine()

    original_directory = Path.cwd()
    result = module.run_ocr(
        image,
        page_number=3,
        model_directory=model_root,
        engine_factory=factory,
        image_loader=lambda _path: "decoded-image",
    )

    schema = json.loads((ROOT / "schemas" / "ocr_worker_result.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)
    assert result["status"] == "ok"
    assert result["selected_models"] == {"detection": "detector-id", "recognition": "recognizer-id"}
    assert result["items"][0]["bbox"] == {"x": 10.0, "y": 20.0, "w": 100.0, "h": 30.0}
    assert observed["constructor"]["text_detection_model_dir"] == "detection"
    assert observed["constructor"]["text_recognition_model_dir"] == "recognition"
    assert observed["source"] == "decoded-image"
    assert observed["inference_directory"] == model_root.resolve()
    assert Path.cwd() == original_directory
    assert observed["constructor"]["use_doc_orientation_classify"] is False
    assert observed["constructor"]["use_doc_unwarping"] is False
    assert observed["constructor"]["use_textline_orientation"] is False
    assert observed["constructor"]["enable_mkldnn"] is False
    assert observed["predict"]["use_doc_orientation_classify"] is False
    assert os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "True"
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_worker_rejects_changed_model_before_engine_creation(tmp_path: Path) -> None:
    module = _load_worker()
    model_root = tmp_path / "models"
    _models(module, model_root)
    (model_root / "detection" / "inference.json").write_text("changed", encoding="utf-8")
    image = tmp_path / "page.png"
    image.write_bytes(b"stable-image")
    called = False

    def factory(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not instantiate engine")

    result = module.run_ocr(
        image,
        page_number=1,
        model_directory=model_root,
        engine_factory=factory,
        image_loader=lambda _path: "decoded-image",
    )

    assert result["status"] == "disabled"
    assert result["error"] == "Offline model package failed integrity validation."
    assert called is False
    assert str(model_root) not in json.dumps(result)
