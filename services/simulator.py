import asyncio
import logging
from typing import Any, Dict, List, TypedDict

from services.engine import WipEngine
from services.sku_catalog import get_simulation_sku_pool

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 5.0


class Ft04InventoryLine(TypedDict, total=False):
    sku: str
    expected: int
    worked: int
    backstock: int
    cv_filled: int
    confirmed_backstock: int


class Ft04SeedScenario(TypedDict):
    container_id: str
    zone: str
    inventory_lines: List[Ft04InventoryLine]


# FT-04 multi-SKU fixture; engine seeds container state from this on init.
FT_04_SEED_SCENARIO: Ft04SeedScenario = {
    "container_id": "FT-04",
    "zone": "Aisle 9",
    "inventory_lines": [
        {
            "sku": "ORANGE-SODA-8PK",
            "expected": 8,
            "worked": 6,
            "backstock": 0,
        },
        {
            "sku": "TWIRL-8PK",
            "expected": 8,
            "worked": 4,
            "backstock": 4,
        },
    ],
}


def _sku_state_from_line(engine: WipEngine, line: Ft04InventoryLine):
    sku = line["sku"]
    fields: Dict[str, Any] = {
        "expected": line["expected"],
        "worked": line.get("worked", 0),
        "backstock": line.get("backstock", 0),
    }
    if "cv_filled" in line:
        fields["cv_filled"] = line["cv_filled"]
    if "confirmed_backstock" in line:
        fields["confirmed_backstock"] = line["confirmed_backstock"]
    return engine._sku_state(sku, **fields)


def seed_ft_04_fixture(engine: WipEngine) -> None:
    """Apply the FT-04 multi-item fixture (Orange Soda drift + Twirl shelf/backstock)."""
    from models.schemas import ContainerState, ContainerStatus

    scenario = FT_04_SEED_SCENARIO
    engine.containers[scenario["container_id"]] = ContainerState(
        id=scenario["container_id"],
        status=ContainerStatus.IN_PROGRESS_SHOPFLOOR,
        zone=scenario["zone"],
        skus=[_sku_state_from_line(engine, line) for line in scenario["inventory_lines"]],
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
