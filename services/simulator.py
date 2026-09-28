import asyncio
import logging
from services.engine import WipEngine
from services.sku_catalog import get_simulation_sku_pool

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 5.0

# FT-04 startup fixture; engine seeds container state from this on init.
FT_04_SEED_SCENARIO = {
    "sku": "TWIRL-8PK",
    "container_id": "FT-04",
    "expected": 8,
    "worked": 4,
    "backstock": 4,
}


def seed_ft_04_fixture(engine: WipEngine) -> None:
    """Apply the FT-04 TWIRL-8PK fixture (8-case: 4 shelf / 4 backstock)."""
    from models.schemas import ContainerState, ContainerStatus

    scenario = FT_04_SEED_SCENARIO
    engine.containers[scenario["container_id"]] = ContainerState(
        id=scenario["container_id"],
        status=ContainerStatus.IN_PROGRESS_SHOPFLOOR,
        zone="Aisle 9",
        skus=[
            engine._sku_state(
                scenario["sku"],
                expected=scenario["expected"],
                worked=scenario["worked"],
                backstock=scenario["backstock"],
            )
        ],
    )


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
