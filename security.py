import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

# Default supports local/docker dev; override in production via WIP_API_KEY.
EXPECTED_API_KEY = os.getenv("WIP_API_KEY", "dev-wip-engine-key")


async def require_api_key(api_key: str | None = Security(api_key_header)) -> str:
    if not api_key or api_key != EXPECTED_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
    return api_key
