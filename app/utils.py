import uuid
from datetime import datetime, timezone


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

