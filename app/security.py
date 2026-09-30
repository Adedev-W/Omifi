import secrets

from fastapi import Header, Request

from .errors import AppError


async def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    settings = request.app.state.settings
    if not settings.internal_api_key:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.internal_api_key):
        raise AppError("UNAUTHORIZED", "A valid X-API-Key is required", 401)
