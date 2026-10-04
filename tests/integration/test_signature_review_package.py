from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]


def test_review_package_builder_generates_local_ui_without_absolute_paths(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "review"
    rendered = tmp_path / "rendered"
    rendered.mkdir()
    for name in ("page-0001.png", "page-0002.png", "signature-page.png"):
        (rendered / name).write_bytes(b"not-a-real-image")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "document_group_id": "group-a",
                "seal_pages": [
                    {
                        "page_id": "page-0001",
                        "page_number": 1,
                        "image": "../rendered/page-0001.png",
                    },
                    {
                        "page_id": "page-0002",
                        "page_number": 2,
                        "image": "../rendered/page-0002.png",
                    },
                ],
                "signature_fields": [
                    {
                        "field_id": "field-1",
                        "page_number": 1,
                        "image": "../rendered/signature-page.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_signature_review_package.py"),
            str(manifest),
            "--output-dir",
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
    html = (output / "index.html").read_text(encoding="utf-8")
    data = json.loads((output / "review-data.json").read_text(encoding="utf-8"))
    export_template = json.loads(
        (output / "review-export-template.json").read_text(encoding="utf-8")
    )
    export_schema = json.loads(
        (ROOT / "schemas" / "signature_review_export.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(export_template, export_schema)
    assert data["document_group_id"] == "group-a"
    assert len(data["seal_pages"]) == 2
    assert len(data["signature_fields"]) == 1
    assert export_template["expected_seal_page_count"] == 2
    assert export_template["expected_signature_field_count"] == 1
    assert "no_missed_seal" in html
    assert "handwritten_present" in html
    assert str(tmp_path) not in html

    server_check = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "serve_signature_review.py"),
            str(output),
            "--check-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert server_check.returncode == 0, server_check.stderr
    assert "url_path=/review/index.html" in server_check.stdout
    assert "images=3" in server_check.stdout
    assert str(tmp_path) not in server_check.stdout
