from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def test_signature_calibration_manifest_example_matches_schema() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "signature_calibration_manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    example = json.loads(
        (ROOT / "benchmarks" / "signature_calibration_manifest.example.json").read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator(schema).validate(example)
    assert example["schema_version"] == "1.1.0"
    assert example["privacy"]["include_source_paths"] is False
    assert {sample["split"] for sample in example["samples"]} == {
        "calibration",
        "validation",
    }
    groups_by_split = {
        split: {
            sample["document_group_id"]
            for sample in example["samples"]
            if sample["split"] == split
        }
        for split in ("calibration", "validation")
    }
    assert groups_by_split["calibration"].isdisjoint(
        groups_by_split["validation"]
    )
