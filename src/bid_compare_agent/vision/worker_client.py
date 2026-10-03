from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .contract import normalize_ocr_worker_result


class VisionWorkerUnavailable(RuntimeError):
    """Raised when a requested isolated worker capability is unavailable."""


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _dependency_state() -> dict[str, dict[str, Any]]:
    return {
        name: {"available": False, "version": None}
        for name in ("opencv", "numpy", "paddleocr", "paddlepaddle")
    }


def _unavailable_health(code: str, message: str, *, failed: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "failed" if failed else "unavailable",
        "required_python": "3.12",
        "python_version": None,
        "python_compatible": False,
        "capabilities": {
            "signature_candidates": False,
            "ocr": False,
            "authenticity_check": False,
        },
        "dependencies": _dependency_state(),
        "offline_models": {
            "configured": False,
            "manifest_valid": False,
            "model_count": 0,
        },
        "error": {"code": code, "message": message},
    }


class VisionWorkerClient:
    def __init__(
        self,
        python_executable: str | Path | None,
        *,
        repo_root: str | Path,
        offline_model_directory: str | Path | None = None,
        health_timeout_seconds: int = 20,
        task_timeout_seconds: int = 120,
        seal_preferred_min_dimension_ratio: float = 0.06,
        seal_preferred_max_area_ratio: float = 0.04,
    ):
        if not 1 <= health_timeout_seconds <= 3600:
            raise ValueError("health_timeout_seconds must be between 1 and 3600")
        if not 1 <= task_timeout_seconds <= 3600:
            raise ValueError("task_timeout_seconds must be between 1 and 3600")
        if not 0 < seal_preferred_min_dimension_ratio <= 1:
            raise ValueError("seal_preferred_min_dimension_ratio must be in (0, 1]")
        if not 0 < seal_preferred_max_area_ratio <= 1:
            raise ValueError("seal_preferred_max_area_ratio must be in (0, 1]")
        self.python_executable = python_executable
        self.repo_root = Path(repo_root).resolve()
        self.offline_model_directory = offline_model_directory
        self.health_timeout_seconds = health_timeout_seconds
        self.task_timeout_seconds = task_timeout_seconds
        self.seal_preferred_min_dimension_ratio = seal_preferred_min_dimension_ratio
        self.seal_preferred_max_area_ratio = seal_preferred_max_area_ratio
        self._health_cache: dict[str, Any] | None = None

    def _resolve_python(self) -> Path | None:
        if self.python_executable is None:
            return None
        candidate = Path(self.python_executable)
        if candidate.is_file():
            return candidate.resolve()
        discovered = shutil.which(str(self.python_executable))
        return Path(discovered).resolve() if discovered else None

    def probe(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._health_cache is not None and not refresh:
            return self._health_cache
        executable = self._resolve_python()
        if executable is None:
            self._health_cache = _unavailable_health(
                "python_executable_unavailable",
                "The isolated vision-worker Python executable is unavailable.",
            )
            return self._health_cache

        script = self.repo_root / "workers" / "vision_worker_health.py"
        environment = os.environ.copy()
        if self.offline_model_directory is not None:
            environment["BID_COMPARE_PADDLEOCR_MODEL_DIR"] = str(
                Path(self.offline_model_directory).resolve()
            )
        try:
            completed = subprocess.run(
                [str(executable), str(script)],
                cwd=self.repo_root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.health_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._health_cache = _unavailable_health(
                "healthcheck_timeout",
                "The vision-worker health check timed out.",
                failed=True,
            )
            return self._health_cache
        except OSError:
            self._health_cache = _unavailable_health(
                "healthcheck_start_failed",
                "The vision-worker health check could not be started.",
                failed=True,
            )
            return self._health_cache

        try:
            payload = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError):
            payload = None
        if completed.returncode != 0 or not isinstance(payload, dict):
            self._health_cache = _unavailable_health(
                "healthcheck_invalid_output",
                "The vision-worker health check returned invalid output.",
                failed=True,
            )
            return self._health_cache
        self._health_cache = payload
        return payload

    def require_signature_capability(self) -> dict[str, Any]:
        health = self.probe()
        if not bool(health.get("capabilities", {}).get("signature_candidates")):
            code = (health.get("error") or {}).get("code", "signature_worker_unavailable")
            raise VisionWorkerUnavailable(f"signature candidate worker unavailable: {code}")
        return health

    def require_ocr_capability(self) -> dict[str, Any]:
        health = self.probe()
        if not bool(health.get("capabilities", {}).get("ocr")):
            code = (health.get("error") or {}).get("code", "ocr_worker_unavailable")
            raise VisionWorkerUnavailable(f"OCR worker unavailable: {code}")
        return health

    def ocr_page(
        self,
        image_path: str | Path,
        *,
        document_id: str,
        page_number: int,
    ) -> dict[str, Any]:
        path = Path(image_path).resolve()
        image_hash = _sha256(path)
        if image_hash is None:
            raise ValueError("image_path must reference a readable file")
        executable = self._resolve_python()
        if executable is None:
            raw = self._ocr_failure(
                page_number,
                image_hash,
                status="disabled",
                error="Isolated vision-worker Python is unavailable.",
            )
            return normalize_ocr_worker_result(
                raw,
                document_id=document_id,
                page_number=page_number,
                image_sha256=image_hash,
            )
        if self.offline_model_directory is None:
            raw = self._ocr_failure(
                page_number,
                image_hash,
                status="disabled",
                error="Offline PaddleOCR model directory is not configured.",
            )
            return normalize_ocr_worker_result(
                raw,
                document_id=document_id,
                page_number=page_number,
                image_sha256=image_hash,
            )

        worker = self.repo_root / "workers" / "run_paddleocr.py"
        with tempfile.TemporaryDirectory(prefix="ocr-worker-") as temporary:
            output = Path(temporary) / "result.json"
            command = [
                str(executable),
                str(worker),
                str(path),
                "--page",
                str(page_number),
                "--model-dir",
                str(Path(self.offline_model_directory).resolve()),
                "--out",
                str(output),
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.task_timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raw = self._ocr_failure(
                    page_number, image_hash, status="failed", error="OCR worker timed out."
                )
            except OSError:
                raw = self._ocr_failure(
                    page_number, image_hash, status="failed", error="OCR worker could not be started."
                )
            else:
                raw = None
                if completed.returncode == 0 and output.is_file():
                    try:
                        candidate = json.loads(output.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        candidate = None
                    if isinstance(candidate, dict):
                        raw = candidate
                if (
                    raw is None
                    or raw.get("page_number") != page_number
                    or raw.get("image_sha256") != image_hash
                ):
                    raw = self._ocr_failure(
                        page_number,
                        image_hash,
                        status="failed",
                        error="OCR worker returned invalid or mismatched output.",
                    )

        return normalize_ocr_worker_result(
            raw,
            document_id=document_id,
            page_number=page_number,
            image_sha256=image_hash,
        )

    @staticmethod
    def _ocr_failure(
        page_number: int,
        image_sha256: str,
        *,
        status: str,
        error: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "engine": "paddleocr",
            "status": status,
            "page_number": page_number,
            "image_sha256": image_sha256,
            "items": [],
            "error": error,
            "requested_profile": "offline-cpu",
            "selected_profile": None,
            "selected_models": {},
        }

    def detect_signature_candidates(
        self,
        image_path: str | Path,
        *,
        page_number: int,
        signature_rois: list[tuple[int, int, int, int]],
    ) -> dict[str, Any]:
        path = Path(image_path).resolve()
        executable = self._resolve_python()
        if executable is None:
            return self._candidate_failure(
                path,
                page_number,
                signature_rois,
                status="disabled",
                error="Isolated vision-worker Python is unavailable.",
            )

        worker = self.repo_root / "workers" / "detect_signature_candidates_cv.py"
        with tempfile.TemporaryDirectory(prefix="signature-worker-") as temporary:
            output = Path(temporary) / "result.json"
            command = [
                str(executable),
                str(worker),
                str(path),
                "--page",
                str(page_number),
                "--seal-preferred-min-dimension-ratio",
                str(self.seal_preferred_min_dimension_ratio),
                "--seal-preferred-max-area-ratio",
                str(self.seal_preferred_max_area_ratio),
                "--out",
                str(output),
            ]
            for roi in signature_rois:
                command.extend(["--signature-roi", ",".join(str(value) for value in roi)])
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.task_timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return self._candidate_failure(
                    path,
                    page_number,
                    signature_rois,
                    status="failed",
                    error="Signature candidate worker timed out.",
                )
            except OSError:
                return self._candidate_failure(
                    path,
                    page_number,
                    signature_rois,
                    status="failed",
                    error="Signature candidate worker could not be started.",
                )

            if output.is_file():
                try:
                    payload = json.loads(output.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = None
                if isinstance(payload, dict):
                    return payload
            return self._candidate_failure(
                path,
                page_number,
                signature_rois,
                status="failed",
                error=(
                    "Signature candidate worker returned invalid output."
                    if completed.returncode != 0
                    else "Signature candidate worker produced no result."
                ),
            )

    @staticmethod
    def _candidate_failure(
        path: Path,
        page_number: int,
        signature_rois: list[tuple[int, int, int, int]],
        *,
        status: str,
        error: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "engine": "opencv",
            "status": status,
            "page_number": page_number,
            "image_sha256": _sha256(path),
            "canvas": None,
            "candidates": [],
            "count": 0,
            "error": error,
            "metadata": {
                "method": "signature-seal-candidates-cv-v1",
                "authenticity_check": False,
                "signature_roi_count": len(signature_rois),
            },
        }
