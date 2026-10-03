from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_recovery_state.py"


@pytest.mark.parametrize("cwd", [ROOT, ROOT.parent], ids=["repo-root", "parent-folder"])
def test_recovery_state_resolves_the_repository_from_any_working_directory(cwd: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "RECOVERY_STATE_OK" in result.stdout
    repo_line = next(line for line in result.stdout.splitlines() if line.startswith("repo_root="))
    assert repo_line.replace("\\", "/").endswith("/bid-compare-agent")
    assert "phase=D13.3:in_progress" in result.stdout
    assert "history_source=repository_checkpoint" in result.stdout
    assert "checkpoint_id=d13.3-recovery-contract-v2" in result.stdout

    state = json.loads((ROOT / "PROJECT_STATE.json").read_text(encoding="utf-8"))
    assert "original_task_id" not in state["recovery"]
    assert state["recovery"]["historical_origin_thread_id"] == (
        "01a0cd3c-1267-7101-9b52-0c63eb4df8c7"
    )
    restore_script = (ROOT / "scripts" / "restore_context.ps1").read_text(
        encoding="utf-8"
    )
    assert "-m compileall -q src scripts tests workers" in restore_script
