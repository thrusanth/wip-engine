import random
import threading
from typing import Dict, List

from services.sku_catalog import SIMULATION_SKU_POOL, get_sku_profile
from models.schemas import (
    ActiveException,
    ContainerState,
    ContainerStatus,
    ExceptionKind,
    GlobalMetrics,
    ResolutionEvent,
    ResolutionType,
    SkuState,
    TelemetryResponse,
)


class WipEngine:
    def __init__(self):
        self.sku_prices = {
            "CHOCO-BISCUITS-6PK": 1.50,
            "BAKED-BEANS-6PK": 1.10,
            "PERONI-12PK": 15.00,
            "ORANGE-SODA-8PK": 2.25,
        }

        self._lock = threading.RLock()
        self.containers: Dict[str, ContainerState] = {}
        self.active_exceptions: List[ActiveException] = []
        self.metrics = GlobalMetrics()
        self._pending_delivery_cages = 4
        self._initialize_mock_data()

    def _sku_state(self, sku_code: str, **fields) -> SkuState:
        profile = get_sku_profile(sku_code)
        return SkuState(
            sku=sku_code,
            name=profile["name"],
            ean=profile["ean"],
            **fields,
        )

    def _initialize_mock_data(self):
        self.containers["FT-02"] = ContainerState(
            id="FT-02",
            status=ContainerStatus.ABANDONED_MID_SHIFT,
            zone="Aisle 4",
            skus=[
                self._sku_state(
                    "BAKED-BEANS-6PK",
                    expected=12,
                    worked=6,
                    backstock=2,
                )
            ],
        )

        self.containers["FT-01"] = ContainerState(
            id="FT-01",
            status=ContainerStatus.IN_PROGRESS_SHOPFLOOR,
            zone="Aisle 2",
            skus=[
                self._sku_state(
                    "CHOCO-BISCUITS-6PK",
                    expected=12,
                    cv_filled=6,
                )
            ],
        )

        self.containers["FT-03"] = ContainerState(
            id="FT-03",
            status=ContainerStatus.RETURNED_MIXED,
            zone="Aisle 7",
            skus=[
                self._sku_state(
                    "PERONI-12PK",
                    expected=12,
                    cv_filled=7,
                    confirmed_backstock=5,
                )
            ],
        )

        from services.simulator import ORANGE_SODA_PHANTOM_DRIFT_SCENARIO

        orange = ORANGE_SODA_PHANTOM_DRIFT_SCENARIO
        self.containers["FT-04"] = ContainerState(
            id=orange["container_id"],
            status=ContainerStatus.IN_PROGRESS_SHOPFLOOR,
            zone="Aisle 9",
            skus=[
                self._sku_state(
                    orange["sku"],
                    expected=orange["expected"],
                    worked=orange["worked"],
                )
            ],
        )

        with self._lock:
            self._recalculate_all()
            self._sync_active_exceptions()

    def _recalculate_sku(self, sku_state: SkuState):
        initial_drift = (
            sku_state.expected
            - sku_state.worked
            - sku_state.backstock
            - sku_state.cv_filled
            - sku_state.confirmed_backstock
        )

        if sku_state.is_resolved:
            if sku_state.resolution_type == ResolutionType.ALL:
                sku_state.drift = 0
                sku_state.variance = 0
                sku_state.shrink_confirmed = 0
            elif sku_state.resolution_type == ResolutionType.NONE:
                sku_state.drift = initial_drift
                sku_state.variance = 0
                sku_state.shrink_confirmed = initial_drift
            elif sku_state.resolution_type == ResolutionType.PARTIAL:
                sku_state.drift = initial_drift - sku_state.recovered_units
                sku_state.variance = 0
                sku_state.shrink_confirmed = sku_state.drift
        else:
            sku_state.drift = max(0, initial_drift)
            sku_state.variance = max(0, initial_drift)

    def _recalculate_all(self):
        total_drift = 0
        total_shrink_cost = 0.0
        total_pending = 0

        for container in self.containers.values():
            container_pending = False

            for sku in container.skus:
                self._recalculate_sku(sku)
                total_drift += sku.drift

                price = self.sku_prices.get(sku.sku, 0.0)
                total_shrink_cost += sku.drift * price

                if sku.variance > 0 and not sku.is_resolved:
                    container_pending = True

            container.is_pending = container_pending
            if container_pending:
                total_pending += 1

        self.metrics = GlobalMetrics(
            pending_delivery_cages=self._pending_delivery_cages,
            active_flattops=len(self.containers),
            detected_phantom_drift=total_drift,
            daily_shrink_cost=total_shrink_cost,
            pending_edge_tasks=total_pending,
        )

    def _sync_active_exceptions(self):
        """Rebuild active_exceptions from unresolved container/SKU state."""
        exceptions: List[ActiveException] = []

        for container in self.containers.values():
            for sku in container.skus:
                if sku.is_resolved:
                    continue

                if sku.drift > 0:
                    exceptions.append(
                        ActiveException(
                            kind=ExceptionKind.PHANTOM_DRIFT,
                            container_id=container.id,
                            sku=sku.sku,
                            ean=sku.ean,
                            zone=container.zone,
                            units=sku.drift,
                            message=(
                                f"{sku.drift} units of {sku.sku} unaccounted on {container.id} "
                                f"({container.status.value})."
                            ),
                        )
                    )
                elif sku.variance > 0:
                    exceptions.append(
                        ActiveException(
                            kind=ExceptionKind.UNTRACKED_BACKSTOCK,
                            container_id=container.id,
                            sku=sku.sku,
                            ean=sku.ean,
                            zone=container.zone,
                            units=sku.variance,
                            message=(
                                f"{sku.variance} units of {sku.sku} missing CV proof-of-fill; "
                                "suspected untracked backstock routing."
                            ),
                        )
                    )

        self.active_exceptions = exceptions

    def apply_simulated_tick(self) -> None:
        """Apply one background simulation step (thread-safe)."""
        with self._lock:
            scenario = random.choice(
                [
                    "phantom_drift",
                    "cage_discrepancy",
                    "cv_fill",
                    "delivery_cage_arrival",
                    "sku_variance",
                ]
            )

            if scenario == "phantom_drift":
                drift_container_id = random.choice(["FT-02", "FT-04"])
                container = self.containers.get(drift_container_id)
                if container and container.skus:
                    sku = container.skus[0]
                    if not sku.is_resolved and sku.worked > 0:
                        sku.worked = max(0, sku.worked - 1)

            elif scenario == "cage_discrepancy":
                self._pending_delivery_cages = min(8, self._pending_delivery_cages + 1)
                cage_profile = get_sku_profile("MIXED-MANIFEST")
                self.active_exceptions.append(
                    ActiveException(
                        kind=ExceptionKind.CAGE_DISCREPANCY,
                        container_id="CAGE-UNLOAD",
                        sku="MIXED-MANIFEST",
                        ean=cage_profile["ean"],
                        zone="Backroom Staging",
                        units=random.randint(1, 6),
                        message="Delivery cage manifest mismatch detected during breakdown.",
                    )
                )

            elif scenario == "cv_fill":
                container = self.containers.get("FT-01")
                if container and container.skus:
                    sku = container.skus[0]
                    if not sku.is_resolved and sku.cv_filled < sku.expected:
                        sku.cv_filled += 1

            elif scenario == "delivery_cage_arrival":
                self._pending_delivery_cages = max(2, self._pending_delivery_cages - 1)

            elif scenario == "sku_variance":
                pool_sku = random.choice(list(SIMULATION_SKU_POOL.keys()))
                if pool_sku == "MIXED-MANIFEST":
                    pool_sku = "CHOCO-BISCUITS-6PK"
                profile = get_sku_profile(pool_sku)
                self.active_exceptions.append(
                    ActiveException(
                        kind=ExceptionKind.SKU_VARIANCE,
                        container_id="FT-SIM",
                        sku=pool_sku,
                        ean=profile["ean"],
                        zone="Shop Floor",
                        units=random.randint(1, 3),
                        message=f"SKU variance detected for {profile['name']} during simulated scan.",
                    )
                )

            # Trim stale simulated cage alerts so the feed stays readable.
            self.active_exceptions = [
                exc
                for exc in self.active_exceptions
                if exc.kind != ExceptionKind.CAGE_DISCREPANCY
                or random.random() > 0.3
            ]

            self._recalculate_all()
            self._sync_active_exceptions()

    def get_telemetry(self) -> TelemetryResponse:
        with self._lock:
            return TelemetryResponse(
                metrics=self.metrics.model_copy(deep=True),
                containers={cid: c.model_copy(deep=True) for cid, c in self.containers.items()},
                active_exceptions=[exc.model_copy(deep=True) for exc in self.active_exceptions],
            )

    def resolve_event(self, event: ResolutionEvent) -> TelemetryResponse:
        with self._lock:
            container = self.containers.get(event.container_id)
            if not container:
                raise ValueError(f"Container {event.container_id} not found")

            target_sku = next((s for s in container.skus if s.sku == event.sku), None)
            if not target_sku:
                raise ValueError(f"SKU {event.sku} not found in container {event.container_id}")

            target_sku.is_resolved = True
            target_sku.resolution_type = event.resolution_type
            target_sku.recovered_units = event.recovered_units

            self._recalculate_all()
            self._sync_active_exceptions()

            return TelemetryResponse(
                metrics=self.metrics.model_copy(deep=True),
                containers={cid: c.model_copy(deep=True) for cid, c in self.containers.items()},
                active_exceptions=[exc.model_copy(deep=True) for exc in self.active_exceptions],
            )


engine = WipEngine()
