#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "signature_review_package_manifest.schema.json"
TEMPLATE = ROOT / "scripts" / "templates" / "signature_review.html"


def _validate_relative_image(value: str, field: str) -> None:
    if "\\" in value:
        raise ValueError(f"{field} must use forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or "://" in value:
        raise ValueError(f"{field} must be a local relative path")


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    seal_ids = [item["page_id"] for item in payload["seal_pages"]]
    seal_numbers = [item["page_number"] for item in payload["seal_pages"]]
    field_ids = [item["field_id"] for item in payload["signature_fields"]]
    if len(seal_ids) != len(set(seal_ids)):
        raise ValueError("seal page IDs must be unique")
    if len(seal_numbers) != len(set(seal_numbers)):
        raise ValueError("seal page numbers must be unique")
    if seal_numbers and set(seal_numbers) != set(range(1, len(seal_numbers) + 1)):
        raise ValueError("seal page numbers must cover 1..N without gaps")
    if len(field_ids) != len(set(field_ids)):
        raise ValueError("signature field IDs must be unique")
    for index, item in enumerate(payload["seal_pages"]):
        _validate_relative_image(item["image"], f"seal_pages[{index}].image")
    for index, item in enumerate(payload["signature_fields"]):
        _validate_relative_image(item["image"], f"signature_fields[{index}].image")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local full-page seal and two-stage signature review UI."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        payload = _load_manifest(args.manifest)
        template = TEMPLATE.read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
        print(f"ERROR {exc}")
        return 2

    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    serialized = serialized.replace("</", "<\\/")
    html = template.replace("__REVIEW_DATA__", serialized)
    if html == template:
        print("ERROR review template data marker is missing")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.html").write_text(html, encoding="utf-8")
    (args.output_dir / "review-data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    export_template = {
        "schema_version": "1.0.0",
        "document_group_id": payload["document_group_id"],
        "expected_seal_page_count": len(payload["seal_pages"]),
        "expected_signature_field_count": len(payload["signature_fields"]),
        "seal_pages": {
            item["page_id"]: {
                "page_number": item["page_number"],
                "status": "unreviewed",
                "missed_seal_boxes": [],
            }
            for item in payload["seal_pages"]
        },
        "signature_fields": {
            item["field_id"]: {
                "page_number": item["page_number"],
                "field_status": "unreviewed",
                "handwritten_status": "unreviewed",
            }
            for item in payload["signature_fields"]
        },
    }
    (args.output_dir / "review-export-template.json").write_text(
        json.dumps(export_template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "SIGNATURE_REVIEW_PACKAGE "
        f"group={payload['document_group_id']} "
        f"seal_pages={len(payload['seal_pages'])} "
        f"signature_fields={len(payload['signature_fields'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
