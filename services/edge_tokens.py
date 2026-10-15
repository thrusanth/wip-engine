"""Edge camera token configuration shared by middleware and dashboard transmitters."""

from __future__ import annotations

import os

# Public demo default (also documented in README); safe to accept when demo mode is enabled.
DEMO_BOUNCER_EDGE_TOKEN = "edge-cam-prod-992-xtz"


def configured_edge_token() -> str:
    return os.getenv("BOUNCER_EDGE_TOKEN", DEMO_BOUNCER_EDGE_TOKEN)


def demo_edge_token_allowed() -> bool:
    raw = os.getenv("BOUNCER_ALLOW_DEMO_EDGE_TOKEN", "true")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_valid_edge_token(provided: str | None) -> bool:
    if not provided:
        return False
    if provided == configured_edge_token():
        return True
    return demo_edge_token_allowed() and provided == DEMO_BOUNCER_EDGE_TOKEN


def edge_camera_headers() -> dict[str, str]:
    return {
        "X-API-Key": configured_edge_token(),
        "Content-Type": "application/json",
    }
