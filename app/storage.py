import hashlib
import re
from pathlib import Path

from .config import Settings
from .errors import AppError


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(filename: str) -> str:
    candidate = Path(filename or "upload.tex").name
    cleaned = _SAFE_NAME.sub("_", candidate).strip("._")
    if not cleaned:
        raise AppError("VALIDATION_ERROR", "Filename is empty after sanitization", 422)
    return cleaned[:255]


def safe_relative_path(settings: Settings, relative_path: str) -> Path:
    root = settings.workspace_root.resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise AppError("VALIDATION_ERROR", "Path traversal is not allowed", 422)
    return target


def write_workspace_file(settings: Settings, file_id: str, filename: str, data: bytes) -> str:
    clean_name = safe_filename(filename)
    relative = str(Path("data") / "uploads" / file_id / clean_name)
    target = safe_relative_path(settings, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative


def read_workspace_file(settings: Settings, relative_path: str) -> bytes:
    target = safe_relative_path(settings, relative_path)
    if not target.is_file():
        raise AppError("FILE_NOT_FOUND", "Stored file is not available", 404)
    return target.read_bytes()


def artifact_path(settings: Settings, relative_path: str) -> Path:
    root = settings.artifact_dir.resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise AppError("ARTIFACT_NOT_FOUND", "Artifact path is invalid", 404)
    return target


def bounded_text(value: bytes, limit: int) -> str:
    limit = max(0, limit)
    text = value.decode("utf-8", errors="replace")
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    marker = b"\n...[truncated]"
    if limit <= len(marker):
        return encoded[:limit].decode("utf-8", errors="ignore")
    return encoded[: limit - len(marker)].decode("utf-8", errors="ignore") + marker.decode()
