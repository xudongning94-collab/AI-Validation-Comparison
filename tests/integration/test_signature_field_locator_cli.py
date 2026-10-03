from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]


def test_signature_field_locator_cli_keeps_text_and_paths_out_of_result(tmp_path: Path) -> None:
    source = tmp_path / "private-ocr-result.json"
    output = tmp_path / "signature-fields.json"
    source.write_text(
        json.dumps(
            {
                "page_number": 8,
                "canvas": {"width": 1241, "height": 1754},
                "items": [
                    {
                        "id": "anchor",
                        "text": "法定代表人签字或签章：",
                        "confidence": 0.99,
                        "bbox": {"x": 239, "y": 730, "w": 259, "h": 25},
                    },
                    {
                        "id": "seal",
                        "text": "供应商名称（公章）：某公司",
                        "confidence": 0.99,
                        "bbox": {"x": 238, "y": 779, "w": 485, "h": 25},
                    },
                    {
                        "id": "date",
                        "text": "日期：2026年10月3日",
                        "confidence": 0.99,
                        "bbox": {"x": 238, "y": 829, "w": 260, "h": 24},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "locate_signature_fields.py"),
            str(source),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "schemas" / "signature_field_locator.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(result, schema)
    assert result["count"] == 1
    serialized = json.dumps(result, ensure_ascii=False)
    assert "法定代表人" not in serialized
    assert str(source) not in serialized
