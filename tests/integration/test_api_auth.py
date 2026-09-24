from __future__ import annotations

import io

from docx import Document
from fastapi.testclient import TestClient

from bid_compare_agent.api import ApiAuthConfig, AuthConfigurationError, create_app


API_KEY = "test-key-with-at-least-16-characters"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("鉴权接口测试。")
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def test_health_is_public_but_business_routes_require_api_key() -> None:
    client = TestClient(create_app(auth_config=ApiAuthConfig(mode="api_key", api_keys=(API_KEY,))))

    assert client.get("/health").status_code == 200
    rejected = client.post(
        "/v1/parse",
        files={"file": ("source.docx", _docx_bytes(), DOCX_MIME)},
    )
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "authentication_required"
    assert rejected.headers["www-authenticate"] == "Bearer"

    accepted = client.post(
        "/v1/parse",
        headers={"Authorization": f"Bearer {API_KEY}"},
        files={"file": ("source.docx", _docx_bytes(), DOCX_MIME)},
    )
    assert accepted.status_code == 200


def test_x_api_key_is_supported_and_invalid_configuration_is_rejected() -> None:
    client = TestClient(create_app(auth_config=ApiAuthConfig(mode="api_key", api_keys=(API_KEY,))))
    response = client.post(
        "/v1/parse",
        headers={"X-API-Key": API_KEY},
        files={"file": ("source.docx", _docx_bytes(), DOCX_MIME)},
    )
    assert response.status_code == 200

    try:
        ApiAuthConfig(mode="api_key", api_keys=())
    except AuthConfigurationError:
        pass
    else:
        raise AssertionError("空 API Key 配置必须被拒绝")
