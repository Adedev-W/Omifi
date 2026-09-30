import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import Settings
from .errors import AppError
from .latex_engine import CompileResult, compile_source, normalize_source, validate_source
from .models import Artifact, Document, DocumentVersion, FileRecord, JudgeReport
from .schemas import (
    ArtifactResponse,
    CreateDocumentRequest,
    DocumentResponse,
    FileResponse,
    JudgeReportRequest,
    JudgeReportResponse,
    RenderResponse,
    Scores,
    VersionResponse,
)
from .storage import artifact_path, read_workspace_file, safe_filename, sha256_bytes, write_workspace_file
from .utils import new_id, utcnow


@dataclass
class CompileOutcome:
    version: DocumentVersion
    warnings: list[str]


def _artifact_response(artifact: Artifact, settings: Settings) -> ArtifactResponse:
    base = settings.public_base_url.rstrip("/")
    return ArtifactResponse(
        artifact_id=artifact.id,
        document_version_id=artifact.document_version_id,
        kind=artifact.kind,
        media_type=artifact.media_type,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        status=artifact.status,
        created_at=artifact.created_at,
        preview_url=f"{base}/v1/artifacts/{artifact.id}/preview",
        download_url=f"{base}/v1/artifacts/{artifact.id}/download",
    )


def _version_response(version: DocumentVersion, settings: Settings) -> VersionResponse:
    return VersionResponse(
        version_id=version.id,
        document_id=version.document_id,
        parent_version_id=version.parent_version_id,
        source_latex=version.source_latex,
        source_sha256=version.source_sha256,
        change_summary=version.change_summary,
        compile_status=version.compile_status,
        compile_error=version.compile_error,
        created_at=version.created_at,
        artifacts=[_artifact_response(item, settings) for item in version.artifacts],
    )


async def get_file(session: AsyncSession, file_id: str) -> FileRecord:
    record = await session.get(FileRecord, file_id)
    if record is None:
        raise AppError("FILE_NOT_FOUND", "File was not found", 404)
    return record


async def upload_file(session: AsyncSession, settings: Settings, filename: str, media_type: str, content: bytes) -> FileResponse:
    if len(content) > settings.max_upload_bytes:
        raise AppError("VALIDATION_ERROR", "Uploaded file exceeds the configured size limit", 422)
    clean_name = safe_filename(filename)
    normalized_media_type = (media_type or "application/octet-stream").lower()
    accepted_suffixes = {".tex", ".txt"}
    if Path(clean_name).suffix.lower() not in accepted_suffixes and not normalized_media_type.startswith("text/") and normalized_media_type != "application/x-tex":
        raise AppError("VALIDATION_ERROR", "Only .tex or plain-text files are accepted", 422)
    file_id = new_id("file")
    relative_path = write_workspace_file(settings, file_id, clean_name, content)
    record = FileRecord(
        id=file_id,
        filename=clean_name,
        relative_path=relative_path,
        media_type=normalized_media_type,
        size_bytes=len(content),
        sha256=sha256_bytes(content),
        created_at=utcnow(),
    )
    session.add(record)
    await session.commit()
    return FileResponse(
        file_id=record.id,
        filename=record.filename,
        media_type=record.media_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        relative_path=record.relative_path,
        created_at=record.created_at,
    )


async def list_files(session: AsyncSession) -> list[FileResponse]:
    result = await session.execute(select(FileRecord).order_by(FileRecord.created_at.desc()))
    return [
        FileResponse(
            file_id=item.id,
            filename=item.filename,
            media_type=item.media_type,
            size_bytes=item.size_bytes,
            sha256=item.sha256,
            relative_path=item.relative_path,
            created_at=item.created_at,
        )
        for item in result.scalars()
    ]


async def file_content(session: AsyncSession, settings: Settings, file_id: str) -> tuple[FileRecord, bytes]:
    record = await get_file(session, file_id)
    return record, read_workspace_file(settings, record.relative_path)


async def get_artifact(session: AsyncSession, settings: Settings, artifact_id: str) -> tuple[Artifact, Path]:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None or artifact.status != "ready":
        raise AppError("ARTIFACT_NOT_FOUND", "Artifact was not found", 404)
    path = artifact_path(settings, artifact.relative_path)
    if not path.is_file():
        raise AppError("ARTIFACT_NOT_FOUND", "Artifact file is not available", 404)
    return artifact, path


async def _document_or_404(session: AsyncSession, document_id: str) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND", "Document was not found", 404)
    return document


async def _source_from_create(session: AsyncSession, settings: Settings, request: CreateDocumentRequest) -> tuple[str, str | None]:
    if request.file_id:
        record, content = await file_content(session, settings, request.file_id)
        try:
            return normalize_source(content.decode("utf-8")), record.id
        except UnicodeDecodeError as exc:
            raise AppError("VALIDATION_ERROR", "Source file must be UTF-8 text", 422) from exc
    assert request.source_latex is not None
    return normalize_source(request.source_latex), None


async def create_document(session: AsyncSession, settings: Settings, request: CreateDocumentRequest) -> CompileOutcome:
    source, source_file_id = await _source_from_create(session, settings, request)
    now = utcnow()
    document = Document(
        id=new_id("doc"),
        name=request.name,
        source_file_id=source_file_id,
        latest_version_id=None,
        created_at=now,
        updated_at=now,
    )
    version = DocumentVersion(
        id=new_id("ver"),
        document_id=document.id,
        parent_version_id=None,
        source_latex=source,
        source_sha256=sha256_bytes(source.encode("utf-8")),
        change_summary=request.change_summary,
        compile_status="not_run",
        created_at=now,
    )
    document.latest_version_id = version.id
    session.add_all([document, version])
    await session.commit()
    return await compile_version(session, settings, document.id, version.id)


async def create_version(session: AsyncSession, settings: Settings, document_id: str, base_version_id: str, source: str, summary: str) -> CompileOutcome:
    document = await _document_or_404(session, document_id)
    if document.latest_version_id != base_version_id:
        raise AppError(
            "VERSION_CONFLICT",
            "Base version is no longer current",
            409,
            {"current_version_id": document.latest_version_id, "base_version_id": base_version_id},
        )
    now = utcnow()
    source = normalize_source(source)
    version = DocumentVersion(
        id=new_id("ver"),
        document_id=document.id,
        parent_version_id=base_version_id,
        source_latex=source,
        source_sha256=sha256_bytes(source.encode("utf-8")),
        change_summary=summary,
        compile_status="not_run",
        created_at=now,
    )
    session.add(version)
    result = await session.execute(
        update(Document)
        .where(Document.id == document_id, Document.latest_version_id == base_version_id)
        .values(latest_version_id=version.id, updated_at=now)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise AppError("VERSION_CONFLICT", "Base version is no longer current", 409)
    await session.commit()
    return await compile_version(session, settings, document_id, version.id)


async def compile_version(session: AsyncSession, settings: Settings, document_id: str, version_id: str) -> CompileOutcome:
    version = await session.get(DocumentVersion, version_id)
    if version is None or version.document_id != document_id:
        raise AppError("DOCUMENT_NOT_FOUND", "Document version was not found", 404)
    validation = validate_source(version.source_latex, settings.max_source_bytes)
    warnings = list(validation.warnings)
    if not validation.valid:
        version.compile_status = "failed"
        version.compile_error = "; ".join(validation.errors)
        await session.commit()
        return CompileOutcome(version, warnings)

    workdir = settings.artifact_dir.resolve() / ".work" / document_id / version_id
    result = compile_source(settings, version.source_latex, workdir)
    if result.warning:
        warnings.append(result.warning)
    version.compile_status = result.status
    version.compile_error = result.log or result.warning
    if result.status == "success" and result.pdf_path is not None:
        data = result.pdf_path.read_bytes()
        if len(data) > settings.max_artifact_bytes:
            version.compile_status = "failed"
            version.compile_error = "Generated PDF exceeds the artifact size limit"
        else:
            artifact_id = new_id("art")
            relative = str(Path(document_id) / version_id / f"{artifact_id}.pdf")
            target = artifact_path(settings, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result.pdf_path, target)
            artifact = Artifact(
                id=artifact_id,
                document_version_id=version.id,
                kind="pdf",
                relative_path=relative,
                media_type="application/pdf",
                size_bytes=len(data),
                sha256=sha256_bytes(data),
                status="ready",
                created_at=utcnow(),
            )
            session.add(artifact)
            version.compile_error = None
    await session.commit()
    result = await session.execute(
        select(DocumentVersion).options(selectinload(DocumentVersion.artifacts)).where(DocumentVersion.id == version.id)
    )
    refreshed = result.scalar_one()
    return CompileOutcome(refreshed, warnings)


async def get_document(session: AsyncSession, settings: Settings, document_id: str) -> DocumentResponse:
    document = await _document_or_404(session, document_id)
    result = await session.execute(
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.artifacts))
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.created_at.desc())
    )
    versions = list(result.scalars())
    response_versions = [_version_response(item, settings) for item in versions]
    latest = next((item for item in response_versions if item.version_id == document.latest_version_id), None)
    return DocumentResponse(
        document_id=document.id,
        name=document.name,
        source_file_id=document.source_file_id,
        latest_version_id=document.latest_version_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        latest_version=latest,
        versions=response_versions,
    )


async def render_version(session: AsyncSession, settings: Settings, document_id: str, version_id: str) -> RenderResponse:
    outcome = await compile_version(session, settings, document_id, version_id)
    error_details = {
        "document_id": document_id,
        "version_id": version_id,
        "source_latex": outcome.version.source_latex,
        "compile_error": outcome.version.compile_error,
        "warnings": outcome.warnings,
    }
    if outcome.version.compile_status == "failed":
        raise AppError(
            "LATEX_COMPILE_FAILED",
            "LaTeX compilation failed",
            422,
            error_details,
        )
    if outcome.version.compile_status == "timeout":
        raise AppError(
            "LATEX_COMPILE_TIMEOUT",
            "LaTeX compilation timed out",
            504,
            error_details,
        )
    if outcome.version.compile_status == "unavailable":
        raise AppError(
            "EXTERNAL_TOOL_UNAVAILABLE",
            "The configured LaTeX compiler is unavailable",
            503,
            error_details,
        )
    return RenderResponse(
        document_id=document_id,
        version=_version_response(outcome.version, settings),
        warnings=outcome.warnings,
    )


async def check_version(session: AsyncSession, settings: Settings, document_id: str, version_id: str, dry_run_compile: bool = False) -> tuple[DocumentVersion, bool, list[str], list[str], str | None]:
    result = await session.execute(
        select(DocumentVersion).options(selectinload(DocumentVersion.artifacts)).where(DocumentVersion.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None or version.document_id != document_id:
        raise AppError("DOCUMENT_NOT_FOUND", "Document version was not found", 404)
    result = validate_source(version.source_latex, settings.max_source_bytes)
    compile_status = version.compile_status
    warnings = list(result.warnings)
    if dry_run_compile and result.valid:
        check_dir = settings.artifact_dir.resolve() / ".checks" / new_id("check")
        compile_result = compile_source(settings, version.source_latex, check_dir)
        compile_status = compile_result.status
        if compile_result.warning:
            warnings.append(compile_result.warning)
        if compile_result.log and compile_result.status in {"failed", "timeout"}:
            result.errors.append(compile_result.log)
        shutil.rmtree(check_dir, ignore_errors=True)
    return version, result.valid and not result.errors, result.errors, warnings, compile_status


async def save_report(session: AsyncSession, document_id: str, request: JudgeReportRequest) -> JudgeReportResponse:
    version = await session.get(DocumentVersion, request.version_id)
    if version is None or version.document_id != document_id:
        raise AppError("DOCUMENT_NOT_FOUND", "Document version was not found", 404)
    report = JudgeReport(
        id=new_id("rpt"),
        document_version_id=version.id,
        rubric_version=request.rubric_version,
        ats_score=request.scores.ats,
        requirements_score=request.scores.requirements,
        quality_score=request.scores.quality,
        report_json={
            "job_description": request.job_description,
            "evidence": request.evidence,
            "gaps": request.gaps,
            "recommendations": request.recommendations,
        },
        warnings_json=request.warnings,
        created_at=utcnow(),
    )
    session.add(report)
    await session.commit()
    return JudgeReportResponse(
        report_id=report.id,
        document_version_id=report.document_version_id,
        rubric_version=report.rubric_version,
        scores=Scores(ats=report.ats_score, requirements=report.requirements_score, quality=report.quality_score),
        evidence=request.evidence,
        gaps=request.gaps,
        recommendations=request.recommendations,
        warnings=request.warnings,
        created_at=report.created_at,
    )


async def cleanup_expired_artifacts(session: AsyncSession, settings: Settings) -> int:
    from datetime import timedelta

    cutoff = utcnow() - timedelta(days=settings.artifact_retention_days)
    result = await session.execute(select(Artifact).where(Artifact.created_at < cutoff, Artifact.status == "ready"))
    removed = 0
    for artifact in result.scalars():
        version = await session.get(DocumentVersion, artifact.document_version_id)
        document = await session.get(Document, version.document_id) if version else None
        if version is None or (document and document.latest_version_id == version.id):
            continue
        path = artifact_path(settings, artifact.relative_path)
        if path.exists():
            path.unlink()
        artifact.status = "expired"
        removed += 1
    await session.commit()
    return removed
