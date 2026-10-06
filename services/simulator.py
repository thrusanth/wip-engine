import asyncio
import logging

from services.engine import WipEngine
from services.simulation_config import FIXED_SIMULATION_RANDOM_SEED, LIVE_SIMULATION_ENABLED
from services.sku_catalog import get_simulation_sku_pool

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 5.0


async def run_telemetry_simulator(
    engine: WipEngine,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Refresh catalog from disk; optionally apply live simulation ticks when enabled."""
    logger.info(
        "Telemetry simulator started (interval=%ss, live_simulation=%s, seed=%s)",
        interval_seconds,
        LIVE_SIMULATION_ENABLED,
        FIXED_SIMULATION_RANDOM_SEED,
    )
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            get_simulation_sku_pool()
            if LIVE_SIMULATION_ENABLED:
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
