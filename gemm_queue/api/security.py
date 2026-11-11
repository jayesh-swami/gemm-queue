import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from gemm_queue.api.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key")


def require_api_key(key: Annotated[str, Depends(api_key_header)]) -> None:
    if not secrets.compare_digest(key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
