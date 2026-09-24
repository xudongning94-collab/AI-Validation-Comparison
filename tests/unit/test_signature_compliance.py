from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bid_compare_agent.compliance import (
    PageEvidence,
    SignatureRequirement,
    VisualCandidate,
    check_signature_compliance,
)


ROOT = Path(__file__).resolve().parents[2]


def _candidate(
    candidate_id: str,
    kind: str,
    *,
    confidence: float = 0.95,
    quality_flags: tuple[str, ...] = (),
) -> VisualCandidate:
    return VisualCandidate(
        candidate_id=candidate_id,
        kind=kind,
        page_number=1,
        bbox={"x": 100, "y": 200, "w": 80, "h": 50},
        confidence=confidence,
        quality_flags=quality_flags,
        detector="test-detector",
    )


def _requirement(**changes) -> SignatureRequirement:
    values = {
        "rule_id": "sign-cover",
        "title": "投标函签署页",
        "expected_company_names": ("星河科技有限公司", "星河科技"),
        "expected_signer_names": ("张三",),
        "signer_role": "法定代表人",
        "require_signature": True,
        "require_seal": True,
        "require_date": True,
        "allowed_pages": (1,),
        "anchor_terms": ("投标人", "法定代表人"),
        "date_not_before": date(2026, 9, 1),
        "date_not_after": date(2026, 9, 30),
    }
    values.update(changes)
    return SignatureRequirement(**values)


def _validate_schema(payload: dict) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "signature_compliance.schema.json").read_text(encoding="utf-8")
    )
    finding_schema = json.loads(
        (ROOT / "schemas" / "finding.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(
        "https://example.local/bid-compare/finding.schema.json",
        Resource.from_contents(finding_schema),
    )
    schema["properties"]["findings"]["items"]["$ref"] = (
        "https://example.local/bid-compare/finding.schema.json"
    )
    Draft202012Validator(schema, registry=registry).validate(payload)


def test_complete_signature_page_passes_without_findings() -> None:
    page = PageEvidence(
        page_number=1,
        native_text="投标人：星河科技有限公司 法定代表人：张三 2026年9月20日",
        company_names=("星河科技有限公司",),
        person_names=("张三",),
        candidates=(
            _candidate("signature-1", "signature"),
            _candidate("seal-1", "seal"),
        ),
        vision_status="ok",
    )

    result = check_signature_compliance("doc-a", [page], [_requirement()])
    payload = result.to_dict()

    _validate_schema(payload)
    assert result.summary == {
        "rule_count": 1,
        "passed_rule_count": 1,
        "review_rule_count": 0,
        "failed_rule_count": 0,
        "finding_count": 0,
    }
    assert result.rules[0].matched_company_name == "星河科技有限公司"
    assert result.rules[0].matched_signer_name == "张三"
    assert result.rules[0].matched_date == "2026-09-20"


def test_missing_candidates_wrong_company_signer_and_date_are_high_risk() -> None:
    page = PageEvidence(
        page_number=1,
        native_text="投标人：其他公司 授权代表：李四 2026-10-02",
        company_names=("其他公司",),
        person_names=("李四",),
        date_values=("2026-10-02",),
        vision_status="ok",
    )

    result = check_signature_compliance("doc-a", [page], [_requirement()])
    codes = {finding.evidence["issue_code"] for finding in result.findings}

    assert {
        "missing_signature",
        "missing_seal",
        "company_name_mismatch",
        "signer_name_mismatch",
        "date_out_of_range",
    }.issubset(codes)
    assert result.rules[0].status == "failed"
    assert all(finding.metadata["authenticity_check"] is False for finding in result.findings)


def test_low_confidence_and_quality_flags_force_review_not_false_success() -> None:
    page = PageEvidence(
        page_number=1,
        native_text="投标人 法定代表人",
        ocr_items=(
            {
                "evidence_id": "ocr-company",
                "text": "星河科技有限公司 张三 2026年9月20日",
                "confidence": 0.60,
            },
        ),
        candidates=(
            _candidate("signature-low", "signature", confidence=0.50),
            _candidate(
                "seal-clipped",
                "seal",
                confidence=0.55,
                quality_flags=("clipped", "unreadable"),
            ),
        ),
        ocr_status="ok",
        vision_status="ok",
    )

    result = check_signature_compliance("doc-a", [page], [_requirement()])
    codes = {finding.evidence["issue_code"] for finding in result.findings}

    assert "signature_low_confidence" in codes
    assert "seal_low_confidence" in codes
    assert "seal_quality_issue" in codes
    assert "company_name_low_confidence" in codes
    assert "signer_name_low_confidence" in codes
    assert "date_low_confidence" in codes
    assert result.rules[0].status == "review"


def test_required_page_or_anchor_mismatch_is_reported() -> None:
    page = PageEvidence(
        page_number=1,
        native_text="普通正文，没有签署区",
    )
    requirement = _requirement(allowed_pages=(2,), anchor_terms=("投标人",))

    result = check_signature_compliance("doc-a", [page], [requirement])

    assert result.rules[0].relevant_pages == []
    assert any(
        finding.evidence["issue_code"] == "required_location_missing"
        for finding in result.findings
    )


def test_unavailable_workers_do_not_masquerade_as_missing_signature_or_seal() -> None:
    page = PageEvidence(page_number=1, ocr_status="failed", vision_status="disabled")
    requirement = _requirement(anchor_terms=(), expected_signer_names=())

    result = check_signature_compliance("doc-a", [page], [requirement])
    codes = {finding.evidence["issue_code"] for finding in result.findings}

    assert "signature_evidence_unavailable" in codes
    assert "seal_evidence_unavailable" in codes
    assert "company_name_evidence_unavailable" in codes
    assert "date_evidence_unavailable" in codes
    assert "missing_signature" not in codes
    assert "missing_seal" not in codes


@pytest.mark.parametrize(
    "changes",
    [
        {"rule_id": ""},
        {"allowed_pages": (0,)},
        {"minimum_candidate_confidence": 1.1},
        {"date_not_before": date(2026, 10, 1), "date_not_after": date(2026, 9, 1)},
    ],
)
def test_invalid_signature_requirements_are_rejected(changes: dict) -> None:
    with pytest.raises(ValueError):
        _requirement(**changes)
