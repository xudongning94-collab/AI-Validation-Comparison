from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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
