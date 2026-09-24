from __future__ import annotations

import io
import json

from docx import Document
from fastapi.testclient import TestClient

from bid_compare_agent.api import create_app


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph(
        "投标人：星河科技有限公司 法定代表人：张三 2026年9月20日"
    )
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def _requirements() -> dict:
    return {
        "requirements": [
            {
                "rule_id": "sign-cover",
                "title": "投标函签署页",
                "expected_company_names": ["星河科技有限公司"],
                "expected_signer_names": ["张三"],
                "require_signature": True,
                "require_seal": True,
                "require_date": True,
                "anchor_terms": ["投标人", "法定代表人"],
                "date_not_before": "2026-09-01",
                "date_not_after": "2026-09-30",
            }
        ]
    }


def _evidence() -> dict:
    return {
        "pages": [
            {
                "page_number": 1,
                "ocr_status": "not_run",
                "vision_status": "ok",
                "candidates": [
                    {
                        "candidate_id": "signature-1",
                        "kind": "signature",
                        "bbox": {"x": 100, "y": 200, "w": 80, "h": 30},
                        "confidence": 0.92,
                        "detector": "test",
                    },
                    {
                        "candidate_id": "seal-1",
                        "kind": "seal",
                        "bbox": {"x": 200, "y": 180, "w": 100, "h": 100},
                        "confidence": 0.95,
                        "detector": "test",
                    },
                ],
            }
        ]
    }


def test_signature_check_endpoint_accepts_rules_and_visual_evidence() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/signature-check",
        files={"file": ("response.docx", _docx_bytes(), DOCX_MIME)},
        data={
            "requirements_json": json.dumps(_requirements(), ensure_ascii=False),
            "evidence_json": json.dumps(_evidence(), ensure_ascii=False),
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["operation"] == "signature_check"
    result = payload["result"]
    assert result["check_type"] == "signature_compliance"
    assert result["summary"]["passed_rule_count"] == 1
    assert result["summary"]["finding_count"] == 0
    assert result["metadata"]["authenticity_check"] is False


def test_signature_check_without_worker_result_is_review_not_missing() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/signature-check",
        files={"file": ("response.docx", _docx_bytes(), DOCX_MIME)},
        data={"requirements_json": json.dumps(_requirements(), ensure_ascii=False)},
    )

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    codes = {finding["evidence"]["issue_code"] for finding in result["findings"]}
    assert "signature_evidence_unavailable" in codes
    assert "seal_evidence_unavailable" in codes
    assert "missing_signature" not in codes
    assert result["summary"]["review_rule_count"] == 1


def test_signature_check_rejects_invalid_json_and_invalid_rule_types() -> None:
    client = TestClient(create_app())
    upload = {"file": ("response.docx", _docx_bytes(), DOCX_MIME)}

    malformed = client.post(
        "/v1/signature-check",
        files=upload,
        data={"requirements_json": "{bad-json"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "invalid_signature_json"

    invalid_rules = _requirements()
    invalid_rules["requirements"][0]["require_seal"] = "yes"
    invalid = client.post(
        "/v1/signature-check",
        files={"file": ("response.docx", _docx_bytes(), DOCX_MIME)},
        data={"requirements_json": json.dumps(invalid_rules, ensure_ascii=False)},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_input"

    invalid_evidence = _evidence()
    invalid_evidence["pages"][0]["candidates"][0]["bbox"] = {
        "x": 10,
        "y": 20,
        "w": "not-a-number",
    }
    malformed_candidate = client.post(
        "/v1/signature-check",
        files={"file": ("response.docx", _docx_bytes(), DOCX_MIME)},
        data={
            "requirements_json": json.dumps(_requirements(), ensure_ascii=False),
            "evidence_json": json.dumps(invalid_evidence, ensure_ascii=False),
        },
    )
    assert malformed_candidate.status_code == 422
    assert malformed_candidate.json()["error"] == {
        "code": "invalid_input",
        "message": "视觉候选 bbox 必须且只能包含 x/y/w/h",
    }
