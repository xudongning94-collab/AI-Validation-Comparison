from __future__ import annotations

import sqlite3

import pytest

from bid_compare_agent.tasks import InvalidTaskTransition, TaskConflictError, TaskStore


def test_task_store_persists_state_and_hash_chained_audit(tmp_path) -> None:
    database = tmp_path / "tasks.sqlite3"
    context = {"schema_version": "1.0.0", "files": [{"sha256": "a" * 64}]}

    with TaskStore(database) as store:
        created = store.create_task(
            "task-001",
            request_fingerprint="request-a",
            context=context,
            actor_id="user-a",
        )
        assert created["status"] == "created"
        store.transition(
            "task-001",
            status="running",
            stage="parsing",
            event_type="stage_started",
            actor_id="worker-a",
        )
        store.transition(
            "task-001",
            status="running",
            stage="reporting",
            event_type="stage_checkpoint",
            actor_id="worker-a",
            payload={"output_sha256": "b" * 64},
        )
        completed = store.transition(
            "task-001",
            status="succeeded",
            stage="complete",
            event_type="task_succeeded",
            actor_id="worker-a",
        )
        assert completed["attempt_count"] == 1
        assert store.verify_audit_chain("task-001") is True
        assert [event["sequence"] for event in store.list_events("task-001")] == [1, 2, 3, 4]

    with TaskStore(database) as reopened:
        assert reopened.get_task("task-001")["status"] == "succeeded"
        assert reopened.verify_audit_chain("task-001") is True


def test_task_store_rejects_context_changes_and_illegal_transitions(tmp_path) -> None:
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        store.create_task(
            "task-002",
            request_fingerprint="request-a",
            context={"files": []},
        )
        same = store.create_task(
            "task-002",
            request_fingerprint="request-a",
            context={"files": []},
        )
        assert same["task_id"] == "task-002"
        with pytest.raises(TaskConflictError):
            store.create_task(
                "task-002",
                request_fingerprint="request-b",
                context={"files": [{"sha256": "changed"}]},
            )
        with pytest.raises(InvalidTaskTransition):
            store.transition(
                "task-002",
                status="succeeded",
                stage="complete",
                event_type="invalid_skip",
            )


def test_recovery_marks_running_tasks_interrupted_and_chain_detects_tampering(tmp_path) -> None:
    database = tmp_path / "tasks.sqlite3"
    with TaskStore(database) as store:
        store.create_task("task-003", request_fingerprint="request-c", context={"files": []})
        store.transition(
            "task-003",
            status="running",
            stage="vision",
            event_type="stage_started",
        )
        assert store.recover_interrupted() == ["task-003"]
        task = store.get_task("task-003")
        assert task["status"] == "interrupted"
        assert task["current_stage"] == "vision"
        assert store.verify_audit_chain("task-003") is True

    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE audit_events SET payload_json = ? WHERE task_id = ? AND sequence = 2",
        ('{"tampered":true}', "task-003"),
    )
    connection.commit()
    connection.close()

    with TaskStore(database) as reopened:
        assert reopened.verify_audit_chain("task-003") is False


def test_from_env_recovers_running_tasks_on_process_restart(tmp_path, monkeypatch) -> None:
    database = tmp_path / "tasks.sqlite3"
    with TaskStore(database) as store:
        store.create_task(
            "task-restart",
            request_fingerprint="request-restart",
            context={"files": []},
        )
        store.transition(
            "task-restart",
            status="running",
            stage="analysis",
            event_type="analysis_started",
        )

    monkeypatch.setenv("BID_COMPARE_DATA_DIR", str(tmp_path))
    with TaskStore.from_env() as recovered:
        task = recovered.get_task("task-restart")
        events = recovered.list_events("task-restart")

        assert task["status"] == "interrupted"
        assert events[-1]["event_type"] == "task_interrupted_on_recovery"
        assert events[-1]["actor_id"] == "startup-recovery"
        assert recovered.verify_audit_chain("task-restart") is True
