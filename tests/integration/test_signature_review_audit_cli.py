from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]


def test_review_audit_cli_reports_incomplete_coverage_without_leaking_paths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private-review.json"
    output = tmp_path / "review-audit.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "document_group_id": "group-a",
                "expected_seal_page_count": 2,
                "expected_signature_field_count": 1,
                "seal_pages": {
                    "page-0001": {
                        "page_number": 1,
                        "status": "no_missed_seal",
                        "missed_seal_boxes": [],
                    }
                },
                "signature_fields": {
                    "field-1": {
                        "page_number": 1,
                        "field_status": "field_present",
                        "handwritten_status": "handwritten_absent",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_signature_review.py"),
            str(source),
            "--output",
            str(output),
            "--require-complete",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 3
    result = json.loads(output.read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "schemas" / "signature_review_audit.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(result, schema)
    assert result["status"] == "incomplete"
    serialized = json.dumps(result)
    assert str(source) not in serialized
    assert "private-review.json" not in serialized
