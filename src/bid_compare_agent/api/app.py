from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated, Any, Callable
from zipfile import BadZipFile

from docx.opc.exceptions import PackageNotFoundError
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pymupdf import FileDataError
from starlette.background import BackgroundTask

from bid_compare_agent import __version__

from .pipeline import ApiPipeline, findings_from_payload
from .uploads import (
    DEFAULT_MAX_UPLOAD_BYTES,
    ApiInputError,
    persist_upload,
    persist_uploads,
)


API_VERSION = "1.0.0"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _envelope(operation: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"api_version": API_VERSION, "operation": operation, "result": result}


async def _run_pipeline(function: Callable[..., dict[str, Any]], *args: Any) -> dict[str, Any]:
    try:
        return await run_in_threadpool(function, *args)
    except (BadZipFile, FileDataError, PackageNotFoundError, ValueError) as exc:
        raise ApiInputError("invalid_input", str(exc), status_code=422) from exc


def create_app(
    *,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    pipeline: ApiPipeline | None = None,
) -> FastAPI:
    application = FastAPI(
        title="Bid Compare Agent API",
        version=__version__,
        description="投标文件解析、比对、辅助分析、评分与 Word 批注 HTTP API",
    )
    application.state.pipeline = pipeline or ApiPipeline()
    application.state.max_upload_bytes = max_upload_bytes

    @application.exception_handler(ApiInputError)
    async def api_input_error_handler(_request: Request, exc: ApiInputError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request_validation_error",
                    "message": "请求字段校验失败",
                }
            },
        )

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "bid-compare-agent",
            "version": __version__,
            "api_version": API_VERSION,
        }

    @application.post("/v1/parse", tags=["documents"])
    async def parse_endpoint(
        file: Annotated[UploadFile, File(description="单个 DOCX/PDF 文件")],
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bid-compare-api-") as raw_dir:
            path = await persist_upload(
                file,
                Path(raw_dir) / "source",
                max_bytes=application.state.max_upload_bytes,
            )
            result = await _run_pipeline(application.state.pipeline.parse, path)
        return _envelope("parse", result)

    @application.post("/v1/preprocess", tags=["documents"])
    async def preprocess_endpoint(
        file: Annotated[UploadFile, File(description="单个 DOCX/PDF 文件")],
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bid-compare-api-") as raw_dir:
            path = await persist_upload(
                file,
                Path(raw_dir) / "source",
                max_bytes=application.state.max_upload_bytes,
            )
            result = await _run_pipeline(application.state.pipeline.preprocess, path)
        return _envelope("preprocess", result)

    async def save_document_set(
        files: list[UploadFile],
        raw_dir: str,
        *,
        minimum: int,
    ) -> list[Path]:
        return await persist_uploads(
            files,
            Path(raw_dir),
            minimum=minimum,
            maximum=5,
            max_bytes=application.state.max_upload_bytes,
        )

    @application.post("/v1/text-compare", tags=["analysis"])
    async def text_compare_endpoint(
        files: Annotated[list[UploadFile], File(description="2-5 个 DOCX/PDF 文件")],
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bid-compare-api-") as raw_dir:
            paths = await save_document_set(files, raw_dir, minimum=2)
            result = await _run_pipeline(application.state.pipeline.text_compare, paths)
        return _envelope("text_compare", result)

    @application.post("/v1/image-compare", tags=["analysis"])
    async def image_compare_endpoint(
        files: Annotated[list[UploadFile], File(description="2-5 个 DOCX/PDF 文件")],
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bid-compare-api-") as raw_dir:
            paths = await save_document_set(files, raw_dir, minimum=2)
            result = await _run_pipeline(application.state.pipeline.image_compare, paths)
        return _envelope("image_compare", result)

    @application.post("/v1/format-check", tags=["analysis"])
    async def format_check_endpoint(
        files: Annotated[list[UploadFile], File(description="1-5 个 DOCX/PDF 文件")],
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bid-compare-api-") as raw_dir:
            paths = await save_document_set(files, raw_dir, minimum=1)
            result = await _run_pipeline(application.state.pipeline.format_check, paths)
        return _envelope("format_check", result)

    @application.post("/v1/ai-check", tags=["analysis"])
    async def ai_check_endpoint(
        files: Annotated[list[UploadFile], File(description="1-5 个 DOCX/PDF 文件")],
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bid-compare-api-") as raw_dir:
            paths = await save_document_set(files, raw_dir, minimum=1)
            result = await _run_pipeline(application.state.pipeline.ai_check, paths)
        return _envelope("ai_check", result)

    @application.post("/v1/score", tags=["analysis"])
    async def score_endpoint(
        files: Annotated[list[UploadFile], File(description="2-5 个 DOCX/PDF 文件")],
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bid-compare-api-") as raw_dir:
            paths = await save_document_set(files, raw_dir, minimum=2)
            result = await _run_pipeline(application.state.pipeline.score, paths)
        return _envelope("score", result)

    @application.post(
        "/v1/annotate-docx",
        tags=["annotations"],
        response_class=FileResponse,
        responses={200: {"content": {DOCX_MEDIA_TYPE: {}}}},
    )
    async def annotate_docx_endpoint(
        file: Annotated[UploadFile, File(description="待批注 DOCX")],
        findings_json: Annotated[str, Form(description="Finding 数组或含 findings 字段的 JSON")],
    ) -> FileResponse:
        try:
            payload = json.loads(findings_json)
            findings = findings_from_payload(payload)
        except json.JSONDecodeError as exc:
            raise ApiInputError("invalid_findings_json", "findings_json 不是有效 JSON", 422) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiInputError("invalid_findings", str(exc), 422) from exc

        temporary = tempfile.TemporaryDirectory(prefix="bid-compare-api-")
        try:
            root = Path(temporary.name)
            source = await persist_upload(
                file,
                root / "source",
                max_bytes=application.state.max_upload_bytes,
                allowed_suffixes={".docx"},
            )
            output = root / "output" / f"{source.stem}.annotated.docx"
            result = await _run_pipeline(
                application.state.pipeline.annotate,
                source,
                output,
                findings,
            )
            summary = result["summary"]
            return FileResponse(
                output,
                filename=output.name,
                media_type=DOCX_MEDIA_TYPE,
                headers={
                    "X-Annotation-Count": str(summary["annotated_comments"]),
                    "X-Skipped-Count": str(summary["skipped_findings"]),
                    "X-Output-SHA256": str(result["metadata"]["output_sha256"]),
                },
                background=BackgroundTask(temporary.cleanup),
            )
        except Exception:
            temporary.cleanup()
            raise

    return application


app = create_app()
