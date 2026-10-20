"""Aggregate dashboard KPIs from API Bouncer reconciliation log rows."""

from __future__ import annotations

from typing import Any

from services.shopfloor_catalog import catalog_by_ean


def reconciliation_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    nested = row.get("payload")
    if isinstance(nested, dict):
        return nested
    return row


def _catalog_row_for_ean(ean: str) -> dict[str, Any] | None:
    ean = str(ean or "").strip()
    if not ean:
        return None
    return catalog_by_ean().get(ean)


def _multipack_retail_gbp(catalog_row: dict[str, Any]) -> float:
    return round(int(catalog_row["unit_price_pence"]) / 100.0, 2)


def waste_units_from_adjustments(ledger_adjustments: dict[str, Any]) -> int:
    """Sum decomposed waste lines (e.g. *-WASTE); fallback to parent write-down qty."""
    waste_from_keys = 0
    for key, raw in ledger_adjustments.items():
        try:
            qty = int(raw)
        except (TypeError, ValueError):
            continue
        if "WASTE" in str(key).upper() and qty > 0:
            waste_from_keys += qty
    if waste_from_keys:
        return waste_from_keys

    return sum(
        abs(int(raw))
        for raw in ledger_adjustments.values()
        if isinstance(raw, (int, float)) and int(raw) < 0
    )


def parent_retail_writeoff_cost(
    ledger_adjustments: dict[str, Any],
    catalog_row: dict[str, Any] | None,
) -> float:
    """
    Total write-off at full parent (multipack) shelf price per destroyed parent SKU line.
    Ignores markdown / calculated_unit_price on surviving loose units.
    """
    if not catalog_row:
        return 0.0

    multipack_retail = _multipack_retail_gbp(catalog_row)
    write_off = 0.0
    for key, raw in ledger_adjustments.items():
        if "WASTE" in str(key).upper():
            continue
        try:
            qty = int(raw)
        except (TypeError, ValueError):
            continue
        if qty < 0:
            write_off += abs(qty) * multipack_retail

    return round(write_off, 2)


def aggregate_kpis_from_reconciliations(
    reconciliations: list[dict[str, Any]],
) -> dict[str, int | float]:
    daily_waste_qty = 0
    daily_waste_cost = 0.0

    for row in reconciliations:
        payload = reconciliation_row_payload(row)
        tx_hook = payload.get("transaction_engine_hook")
        if not isinstance(tx_hook, dict):
            continue

        adjustments = tx_hook.get("ledger_adjustments")
        if not isinstance(adjustments, dict) or not adjustments:
            continue

        row_waste_qty = waste_units_from_adjustments(adjustments)
        if row_waste_qty <= 0:
            continue

        daily_waste_qty += row_waste_qty
        ean = str(row.get("ean") or payload.get("ean") or "").strip()
        catalog_row = _catalog_row_for_ean(ean)
        daily_waste_cost += parent_retail_writeoff_cost(adjustments, catalog_row)

    return {
        "pending_edge_tasks": 0,
        "daily_waste_qty": daily_waste_qty,
        "daily_waste_cost": round(daily_waste_cost, 2),
    }
