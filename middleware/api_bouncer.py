"""Rate limiting, edge token checks, and payload integrity gate before WAL-backed ingestion."""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.bouncer_buffer import record_rejection

BOUNCER_EDGE_TOKEN = os.getenv("BOUNCER_EDGE_TOKEN", "edge-cam-prod-992-xtz")
CV_RATE_LIMIT_PER_MINUTE = int(os.getenv("BOUNCER_CV_RATE_LIMIT_PER_MINUTE", "30"))
FILL_RATE_LIMIT_PER_MINUTE = int(os.getenv("BOUNCER_FILL_RATE_LIMIT_PER_MINUTE", "120"))
MAX_BODY_BYTES = int(os.getenv("BOUNCER_MAX_BODY_BYTES", "65536"))

CV_PATHS = frozenset(
    {
        "/webhook/cv-detection",
        "/api/v1/bouncer/cv-detection",
    }
)
FILL_PATHS = frozenset({"/api/v1/telemetry/fill"})

PROTECTED_PATHS = CV_PATHS | FILL_PATHS


class _RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit_per_minute: int) -> bool:
        now = time.monotonic()
        window = self._windows[key]
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= limit_per_minute:
            return False
        window.append(now)
        return True


_rate_limiter = _RateLimiter()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _reject(
    request: Request,
    *,
    status_code: int,
    reason_code: str,
    detail: str,
    payload_preview: str | None = None,
) -> JSONResponse:
    record_rejection(
        path=request.url.path,
        reason_code=reason_code,
        detail=detail,
        client_ip=_client_key(request),
        payload_preview=payload_preview,
    )
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _validate_fill_integrity(body: dict) -> str | None:
    required = ("event_id", "sku", "action", "timestamp")
    missing = [field for field in required if field not in body]
    if missing:
        return f"Missing required fill fields: {', '.join(missing)}"
    if not isinstance(body.get("event_id"), str) or not body["event_id"].strip():
        return "event_id must be a non-empty string"
    if not isinstance(body.get("sku"), str) or not body["sku"].strip():
        return "sku must be a non-empty string"
    if body.get("action") not in ("increment", "decrement", "fill"):
        return "action must be increment, decrement, or fill"
    return None


def _validate_cv_integrity(body: dict) -> str | None:
    required = (
        "parent_sku",
        "detected_quantity",
        "physical_location",
        "detected_format",
        "loose_units_visible",
        "timestamp",
        "confidence_score",
    )
    missing = [field for field in required if field not in body]
    if missing:
        return f"Missing required CV fields: {', '.join(missing)}"
    try:
        score = float(body["confidence_score"])
    except (TypeError, ValueError):
        return "confidence_score must be numeric"
    if score < 0 or score > 1:
        return "confidence_score must be between 0 and 1"
    return None


class ApiBouncerMiddleware(BaseHTTPMiddleware):
    """
    Intercepts protected ingress routes, enforces per-client rate limits, validates JSON
    integrity, and applies edge token authentication before handlers flush to SQLite WAL.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if request.method != "POST" or path not in PROTECTED_PATHS:
            return await call_next(request)

        raw = await request.body()
        preview = raw[:512].decode("utf-8", errors="replace") if raw else ""

        if len(raw) > MAX_BODY_BYTES:
            return _reject(
                request,
                status_code=413,
                reason_code="PAYLOAD_TOO_LARGE",
                detail=f"Payload exceeds {MAX_BODY_BYTES} byte limit",
                payload_preview=preview,
            )

        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            return _reject(
                request,
                status_code=415,
                reason_code="INVALID_CONTENT_TYPE",
                detail="Content-Type must be application/json",
                payload_preview=preview,
            )

        try:
            body = json.loads(raw.decode("utf-8") if raw else "{}")
        except json.JSONDecodeError:
            return _reject(
                request,
                status_code=400,
                reason_code="MALFORMED_JSON",
                detail="Request body is not valid JSON",
                payload_preview=preview,
            )

        if not isinstance(body, dict):
            return _reject(
                request,
                status_code=422,
                reason_code="INVALID_PAYLOAD_SHAPE",
                detail="JSON body must be an object",
                payload_preview=preview,
            )

        client = _client_key(request)
        if path in CV_PATHS:
            limit = CV_RATE_LIMIT_PER_MINUTE
            api_key = request.headers.get("x-api-key")
            if api_key != BOUNCER_EDGE_TOKEN:
                return _reject(
                    request,
                    status_code=401,
                    reason_code="INVALID_EDGE_TOKEN",
                    detail="Unauthorized: Invalid Edge Camera Token",
                    payload_preview=preview,
                )
            integrity_error = _validate_cv_integrity(body)
        else:
            limit = FILL_RATE_LIMIT_PER_MINUTE
            integrity_error = _validate_fill_integrity(body)

        if integrity_error:
            return _reject(
                request,
                status_code=422,
                reason_code="INTEGRITY_VIOLATION",
                detail=integrity_error,
                payload_preview=preview,
            )

        rate_key = f"{client}:{path}"
        if not _rate_limiter.allow(rate_key, limit):
            return _reject(
                request,
                status_code=429,
                reason_code="RATE_LIMIT_EXCEEDED",
                detail="Rate limit exceeded for this client and route",
                payload_preview=preview,
            )

        async def receive() -> dict:
            return {"type": "http.request", "body": raw, "more_body": False}

        request._receive = receive  # noqa: SLF001 — replay body for downstream handlers
        request.state.bouncer_validated = True
        return await call_next(request)
