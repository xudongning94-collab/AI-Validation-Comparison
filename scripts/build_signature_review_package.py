#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema
from PIL import Image, ImageOps


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


def _write_review_jpeg(
    source_path: Path, target_path: Path, *, quality: int = 82
) -> None:
    with Image.open(source_path) as source:
        source.load()
        image = ImageOps.exif_transpose(source)
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(target_path, format="JPEG", quality=quality, optimize=True)


def _bundle_review_images(
    payload: dict[str, Any], output_dir: Path
) -> dict[str, Any]:
    bundled = copy.deepcopy(payload)
    package_parent = output_dir.resolve().parent
    cache: dict[Path, str] = {}
    for collection_name in ("seal_pages", "signature_fields"):
        for index, item in enumerate(bundled[collection_name]):
            relative = PurePosixPath(item["image"])
            resolved = (output_dir / Path(*relative.parts)).resolve()
            try:
                resolved.relative_to(package_parent)
            except ValueError as exc:
                raise ValueError(
                    f"{collection_name}[{index}].image must stay inside "
                    "the output directory parent"
                ) from exc
            if not resolved.is_file():
                raise ValueError(
                    f"missing image for {collection_name}[{index}].image"
                )
            bundled_path = cache.get(resolved)
            if bundled_path is None:
                bundled_path = f"review-assets/image-{len(cache) + 1:04d}.jpg"
                _write_review_jpeg(resolved, output_dir / bundled_path)
                cache[resolved] = bundled_path
            item["image"] = bundled_path
    return bundled


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local full-page seal and two-stage signature review UI."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--bundle-images",
        action="store_true",
        help="write compressed page images inside the review package",
    )
    args = parser.parse_args()

    try:
        payload = _load_manifest(args.manifest)
        template = TEMPLATE.read_text(encoding="utf-8")
        package_payload = (
            _bundle_review_images(payload, args.output_dir)
            if args.bundle_images
            else payload
        )
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
        print(f"ERROR {exc}")
        return 2

    serialized = json.dumps(package_payload, ensure_ascii=False, separators=(",", ":"))
    serialized = serialized.replace("</", "<\\/")
    html = template.replace("__REVIEW_DATA__", serialized)
    if html == template:
        print("ERROR review template data marker is missing")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.html").write_text(html, encoding="utf-8")
    (args.output_dir / "review-data.json").write_text(
        json.dumps(package_payload, ensure_ascii=False, indent=2), encoding="utf-8"
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
