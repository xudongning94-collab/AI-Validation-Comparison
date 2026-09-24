from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import validate

from bid_compare_agent.api import create_app


ROOT = Path(__file__).resolve().parents[2]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_api_converts_framework_validation_to_stable_error_schema():
    client = TestClient(create_app())

    response = client.post("/v1/parse")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    schema = json.loads((ROOT / "schemas" / "api_error.schema.json").read_text(encoding="utf-8"))
    validate(response.json(), schema)


def test_api_rejects_malformed_document_as_input_error():
    client = TestClient(create_app())

    response = client.post(
        "/v1/parse",
        files={"file": ("broken.docx", b"not-a-docx", DOCX_MIME)},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
