from __future__ import annotations

import math
from typing import Any


class ReviewAuditError(ValueError):
    """Raised when a human-review export violates the review contract."""


_ROOT_PROPERTIES = {
    "schema_version",
    "document_group_id",
    "expected_seal_page_count",
    "expected_signature_field_count",
    "seal_pages",
    "signature_fields",
}
_SEAL_PROPERTIES = {"page_number", "status", "missed_seal_boxes"}
_SIGNATURE_PROPERTIES = {"page_number", "field_status", "handwritten_status"}
_SEAL_STATUSES = {"unreviewed", "no_missed_seal", "missed_seal", "uncertain"}
_FIELD_STATUSES = {"unreviewed", "field_present", "field_absent", "uncertain"}
_HANDWRITING_STATUSES = {
    "unreviewed",
    "handwritten_present",
    "handwritten_absent",
    "not_applicable",
    "uncertain",
}


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewAuditError(f"{field} must be an object")
    return value


def _count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReviewAuditError(f"{field} must be a non-negative integer")
    return value


def _page_number(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReviewAuditError(f"{field} must be an integer >= 1")
    return value


def _bbox(value: Any, field: str) -> None:
    box = _mapping(value, field)
    if set(box) != {"x", "y", "w", "h"}:
        raise ReviewAuditError(f"{field} must contain exactly x, y, w, h")
    for name in ("x", "y", "w", "h"):
        number = box[name]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ReviewAuditError(f"{field}.{name} must be a finite number")
        if not math.isfinite(float(number)) or number < 0 or (
            name in {"w", "h"} and number == 0
        ):
            raise ReviewAuditError(f"{field}.{name} must be non-negative and finite")


def _audit_seal_pages(
    pages: dict[str, Any], expected: int
) -> tuple[dict[str, Any], list[str]]:
    page_numbers: list[int] = []
    reviewed = 0
    uncertain = 0
    missed_pages = 0
    missed_boxes = 0
    for page_id, raw in pages.items():
        if not isinstance(page_id, str) or not page_id:
            raise ReviewAuditError("seal page IDs must be non-empty strings")
        page = _mapping(raw, f"seal_pages.{page_id}")
        unexpected = set(page) - _SEAL_PROPERTIES
        if unexpected:
            raise ReviewAuditError(
                f"unsupported seal page properties for {page_id}: {sorted(unexpected)}"
            )
        missing = _SEAL_PROPERTIES - set(page)
        if missing:
            raise ReviewAuditError(
                f"missing seal page properties for {page_id}: {sorted(missing)}"
            )
        page_number = _page_number(
            page["page_number"], f"seal_pages.{page_id}.page_number"
        )
        page_numbers.append(page_number)
        status = page["status"]
        if status not in _SEAL_STATUSES:
            raise ReviewAuditError(
                f"unsupported seal page status for {page_id}: {status}"
            )
        boxes = page["missed_seal_boxes"]
        if not isinstance(boxes, list):
            raise ReviewAuditError(
                f"seal_pages.{page_id}.missed_seal_boxes must be an array"
            )
        for index, box in enumerate(boxes):
            _bbox(box, f"seal_pages.{page_id}.missed_seal_boxes[{index}]")
        if status == "missed_seal":
            if not boxes:
                raise ReviewAuditError(
                    f"missed_seal status for {page_id} requires at least one bounding box"
                )
            reviewed += 1
            missed_pages += 1
            missed_boxes += len(boxes)
        elif boxes:
            raise ReviewAuditError(
                f"{status} status for {page_id} must not contain missed seal boxes"
            )
        elif status == "no_missed_seal":
            reviewed += 1
        elif status == "uncertain":
            uncertain += 1

    if len(page_numbers) != len(set(page_numbers)):
        raise ReviewAuditError("seal page numbers must be unique")
    expected_numbers = set(range(1, expected + 1))
    coverage_complete = set(page_numbers) == expected_numbers
    review_complete = reviewed == expected and uncertain == 0
    complete = coverage_complete and review_complete
    issues: list[str] = []
    if not coverage_complete:
        issues.append("seal_page_coverage_incomplete")
    if coverage_complete and not review_complete:
        issues.append("seal_page_review_incomplete")
    return (
        {
            "expected": expected,
            "submitted": len(pages),
            "reviewed": reviewed,
            "uncertain": uncertain,
            "complete": complete,
            "missed_page_count": missed_pages,
            "missed_box_count": missed_boxes,
        },
        issues,
    )


def _audit_signature_fields(
    fields: dict[str, Any], expected: int
) -> tuple[dict[str, Any], list[str]]:
    fields_reviewed = 0
    handwriting_reviewed = 0
    uncertain = 0
    handwritten_present = 0
    for field_id, raw in fields.items():
        if not isinstance(field_id, str) or not field_id:
            raise ReviewAuditError("signature field IDs must be non-empty strings")
        field = _mapping(raw, f"signature_fields.{field_id}")
        unexpected = set(field) - _SIGNATURE_PROPERTIES
        if unexpected:
            raise ReviewAuditError(
                f"unsupported signature field properties for {field_id}: "
                f"{sorted(unexpected)}"
            )
        missing = _SIGNATURE_PROPERTIES - set(field)
        if missing:
            raise ReviewAuditError(
                f"missing signature field properties for {field_id}: {sorted(missing)}"
            )
        _page_number(
            field["page_number"], f"signature_fields.{field_id}.page_number"
        )
        field_status = field["field_status"]
        handwriting = field["handwritten_status"]
        if field_status not in _FIELD_STATUSES:
            raise ReviewAuditError(
                f"unsupported field status for {field_id}: {field_status}"
            )
        if handwriting not in _HANDWRITING_STATUSES:
            raise ReviewAuditError(
                f"unsupported handwritten status for {field_id}: {handwriting}"
            )
        if field_status == "field_absent" and handwriting != "not_applicable":
            raise ReviewAuditError(
                f"field_absent status for {field_id} must use not_applicable handwriting"
            )
        if field_status == "unreviewed" and handwriting != "unreviewed":
            raise ReviewAuditError(
                f"unreviewed field {field_id} must use unreviewed handwriting"
            )
        if field_status == "uncertain" and handwriting not in {
            "uncertain",
            "unreviewed",
        }:
            raise ReviewAuditError(
                f"uncertain field {field_id} cannot contain a handwriting decision"
            )
        if field_status == "field_present" and handwriting == "not_applicable":
            raise ReviewAuditError(
                f"field_present status for {field_id} cannot use not_applicable handwriting"
            )

        field_is_uncertain = field_status == "uncertain" or handwriting == "uncertain"
        if field_status in {"field_present", "field_absent"}:
            fields_reviewed += 1
        if handwriting in {
            "handwritten_present",
            "handwritten_absent",
            "not_applicable",
        }:
            handwriting_reviewed += 1
        if field_is_uncertain:
            uncertain += 1
        if handwriting == "handwritten_present":
            handwritten_present += 1

    coverage_complete = len(fields) == expected
    review_complete = (
        fields_reviewed == expected
        and handwriting_reviewed == expected
        and uncertain == 0
    )
    complete = coverage_complete and review_complete
    issues: list[str] = []
    if not coverage_complete:
        issues.append("signature_field_coverage_incomplete")
    if coverage_complete and not review_complete:
        issues.append("signature_field_review_incomplete")
    return (
        {
            "expected": expected,
            "submitted": len(fields),
            "fields_reviewed": fields_reviewed,
            "handwriting_reviewed": handwriting_reviewed,
            "uncertain": uncertain,
            "complete": complete,
            "handwritten_present_count": handwritten_present,
        },
        issues,
    )


def audit_signature_review(payload: dict[str, Any]) -> dict[str, Any]:
    """Audit page/field review coverage without returning source paths or OCR text."""

    review = _mapping(payload, "review")
    unexpected = set(review) - _ROOT_PROPERTIES
    if unexpected:
        raise ReviewAuditError(
            f"unsupported review properties: {sorted(unexpected)}"
        )
    missing = _ROOT_PROPERTIES - set(review)
    if missing:
        raise ReviewAuditError(f"missing review properties: {sorted(missing)}")
    if review["schema_version"] != "1.0.0":
        raise ReviewAuditError("schema_version must be 1.0.0")
    group_id = review["document_group_id"]
    if not isinstance(group_id, str) or not group_id.strip():
        raise ReviewAuditError("document_group_id must be a non-empty string")
    expected_seal = _count(
        review["expected_seal_page_count"], "expected_seal_page_count"
    )
    expected_signature = _count(
        review["expected_signature_field_count"], "expected_signature_field_count"
    )
    seal_pages = _mapping(review["seal_pages"], "seal_pages")
    signature_fields = _mapping(review["signature_fields"], "signature_fields")
    seal, seal_issues = _audit_seal_pages(seal_pages, expected_seal)
    signature, signature_issues = _audit_signature_fields(
        signature_fields, expected_signature
    )
    issues = [*seal_issues, *signature_issues]
    applicable_ready = (expected_seal == 0 or seal["complete"]) and (
        expected_signature == 0 or signature["complete"]
    )
    return {
        "schema_version": "1.0.0",
        "status": "ready" if applicable_ready else "incomplete",
        "document_group_id": group_id,
        "coverage": {"seal": seal, "signature": signature},
        "truth_ready": {
            "seal_recall": expected_seal > 0 and seal["complete"],
            "handwritten_signature": expected_signature > 0
            and signature["complete"],
        },
        "issues": issues,
        "privacy": {
            "contains_source_paths": False,
            "contains_ocr_text": False,
        },
    }
