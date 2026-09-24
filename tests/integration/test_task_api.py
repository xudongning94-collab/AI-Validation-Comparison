from __future__ import annotations

import io

from docx import Document
from fastapi.testclient import TestClient

from bid_compare_agent.api import ApiPipeline, create_app
from bid_compare_agent.tasks import TaskStore


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def _files():
    common = "Project delivery uses a unified quality process and scheduled milestones."
    return [
        ("files", ("a.docx", _docx_bytes(common), DOCX_MIME)),
        ("files", ("b.docx", _docx_bytes(common), DOCX_MIME)),
    ]


def test_analyze_persists_task_context_and_audit_chain(tmp_path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    client = TestClient(create_app(task_store=store))

    analyzed = client.post("/v1/analyze", files=_files())

    assert analyzed.status_code == 200, analyzed.text
    task_id = analyzed.json()["result"]["task"]["task_id"]
    detail = client.get(f"/v1/tasks/{task_id}")
    assert detail.status_code == 200
    result = detail.json()["result"]
    assert result["task"]["status"] == "succeeded"
    assert result["task"]["attempt_count"] == 1
    assert len(result["task"]["context"]["files"]) == 2
    assert all(len(item["sha256"]) == 64 for item in result["task"]["context"]["files"])
    assert [event["event_type"] for event in result["events"]] == [
        "task_created",
        "analysis_started",
        "analysis_succeeded",
    ]
    assert result["audit_chain_valid"] is True
    store.close()


class FailingPipeline(ApiPipeline):
    def analyze(self, paths):
        raise ValueError("synthetic analysis failure")


def test_analyze_failure_is_persisted_for_recovery(tmp_path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    client = TestClient(create_app(task_store=store, pipeline=FailingPipeline()))

    response = client.post("/v1/analyze", files=_files())

    assert response.status_code == 422
    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "failed"
    assert tasks[0]["current_stage"] == "analysis"
    assert tasks[0]["last_error_code"] == "invalid_input"
    assert store.verify_audit_chain(tasks[0]["task_id"]) is True
    store.close()


def test_task_details_do_not_cross_api_key_identity(tmp_path) -> None:
    from bid_compare_agent.api import ApiAuthConfig

    key_a = "task-owner-key-aaaaaaaa"
    key_b = "different-owner-key-bbbb"
    store = TaskStore(tmp_path / "tasks.sqlite3")
    client = TestClient(
        create_app(
            task_store=store,
            auth_config=ApiAuthConfig(mode="api_key", api_keys=(key_a, key_b)),
        )
    )
    analyzed = client.post(
        "/v1/analyze",
        headers={"Authorization": f"Bearer {key_a}"},
        files=_files(),
    )
    task_id = analyzed.json()["result"]["task"]["task_id"]

    hidden = client.get(
        f"/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {key_b}"},
    )
    assert hidden.status_code == 404
    store.close()
