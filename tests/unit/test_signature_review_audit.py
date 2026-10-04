from __future__ import annotations

import pytest

from bid_compare_agent.vision.review_audit import ReviewAuditError, audit_signature_review


def _complete_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "document_group_id": "group-a",
        "expected_seal_page_count": 2,
        "expected_signature_field_count": 2,
        "seal_pages": {
            "page-0001": {
                "page_number": 1,
                "status": "no_missed_seal",
                "missed_seal_boxes": [],
            },
            "page-0002": {
                "page_number": 2,
                "status": "missed_seal",
                "missed_seal_boxes": [{"x": 10, "y": 20, "w": 30, "h": 40}],
            },
        },
        "signature_fields": {
            "field-1": {
                "page_number": 1,
                "field_status": "field_present",
                "handwritten_status": "handwritten_present",
            },
            "field-2": {
                "page_number": 2,
                "field_status": "field_absent",
                "handwritten_status": "not_applicable",
            },
        },
    }


def test_complete_review_is_ready_for_recall_and_handwriting_truth() -> None:
    result = audit_signature_review(_complete_payload())

    assert result["status"] == "ready"
    assert result["coverage"]["seal"]["complete"] is True
    assert result["coverage"]["seal"]["missed_page_count"] == 1
    assert result["coverage"]["seal"]["missed_box_count"] == 1
    assert result["coverage"]["signature"]["complete"] is True
    assert result["coverage"]["signature"]["handwritten_present_count"] == 1
    assert result["truth_ready"] == {
        "seal_recall": True,
        "handwritten_signature": True,
    }


def test_missing_seal_page_keeps_recall_truth_incomplete() -> None:
    payload = _complete_payload()
    payload["seal_pages"].pop("page-0002")

    result = audit_signature_review(payload)

    assert result["status"] == "incomplete"
    assert result["coverage"]["seal"]["submitted"] == 1
    assert result["truth_ready"]["seal_recall"] is False
    assert "seal_page_coverage_incomplete" in result["issues"]


def test_missed_seal_status_requires_at_least_one_box() -> None:
    payload = _complete_payload()
    payload["seal_pages"]["page-0002"]["missed_seal_boxes"] = []

    with pytest.raises(ReviewAuditError, match="requires at least one bounding box"):
        audit_signature_review(payload)


def test_absent_signature_field_cannot_contain_handwriting() -> None:
    payload = _complete_payload()
    payload["signature_fields"]["field-2"]["handwritten_status"] = "handwritten_present"

    with pytest.raises(ReviewAuditError, match="must use not_applicable"):
        audit_signature_review(payload)


def test_uncertain_signature_field_is_counted_once() -> None:
    payload = _complete_payload()
    payload["signature_fields"]["field-1"] = {
        "page_number": 1,
        "field_status": "uncertain",
        "handwritten_status": "uncertain",
    }

    result = audit_signature_review(payload)

    assert result["coverage"]["signature"]["uncertain"] == 1


def test_zero_expected_tracks_are_not_reported_as_incomplete() -> None:
    seal_only = _complete_payload()
    seal_only["expected_signature_field_count"] = 0
    seal_only["signature_fields"] = {}

    signature_only = _complete_payload()
    signature_only["expected_seal_page_count"] = 0
    signature_only["seal_pages"] = {}

    seal_result = audit_signature_review(seal_only)
    signature_result = audit_signature_review(signature_only)

    assert seal_result["coverage"]["signature"]["complete"] is True
    assert "signature_field_coverage_incomplete" not in seal_result["issues"]
    assert signature_result["coverage"]["seal"]["complete"] is True
    assert "seal_page_coverage_incomplete" not in signature_result["issues"]


def test_unknown_or_path_bearing_properties_are_rejected() -> None:
    payload = _complete_payload()
    payload["source_path"] = "C:/private/source.pdf"

    with pytest.raises(ReviewAuditError, match="unsupported review properties"):
        audit_signature_review(payload)
