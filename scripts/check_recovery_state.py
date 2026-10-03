from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "PROJECT_STATE.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _load_state() -> dict[str, Any]:
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PROJECT_STATE.json must contain an object")
    return payload


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"missing state field: {'.'.join(keys)}")
        current = current[key]
    return current


def validate_recovery_state() -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    facts: dict[str, str] = {}

    try:
        state = _load_state()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot load PROJECT_STATE.json: {exc}"], facts

    try:
        expected_directory = str(_nested(state, "project", "repository_directory"))
        expected_version = str(_nested(state, "project", "version"))
        handoff_name = str(_nested(state, "recovery", "authoritative_handoff"))
        history_source = str(_nested(state, "recovery", "history_source"))
        checkpoint_id = str(_nested(state, "recovery", "checkpoint_id"))
        historical_origin_thread_id = str(
            _nested(state, "recovery", "historical_origin_thread_id")
        )
        thread_history_authoritative = _nested(
            state, "recovery", "thread_history_authoritative"
        )
        phase_id = str(_nested(state, "phase", "id"))
        phase_status = str(_nested(state, "phase", "status"))
        baseline_commit = str(_nested(state, "git", "baseline_commit"))
        allowed_branches = _nested(state, "git", "allowed_checkpoint_branches")
        expected_tests = int(_nested(state, "verification", "expected_passed_tests"))
    except (TypeError, ValueError) as exc:
        return [str(exc)], facts

    if ROOT.name != expected_directory:
        errors.append(
            f"repository directory mismatch: expected {expected_directory}, got {ROOT.name}"
        )

    if history_source != "repository_checkpoint":
        errors.append(
            "recovery.history_source must be repository_checkpoint; "
            "Codex thread history is navigation metadata, not project state"
        )
    if not checkpoint_id:
        errors.append("recovery.checkpoint_id must not be empty")
    if not historical_origin_thread_id:
        errors.append("recovery.historical_origin_thread_id must not be empty")
    if thread_history_authoritative is not False:
        errors.append("recovery.thread_history_authoritative must be false")

    root_result = _git("rev-parse", "--show-toplevel")
    if root_result.returncode != 0:
        errors.append(f"not a Git repository: {root_result.stderr.strip()}")
    else:
        actual_root = Path(root_result.stdout.strip()).resolve()
        facts["repo_root"] = str(actual_root)
        if actual_root != ROOT.resolve():
            errors.append(f"Git root mismatch: expected {ROOT}, got {actual_root}")

    try:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        actual_version = str(pyproject["project"]["version"])
        facts["version"] = actual_version
        if actual_version != expected_version:
            errors.append(
                f"version mismatch: PROJECT_STATE={expected_version}, pyproject={actual_version}"
            )
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        errors.append(f"cannot read project version: {exc}")

    branch_result = _git("branch", "--show-current")
    branch = branch_result.stdout.strip()
    facts["branch"] = branch or "DETACHED"
    if not isinstance(allowed_branches, list) or branch not in allowed_branches:
        errors.append(f"branch {branch or 'DETACHED'} is not allowed by PROJECT_STATE.json")

    head_result = _git("rev-parse", "HEAD")
    if head_result.returncode == 0:
        facts["head"] = head_result.stdout.strip()
    else:
        errors.append(f"cannot resolve HEAD: {head_result.stderr.strip()}")

    ancestor_result = _git("merge-base", "--is-ancestor", baseline_commit, "HEAD")
    if ancestor_result.returncode != 0:
        errors.append(f"baseline commit {baseline_commit} is not an ancestor of HEAD")

    for relative_path in ("AGENTS.md", "PROJECT_STATE.json", handoff_name):
        path = ROOT / relative_path
        if not path.is_file():
            errors.append(f"required recovery file is missing: {relative_path}")
            continue
        tracked = _git("ls-files", "--error-unmatch", "--", relative_path)
        if tracked.returncode != 0:
            errors.append(f"required recovery file is not tracked or staged: {relative_path}")

    handoff_path = ROOT / handoff_name
    if handoff_path.is_file():
        handoff_text = handoff_path.read_text(encoding="utf-8")
        for required_text in (
            phase_id,
            phase_status,
            "PROJECT_STATE.json",
            f"恢复来源：`{history_source}`",
            f"恢复检查点 ID：`{checkpoint_id}`",
        ):
            if required_text not in handoff_text:
                errors.append(f"handoff does not contain required state marker: {required_text}")

    facts["history_source"] = history_source
    facts["checkpoint_id"] = checkpoint_id
    facts["historical_origin_thread_id"] = historical_origin_thread_id
    facts["phase"] = f"{phase_id}:{phase_status}"
    facts["expected_passed_tests"] = str(expected_tests)
    return errors, facts


def main() -> int:
    errors, facts = validate_recovery_state()
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1

    print("RECOVERY_STATE_OK")
    for key, value in facts.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
