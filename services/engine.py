from typing import Dict, List
from models.schemas import ContainerState, ContainerStatus, SkuState, GlobalMetrics, TelemetryResponse, ResolutionEvent, ResolutionType

class WipEngine:
    def __init__(self):
        # SKU Price Mapping
        self.sku_prices = {
            "CHOCO-BISCUITS-6PK": 1.50,
            "BAKED-BEANS-6PK": 1.10,
            "PERONI-12PK": 15.00
        }
        
        # In-memory database
        self.containers: Dict[str, ContainerState] = {}
        self._initialize_mock_data()

    def _initialize_mock_data(self):
        """Initializes the three scenarios requested in the mock data."""
        # Scenario 1 (FT-02)
        self.containers["FT-02"] = ContainerState(
            id="FT-02",
            status=ContainerStatus.ABANDONED_MID_SHIFT,
            zone="Aisle 4",
            skus=[
                SkuState(
                    sku="BAKED-BEANS-6PK",
                    expected=12,
                    worked=6,
                    backstock=2,
                )
            ]
        )

        # Scenario 2 (FT-01)
        self.containers["FT-01"] = ContainerState(
            id="FT-01",
            status=ContainerStatus.IN_PROGRESS_SHOPFLOOR,
            zone="Aisle 2",
            skus=[
                SkuState(
                    sku="CHOCO-BISCUITS-6PK",
                    expected=12,
                    cv_filled=6,
                )
            ]
        )

        # Scenario 3 (FT-03)
        self.containers["FT-03"] = ContainerState(
            id="FT-03",
            status=ContainerStatus.RETURNED_MIXED,
            zone="Aisle 7",
            skus=[
                SkuState(
                    sku="PERONI-12PK",
                    expected=12,
                    cv_filled=7,
                    confirmed_backstock=5,
                )
            ]
        )
        
        # Calculate initial state
        self._recalculate_all()

    def _recalculate_sku(self, sku_state: SkuState):
        """Calculates derived metrics for a single SKU based on its base values and resolution state."""
        # Baseline calculations (before resolutions)
        initial_drift = sku_state.expected - sku_state.worked - sku_state.backstock - sku_state.cv_filled - sku_state.confirmed_backstock
        
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
            sku_state.variance = max(0, initial_drift) # Variance is conceptually unresolved drift

    def _recalculate_all(self):
        """Recalculates all derived metrics and global totals."""
        total_drift = 0
        total_shrink_cost = 0.0
        total_pending = 0

        for container in self.containers.values():
            container_pending = False
            
            for sku in container.skus:
                self._recalculate_sku(sku)
                
                total_drift += sku.drift
                
                # Shrink cost is based on active drift or confirmed shrink
                price = self.sku_prices.get(sku.sku, 0.0)
                total_shrink_cost += (sku.drift * price)
                
                if sku.variance > 0 and not sku.is_resolved:
                    container_pending = True

            container.is_pending = container_pending
            if container_pending:
                total_pending += 1

        self.metrics = GlobalMetrics(
            pending_delivery_cages=4,
            active_flattops=3,
            detected_phantom_drift=total_drift,
            daily_shrink_cost=total_shrink_cost,
            pending_edge_tasks=total_pending
        )

    def get_telemetry(self) -> TelemetryResponse:
        """Returns the complete system state."""
        return TelemetryResponse(
            metrics=self.metrics,
            containers=self.containers
        )

    def resolve_event(self, event: ResolutionEvent) -> TelemetryResponse:
        """Processes a shift leader resolution event and updates the system state."""
        container = self.containers.get(event.container_id)
        if not container:
            raise ValueError(f"Container {event.container_id} not found")
            
        target_sku = next((s for s in container.skus if s.sku == event.sku), None)
        if not target_sku:
            raise ValueError(f"SKU {event.sku} not found in container {event.container_id}")

        # Update resolution state
        target_sku.is_resolved = True
        target_sku.resolution_type = event.resolution_type
        target_sku.recovered_units = event.recovered_units

        # Recalculate engine
        self._recalculate_all()
        
        return self.get_telemetry()

# Global singleton instance
engine = WipEngine()