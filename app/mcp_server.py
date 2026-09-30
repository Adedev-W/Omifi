import base64
import os
from typing import Any

import httpx
from fastmcp import FastMCP


def _backend_url() -> str:
    return os.getenv("LATEX_BACKEND_URL", "http://localhost:8080").rstrip("/")


def _headers() -> dict[str, str]:
    key = os.getenv("LATEX_BACKEND_API_KEY", "")
    return {"X-API-Key": key} if key else {}


def _raise_for_backend(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        payload = response.json()
    except ValueError:
        payload = {"error": {"code": "BACKEND_ERROR", "message": response.text, "details": {}}}
    error = payload.get("error", {})
    raise RuntimeError(f"{error.get('code', 'BACKEND_ERROR')}: {error.get('message', 'Backend request failed')}")


mcp = FastMCP("cv-editor-files")


@mcp.tool()
async def upload_file(filename: str, content_base64: str, media_type: str = "text/x-tex") -> dict[str, Any]:
    """Upload a .tex or text file through the backend API."""
    try:
        content = base64.b64decode(content_base64, validate=True)
    except ValueError as exc:
        raise ValueError("content_base64 must be valid base64") from exc
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{_backend_url()}/v1/files",
            headers=_headers(),
            files={"file": (filename, content, media_type)},
        )
    _raise_for_backend(response)
    return response.json()


@mcp.tool()
async def list_files() -> list[dict[str, Any]]:
    """List files available in the configured local workspace."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{_backend_url()}/v1/files", headers=_headers())
    _raise_for_backend(response)
    return response.json()


@mcp.tool()
async def download_file(file_id: str) -> dict[str, Any]:
    """Download a file and return metadata plus base64 content."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{_backend_url()}/v1/files/{file_id}/download", headers=_headers())
    _raise_for_backend(response)
    return {
        "file_id": file_id,
        "filename": response.headers.get("content-disposition", "").split("filename=")[-1].strip('"') or file_id,
        "media_type": response.headers.get("content-type", "application/octet-stream"),
        "size_bytes": len(response.content),
        "sha256": response.headers.get("x-file-sha256", ""),
        "content_base64": base64.b64encode(response.content).decode("ascii"),
    }


if __name__ == "__main__":
    mcp.run()
