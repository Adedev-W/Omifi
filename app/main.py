import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db import Database
from .errors import AppError, app_error_handler, general_error_handler, validation_error_handler
from .schemas import (
    CheckLatexResponse,
    CreateDocumentRequest,
    DocumentResponse,
    FileResponse as FileMetadataResponse,
    JudgeReportRequest,
    JudgeReportResponse,
    RenderResponse,
    VersionRefRequest,
    VersionRequest,
)
from .security import require_api_key
from .services import (
    check_version,
    create_document,
    create_version,
    file_content,
    get_artifact,
    get_document,
    list_files,
    cleanup_expired_artifacts,
    render_version,
    save_report,
    upload_file,
)

logger = logging.getLogger("cv_automation")
_DOCUMENT_PATH = re.compile(r"/v1/documents/([^/]+)")
_ARTIFACT_PATH = re.compile(r"/v1/artifacts/([^/]+)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.ensure_directories()
    await app.state.db.create_schema()
    async with app.state.db.session_context() as session:
        await cleanup_expired_artifacts(session, settings)
    yield
    await app.state.db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(title="Omifi Backend", version="1.0.0", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.db = Database(resolved_settings)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, general_error_handler)
    from fastapi.exceptions import RequestValidationError

    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        document_match = _DOCUMENT_PATH.search(request.url.path)
        artifact_match = _ARTIFACT_PATH.search(request.url.path)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            logger.info(json.dumps({
                    "event": "request_complete",
                    "request_id": request_id,
                    "operation": f"{request.method} {request.url.path}",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "status_code": status_code,
                    "document_id": document_match.group(1) if document_match else None,
                    "artifact_id": artifact_match.group(1) if artifact_match else None,
                }))

    async def session_dependency(request: Request):
        async with request.app.state.db.session_context() as session:
            yield session

    Session = Depends(session_dependency)
    Protected = Depends(require_api_key)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/files", response_model=FileMetadataResponse, dependencies=[Protected])
    async def upload(file: UploadFile = File(...), session: AsyncSession = Session):
        content = await file.read(resolved_settings.max_upload_bytes + 1)
        return await upload_file(session, resolved_settings, file.filename or "upload.tex", file.content_type or "application/octet-stream", content)

    @app.get("/v1/files", response_model=list[FileMetadataResponse], dependencies=[Protected])
    async def files(session: AsyncSession = Session):
        return await list_files(session)

    @app.get("/v1/files/{file_id}/download", dependencies=[Protected])
    async def download_file(file_id: str, session: AsyncSession = Session):
        record, content = await file_content(session, resolved_settings, file_id)
        return Response(
            content=content,
            media_type=record.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{record.filename}"',
                "X-File-ID": record.id,
                "X-File-SHA256": record.sha256,
            },
        )

    @app.post("/v1/documents", response_model=DocumentResponse, dependencies=[Protected])
    async def documents(request: CreateDocumentRequest, session: AsyncSession = Session):
        outcome = await create_document(session, resolved_settings, request)
        if outcome.version.compile_status == "failed":
            raise AppError("LATEX_COMPILE_FAILED", "Initial LaTeX source is invalid", 422, {"document_id": outcome.version.document_id, "version_id": outcome.version.id, "source_latex": outcome.version.source_latex, "compile_error": outcome.version.compile_error})
        return await get_document(session, resolved_settings, outcome.version.document_id)

    @app.get("/v1/documents/{document_id}", response_model=DocumentResponse, dependencies=[Protected])
    async def document(document_id: str, session: AsyncSession = Session):
        return await get_document(session, resolved_settings, document_id)

    @app.post("/v1/documents/{document_id}/versions", response_model=DocumentResponse, dependencies=[Protected])
    async def version(document_id: str, request: VersionRequest, session: AsyncSession = Session):
        outcome = await create_version(session, resolved_settings, document_id, request.base_version_id, request.source_latex, request.change_summary)
        if outcome.version.compile_status == "failed":
            raise AppError("LATEX_COMPILE_FAILED", "LaTeX source is invalid or compilation failed", 422, {"document_id": document_id, "version_id": outcome.version.id, "source_latex": outcome.version.source_latex, "compile_error": outcome.version.compile_error})
        return await get_document(session, resolved_settings, document_id)

    @app.post("/v1/documents/{document_id}/check-latex", response_model=CheckLatexResponse, dependencies=[Protected])
    async def check_latex(document_id: str, request: VersionRefRequest, session: AsyncSession = Session):
        version_record, valid, errors, warnings, compile_status = await check_version(session, resolved_settings, document_id, request.version_id, request.dry_run_compile)
        return CheckLatexResponse(document_id=document_id, version_id=version_record.id, valid=valid, errors=errors, warnings=warnings, compile_status=compile_status)

    @app.post("/v1/documents/{document_id}/render", response_model=RenderResponse, dependencies=[Protected])
    async def render(document_id: str, request: VersionRefRequest, session: AsyncSession = Session):
        return await render_version(session, resolved_settings, document_id, request.version_id)

    @app.post("/v1/documents/{document_id}/reports", response_model=JudgeReportResponse, dependencies=[Protected])
    async def report(document_id: str, request: JudgeReportRequest, session: AsyncSession = Session):
        return await save_report(session, document_id, request)

    @app.get("/v1/artifacts/{artifact_id}/preview", dependencies=[Protected])
    async def preview_artifact(artifact_id: str, session: AsyncSession = Session):
        artifact, path = await get_artifact(session, resolved_settings, artifact_id)
        return Response(content=path.read_bytes(), media_type=artifact.media_type, headers={"Content-Disposition": "inline"})

    @app.get("/v1/artifacts/{artifact_id}/download", dependencies=[Protected])
    async def download_artifact(artifact_id: str, session: AsyncSession = Session):
        artifact, path = await get_artifact(session, resolved_settings, artifact_id)
        return Response(
            content=path.read_bytes(),
            media_type=artifact.media_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact_id}.pdf"'},
        )

    return app


app = create_app()
