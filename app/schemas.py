from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    relative_path: str | None = None
    created_at: datetime | None = None


class CreateDocumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    file_id: str | None = None
    source_latex: str | None = None
    change_summary: str = "Initial source"

    @model_validator(mode="after")
    def require_one_source(self) -> "CreateDocumentRequest":
        if bool(self.file_id) == bool(self.source_latex):
            raise ValueError("Exactly one of file_id or source_latex is required")
        return self


class VersionRequest(BaseModel):
    base_version_id: str = Field(min_length=1)
    source_latex: str = Field(min_length=1)
    change_summary: str = Field(default="", max_length=4000)
    job_description: str | None = None


class VersionRefRequest(BaseModel):
    version_id: str = Field(min_length=1)
    dry_run_compile: bool = False


class CheckLatexResponse(BaseModel):
    document_id: str
    version_id: str
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    compile_status: str | None = None


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artifact_id: str
    document_version_id: str
    kind: str
    media_type: str
    size_bytes: int
    sha256: str
    status: str
    created_at: datetime
    preview_url: str | None = None
    download_url: str | None = None


class VersionResponse(BaseModel):
    version_id: str
    document_id: str
    parent_version_id: str | None
    source_latex: str
    source_sha256: str
    change_summary: str
    compile_status: str
    compile_error: str | None
    created_at: datetime
    artifacts: list[ArtifactResponse] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    document_id: str
    name: str
    source_file_id: str | None
    latest_version_id: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: VersionResponse | None = None
    versions: list[VersionResponse] = Field(default_factory=list)


class RenderResponse(BaseModel):
    document_id: str
    version: VersionResponse
    warnings: list[str] = Field(default_factory=list)


class Scores(BaseModel):
    ats: int = Field(ge=0, le=100)
    requirements: int = Field(ge=0, le=100)
    quality: int = Field(ge=0, le=100)


class JudgeReportRequest(BaseModel):
    version_id: str = Field(min_length=1)
    job_description: str | None = None
    rubric_version: str = Field(default="mvp-v1", min_length=1, max_length=100)
    scores: Scores
    evidence: list[Any] = Field(default_factory=list)
    gaps: list[Any] = Field(default_factory=list)
    recommendations: list[Any] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class JudgeReportResponse(BaseModel):
    report_id: str
    document_version_id: str
    rubric_version: str
    scores: Scores
    evidence: list[Any]
    gaps: list[Any]
    recommendations: list[Any]
    warnings: list[str]
    created_at: datetime


class McpFileContent(BaseModel):
    file_id: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    content_base64: str


class CompileResult:
    status: Literal["success", "failed", "timeout", "unavailable"]
    log: str = ""
    warning: str | None = None
