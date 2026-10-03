from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pymupdf


class PageRenderingError(RuntimeError):
    """A sanitized page-rendering failure safe to expose in local manifests."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_match_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _docx_match_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as package:
            root = ElementTree.fromstring(package.read("word/document.xml"))
    except (KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise PageRenderingError(
            "source_docx_invalid",
            "DOCX content could not be read for canonical PDF verification.",
        ) from exc
    return _normalize_match_text(
        "".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    )


def _pdf_match_text(path: Path) -> tuple[str, int]:
    try:
        with pymupdf.open(path) as document:
            return (
                _normalize_match_text("".join(page.get_text() for page in document)),
                document.page_count,
            )
    except Exception as exc:
        raise PageRenderingError(
            "canonical_pdf_invalid",
            "Canonical PDF content could not be read.",
        ) from exc


def _sampled_shingle_match(
    source: str,
    target: str,
    *,
    shingle_size: int = 64,
    sample_limit: int = 300,
) -> dict[str, int | float]:
    if len(source) < shingle_size or len(target) < shingle_size:
        return {"sample_count": 0, "matched_count": 0, "match_rate": 0.0}
    final_start = len(source) - shingle_size
    step = max(shingle_size, max(1, final_start // max(1, sample_limit - 1)))
    positions = list(range(0, final_start + 1, step))[:sample_limit]
    if positions and positions[-1] != final_start and len(positions) < sample_limit:
        positions.append(final_start)
    matched = sum(source[position : position + shingle_size] in target for position in positions)
    return {
        "sample_count": len(positions),
        "matched_count": matched,
        "match_rate": round(matched / len(positions), 6),
    }


def _canonical_pdf_contract(
    docx_path: Path,
    pdf_path: Path,
    *,
    minimum_text_match: float,
) -> dict[str, Any]:
    docx_text = _docx_match_text(docx_path)
    pdf_text, page_count = _pdf_match_text(pdf_path)
    docx_to_pdf = _sampled_shingle_match(docx_text, pdf_text)
    pdf_to_docx = _sampled_shingle_match(pdf_text, docx_text)
    matched = (
        docx_to_pdf["sample_count"] > 0
        and pdf_to_docx["sample_count"] > 0
        and docx_to_pdf["match_rate"] >= minimum_text_match
        and pdf_to_docx["match_rate"] >= minimum_text_match
    )
    source_hash = _sha256(pdf_path)
    return {
        "source_sha256": source_hash,
        "page_count": page_count,
        "integrity": {
            "source_sha256_before": source_hash,
            "source_sha256_after": source_hash,
            "source_unchanged": True,
        },
        "content_match": {
            "method": "normalized-alphanumeric-shingle-v1",
            "shingle_size": 64,
            "sample_limit": 300,
            "minimum_bidirectional_match": minimum_text_match,
            "docx_to_pdf": docx_to_pdf,
            "pdf_to_docx": pdf_to_docx,
            "matched": matched,
        },
    }


def _refresh_canonical_integrity(contract: dict[str, Any], pdf_path: Path) -> None:
    source_hash_after = _sha256(pdf_path)
    integrity = contract["integrity"]
    integrity["source_sha256_after"] = source_hash_after
    integrity["source_unchanged"] = (
        integrity["source_sha256_before"] == source_hash_after
    )


def _find_docx_renderer(explicit: str | Path | None) -> Path | None:
    if explicit is not None:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate.resolve()
        discovered = shutil.which(str(explicit))
        return Path(discovered).resolve() if discovered else None

    for name in ("soffice", "libreoffice"):
        discovered = shutil.which(name)
        if discovered:
            return Path(discovered).resolve()
    for environment_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(environment_name)
        if not base:
            continue
        candidate = Path(base) / "LibreOffice" / "program" / "soffice.exe"
        if candidate.is_file():
            return candidate.resolve()
    return None


def _convert_docx_to_pdf(
    source: Path,
    work_dir: Path,
    renderer: Path,
    timeout_seconds: int,
) -> Path:
    profile_dir = work_dir / "libreoffice-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(renderer),
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--headless",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(work_dir),
        str(source),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PageRenderingError(
            "docx_conversion_timeout",
            "DOCX conversion exceeded the configured timeout.",
        ) from exc
    except OSError as exc:
        raise PageRenderingError(
            "docx_renderer_start_failed",
            "DOCX renderer could not be started.",
        ) from exc

    converted = work_dir / f"{source.stem}.pdf"
    if completed.returncode != 0 or not converted.is_file():
        raise PageRenderingError(
            "docx_conversion_failed",
            "DOCX renderer did not produce a PDF.",
        )
    return converted


def _render_pdf_pages(
    pdf_path: Path,
    staging_dir: Path,
    *,
    source_hash: str,
    dpi: int,
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    try:
        with pymupdf.open(pdf_path) as document:
            if document.page_count < 1:
                raise PageRenderingError("empty_document", "Document contains no pages.")
            for page_index, page in enumerate(document):
                pixmap = page.get_pixmap(
                    matrix=matrix,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                filename = (
                    f"{source_hash[:16]}-page-{page_index + 1:04d}-dpi-{dpi}.png"
                )
                image_path = staging_dir / filename
                pixmap.save(image_path)
                pages.append(
                    {
                        "page_number": page_index + 1,
                        "image": filename,
                        "image_sha256": _sha256(image_path),
                        "width": pixmap.width,
                        "height": pixmap.height,
                    }
                )
    except PageRenderingError:
        raise
    except Exception as exc:
        raise PageRenderingError(
            "pdf_render_failed",
            "PDF pages could not be rendered.",
        ) from exc
    return pages


def _publish_pages(
    staging_dir: Path,
    output_dir: Path,
    pages: list[dict[str, Any]],
) -> None:
    pending: list[tuple[Path, Path]] = []
    for page in pages:
        source = staging_dir / page["image"]
        destination = output_dir / page["image"]
        if destination.exists():
            if _sha256(destination) != page["image_sha256"]:
                raise PageRenderingError(
                    "output_conflict",
                    "An existing rendered page has unexpected content.",
                )
            continue
        pending.append((source, destination))

    published: list[Path] = []
    try:
        for source, destination in pending:
            source.replace(destination)
            published.append(destination)
    except OSError as exc:
        for destination in published:
            destination.unlink(missing_ok=True)
        raise PageRenderingError(
            "output_write_failed",
            "Rendered pages could not be published atomically.",
        ) from exc


def _result(
    *,
    status: str,
    source_type: str,
    source_hash_before: str,
    source_hash_after: str,
    dpi: int,
    backend: str,
    timeout_seconds: int,
    pages: list[dict[str, Any]],
    error: dict[str, str] | None,
    canonical_pdf: dict[str, Any] | None = None,
    warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.1.0",
        "status": status,
        "source_type": source_type,
        "source_sha256": source_hash_before,
        "page_count": len(pages),
        "pages": pages,
        "renderer": {
            "backend": backend,
            "format": "png",
            "dpi": dpi,
            "docx_conversion_timeout_seconds": timeout_seconds,
            "authenticity_check": False,
        },
        "integrity": {
            "source_sha256_before": source_hash_before,
            "source_sha256_after": source_hash_after,
            "source_unchanged": source_hash_before == source_hash_after,
        },
        "canonical_pdf": canonical_pdf,
        "warnings": warnings or [],
        "error": error,
    }


def render_document_pages(
    source: str | Path,
    output_dir: str | Path,
    *,
    dpi: int = 150,
    docx_renderer: str | Path | None = None,
    timeout_seconds: int = 120,
    canonical_pdf: str | Path | None = None,
    canonical_pdf_minimum_text_match: float = 0.7,
) -> dict[str, Any]:
    """Render PDF or DOCX pages without exposing source paths in the result.

    PDF files are rendered directly with PyMuPDF. A DOCX can use a verified
    same-source canonical PDF to preserve authoritative pagination. Otherwise,
    DOCX files require an isolated LibreOffice-compatible executable and are
    first converted inside a temporary directory. Page images are only moved
    to ``output_dir`` after all input hashes have been verified unchanged.
    """

    source_path = Path(source).resolve()
    output_path = Path(output_dir).resolve()
    if not source_path.is_file():
        raise ValueError("source document does not exist")
    source_type = source_path.suffix.lower().lstrip(".")
    if source_type not in {"pdf", "docx"}:
        raise ValueError("only PDF and DOCX page rendering is supported")
    if not 72 <= dpi <= 600:
        raise ValueError("dpi must be between 72 and 600")
    if not 1 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be between 1 and 3600")
    if not 0 <= canonical_pdf_minimum_text_match <= 1:
        raise ValueError("canonical_pdf_minimum_text_match must be between 0 and 1")

    canonical_path: Path | None = None
    canonical_contract: dict[str, Any] | None = None
    if canonical_pdf is not None:
        if source_type != "docx":
            raise ValueError("canonical_pdf is only supported for DOCX sources")
        canonical_path = Path(canonical_pdf).resolve()
        if not canonical_path.is_file() or canonical_path.suffix.lower() != ".pdf":
            raise ValueError("canonical_pdf must be an existing PDF file")

    source_hash_before = _sha256(source_path)
    output_path.mkdir(parents=True, exist_ok=True)
    if canonical_path is not None:
        backend = "canonical-pdf+pymupdf"
        try:
            canonical_contract = _canonical_pdf_contract(
                source_path,
                canonical_path,
                minimum_text_match=canonical_pdf_minimum_text_match,
            )
        except PageRenderingError as exc:
            source_hash_after = _sha256(source_path)
            return _result(
                status="failed",
                source_type=source_type,
                source_hash_before=source_hash_before,
                source_hash_after=source_hash_after,
                dpi=dpi,
                backend=backend,
                timeout_seconds=timeout_seconds,
                pages=[],
                error={"code": exc.code, "message": str(exc)},
            )
        if not canonical_contract["content_match"]["matched"]:
            _refresh_canonical_integrity(canonical_contract, canonical_path)
            source_hash_after = _sha256(source_path)
            return _result(
                status="failed",
                source_type=source_type,
                source_hash_before=source_hash_before,
                source_hash_after=source_hash_after,
                dpi=dpi,
                backend=backend,
                timeout_seconds=timeout_seconds,
                pages=[],
                error={
                    "code": "canonical_pdf_content_mismatch",
                    "message": "Canonical PDF did not meet the bidirectional text-match threshold.",
                },
                canonical_pdf=canonical_contract,
            )
    else:
        backend = "pymupdf" if source_type == "pdf" else "libreoffice+pymupdf"

    if source_type == "docx" and canonical_path is None:
        resolved_renderer = _find_docx_renderer(docx_renderer)
        if resolved_renderer is None:
            source_hash_after = _sha256(source_path)
            return _result(
                status="unavailable",
                source_type=source_type,
                source_hash_before=source_hash_before,
                source_hash_after=source_hash_after,
                dpi=dpi,
                backend=backend,
                timeout_seconds=timeout_seconds,
                pages=[],
                error={
                    "code": "docx_renderer_unavailable",
                    "message": "No LibreOffice-compatible DOCX renderer is available.",
                },
            )

    with tempfile.TemporaryDirectory(prefix="page-render-") as temporary:
        work_dir = Path(temporary)
        staging_dir = work_dir / "pages"
        staging_dir.mkdir()
        try:
            if source_type == "docx":
                if canonical_path is not None:
                    pdf_path = canonical_path
                else:
                    pdf_path = _convert_docx_to_pdf(
                        source_path,
                        work_dir,
                        resolved_renderer,
                        timeout_seconds,
                    )
            else:
                pdf_path = source_path
            pages = _render_pdf_pages(
                pdf_path,
                staging_dir,
                source_hash=(
                    canonical_contract["source_sha256"]
                    if canonical_contract is not None
                    else source_hash_before
                ),
                dpi=dpi,
            )
            source_hash_after = _sha256(source_path)
            if source_hash_after != source_hash_before:
                raise PageRenderingError(
                    "source_mutated",
                    "Source document changed during page rendering.",
                )
            if canonical_contract is not None and canonical_path is not None:
                _refresh_canonical_integrity(canonical_contract, canonical_path)
                if not canonical_contract["integrity"]["source_unchanged"]:
                    raise PageRenderingError(
                        "canonical_pdf_mutated",
                        "Canonical PDF changed during page rendering.",
                    )
            _publish_pages(staging_dir, output_path, pages)
        except PageRenderingError as exc:
            source_hash_after = _sha256(source_path)
            return _result(
                status="failed",
                source_type=source_type,
                source_hash_before=source_hash_before,
                source_hash_after=source_hash_after,
                dpi=dpi,
                backend=backend,
                timeout_seconds=timeout_seconds,
                pages=[],
                error={"code": exc.code, "message": str(exc)},
                canonical_pdf=canonical_contract,
            )

    return _result(
        status="ok",
        source_type=source_type,
        source_hash_before=source_hash_before,
        source_hash_after=source_hash_after,
        dpi=dpi,
        backend=backend,
        timeout_seconds=timeout_seconds,
        pages=pages,
        error=None,
        canonical_pdf=canonical_contract,
        warnings=(
            [
                {
                    "code": "canonical_pdf_used",
                    "message": "Verified same-source PDF supplied the canonical page layout.",
                }
            ]
            if canonical_contract is not None
            else []
        ),
    )
