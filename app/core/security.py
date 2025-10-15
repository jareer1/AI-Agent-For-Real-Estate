from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from .config import get_settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Depends(api_key_header)) -> None:
    settings = get_settings()
    if not settings.api_key:
        return
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


