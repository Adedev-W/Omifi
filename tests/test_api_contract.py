from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

import app.services as services
from app.config import Settings
from app.db import Database
from app.latex_engine import CompileResult
from app.main import create_app, lifespan
from app.models import Artifact, Document, DocumentVersion
from app.services import cleanup_expired_artifacts
from app.storage import artifact_path, sha256_bytes
from app.utils import new_id, utcnow


SOURCE = r"\documentclass{article}\begin{document}Hello\end{document}"


@pytest.mark.asyncio
async def test_health_is_public_and_internal_api_key_is_enforced(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        workspace_root=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
        internal_api_key="secret",
        latex_engine="missing-engine",
    )
    app = create_app(settings)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/v1/files")).json()["error"]["code"] == "UNAUTHORIZED"
            assert (await client.get("/v1/files", headers={"X-API-Key": "secret"})).status_code == 200


@pytest.mark.asyncio
async def test_document_version_conflict_and_source_immutability(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        workspace_root=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
        latex_engine="missing-engine",
    )
    app = create_app(settings)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/v1/documents", json={"name": "cv.tex", "source_latex": SOURCE})
            assert created.status_code == 200
            document = created.json()
            doc_id = document["document_id"]
            version_id = document["latest_version_id"]
            replacement = SOURCE.replace("Hello", "Updated")
            edited = await client.post(
                f"/v1/documents/{doc_id}/versions",
                json={"base_version_id": version_id, "source_latex": replacement, "change_summary": "Update"},
            )
            assert edited.status_code == 200
            conflict = await client.post(
                f"/v1/documents/{doc_id}/versions",
                json={"base_version_id": version_id, "source_latex": SOURCE, "change_summary": "Stale"},
            )
            assert conflict.status_code == 409
            assert len(edited.json()["versions"]) == 2
            assert any("Hello" in item["source_latex"] for item in edited.json()["versions"])


@pytest.mark.asyncio
async def test_document_source_latex_is_normalized_before_compile_and_storage(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        workspace_root=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
        latex_engine="missing-engine",
    )
    app = create_app(settings)
    source = "\ufeff```latex\r\n" + SOURCE + "\r\n```\r\n"
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/v1/documents", json={"name": "cv.tex", "source_latex": source})

    assert response.status_code == 200
    assert response.json()["latest_version"]["source_latex"] == SOURCE


@pytest.mark.asyncio
async def test_upload_report_and_latex_check_contract(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        workspace_root=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
        latex_engine="missing-engine",
    )
    app = create_app(settings)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            rejected = await client.post("/v1/files", files={"file": ("photo.jpg", b"binary", "image/jpeg")})
            assert rejected.status_code == 422
            assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"
            upload = await client.post("/v1/files", files={"file": ("cv.tex", SOURCE.encode(), "text/x-tex")})
            assert upload.status_code == 200
            file_id = upload.json()["file_id"]
            file_download = await client.get(f"/v1/files/{file_id}/download")
            assert file_download.status_code == 200
            assert file_download.content == SOURCE.encode()
            assert file_download.headers["x-file-sha256"] == upload.json()["sha256"]
            created = await client.post("/v1/documents", json={"name": "uploaded.tex", "file_id": file_id})
            assert created.status_code == 200
            doc = created.json()
            check = await client.post(
                f"/v1/documents/{doc['document_id']}/check-latex",
                json={"version_id": doc["latest_version_id"], "dry_run_compile": True},
            )
            assert check.status_code == 200
            assert check.json()["compile_status"] == "unavailable"
            report = await client.post(
                f"/v1/documents/{doc['document_id']}/reports",
                json={
                    "version_id": doc["latest_version_id"],
                    "scores": {"ats": 80, "requirements": 75, "quality": 90},
                    "evidence": [{"source": "cv", "text": "Hello"}],
                    "recommendations": ["Add keywords"],
                    "warnings": ["web unavailable"],
                },
            )
            assert report.status_code == 200
            assert report.json()["scores"]["ats"] == 80


@pytest.mark.asyncio
async def test_invalid_document_source_returns_serializable_validation_error(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        workspace_root=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
        latex_engine="missing-engine",
    )
    app = create_app(settings)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/documents",
                json={"name": "EditingComponent", "source_latex": "", "change_summary": ""},
            )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["ctx"]["error"] == "Exactly one of file_id or source_latex is required"


@pytest.mark.asyncio
async def test_render_publishes_opaque_artifact_urls(monkeypatch, tmp_path: Path):
    def fake_compile(settings, source, workdir):
        workdir.mkdir(parents=True, exist_ok=True)
        pdf = workdir / "source.pdf"
        pdf.write_bytes(b"%PDF-test")
        return CompileResult(status="success", pdf_path=pdf)

    monkeypatch.setattr(services, "compile_source", fake_compile)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        workspace_root=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    )
    app = create_app(settings)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/v1/documents", json={"name": "cv.tex", "source_latex": SOURCE})
            artifact = created.json()["latest_version"]["artifacts"][0]
            assert artifact["artifact_id"].startswith("art_")
            preview = await client.get(artifact["preview_url"].replace("http://localhost:8080", ""))
            assert preview.status_code == 200
            assert preview.content == b"%PDF-test"


@pytest.mark.asyncio
async def test_sqlite_connection_enables_foreign_keys_and_busy_timeout(tmp_path: Path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'cv.db'}", busy_timeout_seconds=7)
    database = Database(settings)
    await database.create_schema()
    async with database.session_context() as session:
        foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar_one()
        busy_timeout = (await session.execute(text("PRAGMA busy_timeout"))).scalar_one()
    await database.close()
    assert foreign_keys == 1
    assert busy_timeout == 7000


@pytest.mark.asyncio
async def test_retention_expires_old_artifacts_but_keeps_latest(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        artifact_dir=tmp_path / "artifacts",
        workspace_root=tmp_path / "workspace",
        artifact_retention_days=1,
    )
    database = Database(settings)
    await database.create_schema()
    now = utcnow()
    document_id = new_id("doc")
    old_version_id = new_id("ver")
    latest_version_id = new_id("ver")
    old_artifact_id = new_id("art")
    old_relative = f"{document_id}/{old_version_id}/{old_artifact_id}.pdf"
    old_path = artifact_path(settings, old_relative)
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_bytes(b"old")
    async with database.session_context() as session:
        session.add(Document(id=document_id, name="cv.tex", latest_version_id=latest_version_id, created_at=now, updated_at=now))
        session.add_all([
            DocumentVersion(id=old_version_id, document_id=document_id, source_latex="old", source_sha256=sha256_bytes(b"old"), change_summary="old", compile_status="success", created_at=now - timedelta(days=3)),
            DocumentVersion(id=latest_version_id, document_id=document_id, source_latex="latest", source_sha256=sha256_bytes(b"latest"), change_summary="latest", compile_status="success", created_at=now),
            Artifact(id=old_artifact_id, document_version_id=old_version_id, kind="pdf", relative_path=old_relative, media_type="application/pdf", size_bytes=3, sha256=sha256_bytes(b"old"), status="ready", created_at=now - timedelta(days=3)),
        ])
        await session.commit()
        assert await cleanup_expired_artifacts(session, settings) == 1
        expired = await session.get(Artifact, old_artifact_id)
        assert expired.status == "expired"
    await database.close()
    assert not old_path.exists()


@pytest.mark.asyncio
async def test_invalid_source_is_persisted_before_compile_error(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cv.db'}",
        workspace_root=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
        latex_engine="missing-engine",
    )
    app = create_app(settings)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/v1/documents", json={"name": "invalid.tex", "source_latex": "not latex"})
            assert response.status_code == 422
            error = response.json()["error"]
            assert error["code"] == "LATEX_COMPILE_FAILED"
            document = await client.get(f"/v1/documents/{error['details']['document_id']}")
            assert document.status_code == 200
            assert document.json()["latest_version"]["compile_status"] == "failed"
            assert document.json()["latest_version"]["source_latex"] == "not latex"
