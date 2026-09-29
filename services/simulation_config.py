"""Shared simulation configuration (deterministic fixtures + optional live ticks)."""

import os
from datetime import datetime, timezone

FIXED_SIMULATION_RANDOM_SEED = int(os.getenv("WIP_SIMULATION_RANDOM_SEED", "424242"))

# Stable timestamp for fixture-derived exceptions (dashboard reloads / process restarts).
FIXTURE_EXCEPTION_DETECTED_AT = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)

# Live background mutations are off by default so dashboard reloads stay stable until
# an operator submits an explicit resolution event.
LIVE_SIMULATION_ENABLED = os.getenv("WIP_LIVE_SIMULATION", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
