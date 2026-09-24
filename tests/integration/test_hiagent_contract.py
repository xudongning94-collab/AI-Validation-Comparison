from __future__ import annotations

import json
from pathlib import Path

from bid_compare_agent.api.app import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_hiagent_openapi_snapshot_matches_runtime() -> None:
    snapshot = json.loads(
        (PROJECT_ROOT / "hiagent" / "openapi.json").read_text(encoding="utf-8")
    )

    assert snapshot == app.openapi()
    assert snapshot["info"]["version"] == "0.1.0-alpha.12"
    assert {
        "/health",
        "/v1/parse",
        "/v1/preprocess",
        "/v1/text-compare",
        "/v1/image-compare",
        "/v1/format-check",
        "/v1/ai-check",
        "/v1/signature-check",
        "/v1/analyze",
        "/v1/score",
        "/v1/annotate-docx",
        "/v1/tasks/{task_id}",
    } == set(snapshot["paths"])


def test_hiagent_environment_contract_has_no_secret_value() -> None:
    content = (PROJECT_ROOT / "hiagent" / "environment.example.env").read_text(
        encoding="utf-8"
    )

    assert "BID_COMPARE_API_BASE_URL=" in content
    assert "BID_COMPARE_API_TIMEOUT_SECONDS=120" in content
    assert "TOKEN=" not in content
