from __future__ import annotations

from pathlib import Path
from typing import Sequence

from fastapi import UploadFile


CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
SUPPORTED_DOCUMENT_SUFFIXES = {".docx", ".pdf"}


class ApiInputError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def safe_filename(filename: str | None) -> str:
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."}:
        raise ApiInputError("invalid_filename", "上传文件名不能为空")
    return name


def validate_file_count(files: Sequence[UploadFile], minimum: int, maximum: int) -> None:
    if not minimum <= len(files) <= maximum:
        raise ApiInputError(
            "invalid_file_count",
            f"文件数量必须在 {minimum}-{maximum} 之间，实际收到 {len(files)} 个",
        )


async def persist_upload(
    upload: UploadFile,
    directory: Path,
    *,
    max_bytes: int,
    allowed_suffixes: set[str] | None = None,
) -> Path:
    filename = safe_filename(upload.filename)
    suffix = Path(filename).suffix.lower()
    allowed = allowed_suffixes or SUPPORTED_DOCUMENT_SUFFIXES
    if suffix not in allowed:
        supported = ", ".join(sorted(allowed))
        raise ApiInputError(
            "unsupported_file_type",
            f"不支持的文件格式 {suffix or '(无扩展名)'}；当前支持 {supported}",
            status_code=415,
        )

    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    total = 0
    try:
        with target.open("wb") as handle:
            while chunk := await upload.read(CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise ApiInputError(
                        "file_too_large",
                        f"文件 {filename} 超过 {max_bytes} 字节上限",
                        status_code=413,
                    )
                handle.write(chunk)
    finally:
        await upload.close()
    return target


async def persist_uploads(
    files: Sequence[UploadFile],
    directory: Path,
    *,
    minimum: int,
    maximum: int,
    max_bytes: int,
    allowed_suffixes: set[str] | None = None,
) -> list[Path]:
    validate_file_count(files, minimum, maximum)
    paths: list[Path] = []
    for index, upload in enumerate(files):
        paths.append(
            await persist_upload(
                upload,
                directory / f"file-{index:02d}",
                max_bytes=max_bytes,
                allowed_suffixes=allowed_suffixes,
            )
        )
    return paths
