from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_model_stager_requires_explicit_network_acknowledgement(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "stage_official_vision_models.py"),
            "--destination",
            str(tmp_path / "models"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 2
    assert "explicit --allow-network is required" in result.stderr
    assert not (tmp_path / "models").exists()
