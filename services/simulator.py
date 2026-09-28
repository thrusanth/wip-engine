import asyncio
import logging
from services.engine import WipEngine
from services.sku_catalog import get_simulation_sku_pool

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 5.0

# Baseline phantom-drift scenario for Orange Soda (FT-04); engine seeds this on startup.
ORANGE_SODA_PHANTOM_DRIFT_SCENARIO = {
    "sku": "ORANGE-SODA-8PK",
    "container_id": "FT-04",
    "expected": 8,
    "worked": 6,
    "phantom_drift": 2,
}


async def run_telemetry_simulator(
    engine: WipEngine,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Periodically inject realistic retail inventory anomalies into live state."""
    logger.info("Telemetry simulator started (interval=%ss)", interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            get_simulation_sku_pool()
            engine.apply_simulated_tick()
    except asyncio.CancelledError:
        logger.info("Telemetry simulator shutting down")
        raise


def spawn_simulator_task(
    engine: WipEngine,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> asyncio.Task:
    return asyncio.create_task(
        run_telemetry_simulator(engine, interval_seconds=interval_seconds),
        name="wip-telemetry-simulator",
    )
