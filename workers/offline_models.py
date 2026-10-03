#!/usr/bin/env python3
"""Validate and describe explicitly staged PaddleOCR model directories."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


MANIFEST_SCHEMA_VERSION = "2.0.0"
MODEL_KINDS = frozenset({"detection", "recognition", "classification"})
REQUIRED_MODEL_KINDS = frozenset({"detection", "recognition"})


class ModelManifestError(ValueError):
    """Raised when an offline model package fails its integrity contract."""


@dataclass(frozen=True)
class VerifiedModel:
    model_id: str
    kind: str
    model_name: str
    directory: Path
    files: tuple[Path, ...]


@dataclass(frozen=True)
class VerifiedModelPackage:
    root: Path
    models: tuple[VerifiedModel, ...]

    def require(self, kind: str) -> VerifiedModel:
        matches = [model for model in self.models if model.kind == kind]
        if len(matches) != 1:
            raise ModelManifestError(f"offline package must contain exactly one {kind} model")
        return matches[0]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(value: Any, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ModelManifestError(f"{field} must be a non-empty POSIX relative path")
    if not value.isascii():
        raise ModelManifestError(f"{field} must use ASCII characters for Paddle runtime compatibility")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ModelManifestError(f"{field} must remain inside the model package")
    return path


def _safe_target(root: Path, relative: PurePosixPath, field: str) -> Path:
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ModelManifestError(f"{field} cannot traverse a symbolic link")
    try:
        candidate.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise ModelManifestError(f"{field} must remain inside the model package") from exc
    return candidate


def _parse_payload(root: Path) -> dict[str, Any]:
    manifest_path = root / "model_manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelManifestError("offline model manifest is unreadable") from exc
    if not isinstance(payload, dict):
        raise ModelManifestError("offline model manifest must be an object")
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ModelManifestError("unsupported offline model manifest schema")
    if set(payload) != {"schema_version", "models"}:
        raise ModelManifestError("offline model manifest contains unsupported fields")
    return payload


def verify_model_package(directory: str | Path) -> VerifiedModelPackage:
    original_root = Path(directory)
    if original_root.is_symlink():
        raise ModelManifestError("offline model package root cannot be a symbolic link")
    root = original_root.resolve()
    if not root.is_dir():
        raise ModelManifestError("offline model package directory is unavailable")
    payload = _parse_payload(root)
    raw_models = payload.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ModelManifestError("offline model manifest models must be a non-empty array")

    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    verified: list[VerifiedModel] = []
    for index, raw_model in enumerate(raw_models):
        field = f"models[{index}]"
        if not isinstance(raw_model, dict) or set(raw_model) != {
            "id",
            "kind",
            "model_name",
            "relative_directory",
            "files",
        }:
            raise ModelManifestError(f"{field} has invalid fields")
        model_id = raw_model.get("id")
        kind = raw_model.get("kind")
        model_name = raw_model.get("model_name")
        if not isinstance(model_id, str) or not model_id.strip() or model_id in seen_ids:
            raise ModelManifestError(f"{field}.id must be non-empty and unique")
        if kind not in MODEL_KINDS or kind in seen_kinds:
            raise ModelManifestError(f"{field}.kind must be supported and unique")
        if not isinstance(model_name, str) or not model_name.strip():
            raise ModelManifestError(f"{field}.model_name must be non-empty")
        relative_directory = _relative_path(
            raw_model.get("relative_directory"), f"{field}.relative_directory"
        )
        model_directory = _safe_target(root, relative_directory, f"{field}.relative_directory")
        if not model_directory.is_dir():
            raise ModelManifestError(f"{field}.relative_directory is unavailable")

        raw_files = raw_model.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ModelManifestError(f"{field}.files must be a non-empty array")
        declared: set[str] = set()
        verified_files: list[Path] = []
        for file_index, raw_file in enumerate(raw_files):
            file_field = f"{field}.files[{file_index}]"
            if not isinstance(raw_file, dict) or set(raw_file) != {"relative_path", "sha256"}:
                raise ModelManifestError(f"{file_field} has invalid fields")
            relative_file = _relative_path(raw_file.get("relative_path"), f"{file_field}.relative_path")
            relative_key = relative_file.as_posix()
            expected_hash = raw_file.get("sha256")
            if relative_key in declared:
                raise ModelManifestError(f"{file_field}.relative_path must be unique")
            if (
                not isinstance(expected_hash, str)
                or len(expected_hash) != 64
                or any(character not in "0123456789abcdef" for character in expected_hash)
            ):
                raise ModelManifestError(f"{file_field}.sha256 must be lowercase hexadecimal")
            target = _safe_target(model_directory, relative_file, f"{file_field}.relative_path")
            if not target.is_file():
                raise ModelManifestError(f"{file_field}.relative_path is unavailable")
            try:
                actual_hash = sha256_file(target)
            except OSError as exc:
                raise ModelManifestError(f"{file_field}.relative_path is unreadable") from exc
            if actual_hash != expected_hash:
                raise ModelManifestError(f"{file_field}.sha256 does not match")
            declared.add(relative_key)
            verified_files.append(target)

        actual: set[str] = set()
        for target in model_directory.rglob("*"):
            if target.is_symlink():
                raise ModelManifestError(f"{field} cannot contain symbolic links")
            if target.is_file():
                actual.add(target.relative_to(model_directory).as_posix())
        if actual != declared:
            raise ModelManifestError(f"{field}.files must declare every model file")

        seen_ids.add(model_id)
        seen_kinds.add(kind)
        verified.append(
            VerifiedModel(
                model_id=model_id,
                kind=kind,
                model_name=model_name,
                directory=model_directory,
                files=tuple(verified_files),
            )
        )

    if not REQUIRED_MODEL_KINDS.issubset(seen_kinds):
        raise ModelManifestError("offline model package requires detection and recognition models")
    return VerifiedModelPackage(root=root, models=tuple(verified))


def public_model_state(directory: str | Path | None) -> dict[str, Any]:
    if directory is None:
        return {"configured": False, "manifest_valid": False, "model_count": 0}
    try:
        package = verify_model_package(directory)
    except (ModelManifestError, OSError):
        return {"configured": True, "manifest_valid": False, "model_count": 0}
    return {"configured": True, "manifest_valid": True, "model_count": len(package.models)}


def build_manifest(
    root: str | Path,
    models: Iterable[tuple[str, str, str, str | Path]],
) -> dict[str, Any]:
    package_root = Path(root).resolve()
    payload_models: list[dict[str, Any]] = []
    for model_id, kind, model_name, directory in models:
        if kind not in MODEL_KINDS:
            raise ModelManifestError(f"unsupported model kind: {kind}")
        model_directory = Path(directory).resolve()
        try:
            relative_directory = model_directory.relative_to(package_root).as_posix()
        except ValueError as exc:
            raise ModelManifestError("model directory must be inside the package root") from exc
        files: list[dict[str, str]] = []
        for target in sorted(model_directory.rglob("*")):
            if target.is_symlink():
                raise ModelManifestError("model directory cannot contain symbolic links")
            if target.is_file():
                files.append(
                    {
                        "relative_path": target.relative_to(model_directory).as_posix(),
                        "sha256": sha256_file(target),
                    }
                )
        if not files:
            raise ModelManifestError("model directory must contain at least one file")
        payload_models.append(
            {
                "id": model_id,
                "kind": kind,
                "model_name": model_name,
                "relative_directory": relative_directory,
                "files": files,
            }
        )
    return {"schema_version": MANIFEST_SCHEMA_VERSION, "models": payload_models}
