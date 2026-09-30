import base64
import hashlib

import pytest

import app.mcp_server as server


class FakeResponse:
    is_success = True
    content = b"hello"
    headers = {
        "content-disposition": 'attachment; filename="cv.tex"',
        "content-type": "text/x-tex",
        "x-file-sha256": hashlib.sha256(content).hexdigest(),
    }

    def json(self):
        return {"file_id": "file_1", "filename": "cv.tex"}


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        return FakeResponse()

    async def get(self, *args, **kwargs):
        return FakeResponse()


@pytest.mark.asyncio
async def test_mcp_upload_and_download_use_base64_and_metadata(monkeypatch):
    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)
    uploaded = await server.upload_file.fn("cv.tex", base64.b64encode(b"hello").decode(), "text/x-tex")
    listed = await server.list_files.fn()
    downloaded = await server.download_file.fn("file_1")
    assert uploaded["file_id"] == "file_1"
    assert listed["file_id"] == "file_1"
    assert base64.b64decode(downloaded["content_base64"]) == b"hello"
    assert downloaded["sha256"] == hashlib.sha256(b"hello").hexdigest()


@pytest.mark.asyncio
async def test_mcp_rejects_invalid_base64():
    with pytest.raises(ValueError, match="valid base64"):
        await server.upload_file.fn("cv.tex", "not-base64!")
