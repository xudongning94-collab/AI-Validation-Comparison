from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TERMINAL_STATES = {"succeeded", "cancelled"}
ALLOWED_TRANSITIONS = {
    "created": {"running", "cancelled"},
    "running": {"running", "succeeded", "failed", "interrupted", "cancelled"},
    "failed": {"running", "cancelled"},
    "interrupted": {"running", "cancelled"},
    "succeeded": set(),
    "cancelled": set(),
}


class TaskNotFoundError(KeyError):
    pass


class TaskConflictError(ValueError):
    pass


class InvalidTaskTransition(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(record).encode("utf-8")).hexdigest()


class TaskStore:
    """SQLite task state and append-only hash-chained audit store."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.database,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    @classmethod
    def from_env(cls) -> "TaskStore":
        data_dir = os.environ.get("BID_COMPARE_DATA_DIR", "").strip()
        if not data_dir:
            return cls(":memory:")
        store = cls(Path(data_dir).resolve() / "tasks.sqlite3")
        store.recover_interrupted(actor_id="startup-recovery")
        return store

    def _initialize(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            if self.database != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error_code TEXT,
                    last_error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_event_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    UNIQUE(task_id, sequence),
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );

                CREATE INDEX IF NOT EXISTS idx_audit_task_sequence
                    ON audit_events(task_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                    ON tasks(status);
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "TaskStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _begin(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def _append_event_locked(
        self,
        *,
        task_id: str,
        event_type: str,
        stage: str,
        actor_id: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        previous = self._connection.execute(
            """
            SELECT sequence, event_hash
            FROM audit_events
            WHERE task_id = ?
            ORDER BY sequence DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        sequence = int(previous["sequence"]) + 1 if previous else 1
        previous_hash = str(previous["event_hash"]) if previous else "0" * 64
        payload_json = _canonical_json(payload)
        hash_record = {
            "task_id": task_id,
            "sequence": sequence,
            "event_type": event_type,
            "stage": stage,
            "actor_id": actor_id,
            "created_at": created_at,
            "payload_json": payload_json,
            "previous_event_hash": previous_hash,
        }
        digest = _event_hash(hash_record)
        cursor = self._connection.execute(
            """
            INSERT INTO audit_events (
                task_id, sequence, event_type, stage, actor_id, created_at,
                payload_json, previous_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                sequence,
                event_type,
                stage,
                actor_id,
                created_at,
                payload_json,
                previous_hash,
                digest,
            ),
        )
        return {
            "event_id": int(cursor.lastrowid),
            **hash_record,
            "payload": payload,
            "event_hash": digest,
        }

    def create_task(
        self,
        task_id: str,
        *,
        request_fingerprint: str,
        context: dict[str, Any],
        actor_id: str = "system",
    ) -> dict[str, Any]:
        now = _utc_now()
        context_json = _canonical_json(context)
        with self._lock:
            self._begin()
            try:
                existing = self._connection.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if existing:
                    if (
                        existing["request_fingerprint"] != request_fingerprint
                        or existing["context_json"] != context_json
                    ):
                        raise TaskConflictError(f"任务 {task_id} 已存在且上下文不同")
                    self._connection.execute("COMMIT")
                    return self._row_to_task(existing)
                self._connection.execute(
                    """
                    INSERT INTO tasks (
                        task_id, status, current_stage, request_fingerprint,
                        context_json, attempt_count, created_at, updated_at
                    ) VALUES (?, 'created', 'created', ?, ?, 0, ?, ?)
                    """,
                    (task_id, request_fingerprint, context_json, now, now),
                )
                self._append_event_locked(
                    task_id=task_id,
                    event_type="task_created",
                    stage="created",
                    actor_id=actor_id,
                    payload={"request_fingerprint": request_fingerprint},
                    created_at=now,
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.get_task(task_id)

    def transition(
        self,
        task_id: str,
        *,
        status: str,
        stage: str,
        event_type: str,
        actor_id: str = "system",
        payload: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        if status not in ALLOWED_TRANSITIONS:
            raise InvalidTaskTransition(f"未知任务状态: {status}")
        now = _utc_now()
        with self._lock:
            self._begin()
            try:
                row = self._connection.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    raise TaskNotFoundError(task_id)
                current = str(row["status"])
                if status not in ALLOWED_TRANSITIONS[current]:
                    raise InvalidTaskTransition(f"任务状态不能从 {current} 跳转到 {status}")
                attempt_increment = 1 if status == "running" and current != "running" else 0
                self._connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, current_stage = ?,
                        attempt_count = attempt_count + ?, updated_at = ?,
                        last_error_code = ?, last_error_message = ?
                    WHERE task_id = ?
                    """,
                    (
                        status,
                        stage,
                        attempt_increment,
                        now,
                        error_code,
                        error_message,
                        task_id,
                    ),
                )
                event_payload = dict(payload or {})
                event_payload.update({"from_status": current, "to_status": status})
                if error_code:
                    event_payload["error_code"] = error_code
                self._append_event_locked(
                    task_id=task_id,
                    event_type=event_type,
                    stage=stage,
                    actor_id=actor_id,
                    payload=event_payload,
                    created_at=now,
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.get_task(task_id)

    def recover_interrupted(self, *, actor_id: str = "recovery") -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT task_id, current_stage FROM tasks WHERE status = 'running' ORDER BY task_id"
            ).fetchall()
        recovered: list[str] = []
        for row in rows:
            task_id = str(row["task_id"])
            self.transition(
                task_id,
                status="interrupted",
                stage=str(row["current_stage"]),
                event_type="task_interrupted_on_recovery",
                actor_id=actor_id,
                payload={"reason": "process_restart"},
            )
            recovered.append(task_id)
        return recovered

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": str(row["task_id"]),
            "status": str(row["status"]),
            "current_stage": str(row["current_stage"]),
            "request_fingerprint": str(row["request_fingerprint"]),
            "context": json.loads(str(row["context_json"])),
            "attempt_count": int(row["attempt_count"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_error_code": row["last_error_code"],
            "last_error_message": row["last_error_message"],
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise TaskNotFoundError(task_id)
        return self._row_to_task(row)

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        self.get_task(task_id)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM audit_events WHERE task_id = ? ORDER BY sequence", (task_id,)
            ).fetchall()
        return [
            {
                "event_id": int(row["event_id"]),
                "task_id": str(row["task_id"]),
                "sequence": int(row["sequence"]),
                "event_type": str(row["event_type"]),
                "stage": str(row["stage"]),
                "actor_id": str(row["actor_id"]),
                "created_at": str(row["created_at"]),
                "payload": json.loads(str(row["payload_json"])),
                "payload_json": str(row["payload_json"]),
                "previous_event_hash": str(row["previous_event_hash"]),
                "event_hash": str(row["event_hash"]),
            }
            for row in rows
        ]

    def verify_audit_chain(self, task_id: str) -> bool:
        previous_hash = "0" * 64
        for event in self.list_events(task_id):
            if event["previous_event_hash"] != previous_hash:
                return False
            record = {
                "task_id": event["task_id"],
                "sequence": event["sequence"],
                "event_type": event["event_type"],
                "stage": event["stage"],
                "actor_id": event["actor_id"],
                "created_at": event["created_at"],
                "payload_json": event["payload_json"],
                "previous_event_hash": event["previous_event_hash"],
            }
            if _event_hash(record) != event["event_hash"]:
                return False
            previous_hash = event["event_hash"]
        return True

    def list_tasks(self, statuses: Iterable[str] | None = None) -> list[dict[str, Any]]:
        values = tuple(statuses or ())
        with self._lock:
            if values:
                placeholders = ",".join("?" for _ in values)
                rows = self._connection.execute(
                    f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY created_at",
                    values,
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM tasks ORDER BY created_at"
                ).fetchall()
        return [self._row_to_task(row) for row in rows]
