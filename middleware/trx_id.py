import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TRX_ID_HEADER = "X-Trx-ID"


class TrxIdMiddleware(BaseHTTPMiddleware):
    """Reads or generates an X-Trx-ID for each request and echoes it on the response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        trx_id = request.headers.get(TRX_ID_HEADER) or str(uuid.uuid4())
        request.state.trx_id = trx_id

        response = await call_next(request)
        response.headers[TRX_ID_HEADER] = trx_id
        return response
