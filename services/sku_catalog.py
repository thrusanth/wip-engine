"""Retail SKU catalog with 13-digit EAN barcodes for simulation and telemetry."""

from typing import Dict, NotRequired, Optional, TypedDict


class SkuCatalogEntry(TypedDict):
    ean: str
    name: str
    price: NotRequired[float]


# Standard UK retail-style prefixes (501...) mapped to active mock SKUs.
SIMULATION_SKU_POOL: Dict[str, SkuCatalogEntry] = {
    "BAKED-BEANS-6PK": {
        "ean": "5012345678901",
        "name": "Heinz Baked Beans 6pk",
        "price": 1.10,
    },
    "CHOCO-BISCUITS-6PK": {
        "ean": "5012345678918",
        "name": "McVitie's Chocolate Biscuits 6pk",
        "price": 1.50,
    },
    "PERONI-12PK": {
        "ean": "5012345678925",
        "name": "Peroni Nastro Azzurro 12pk",
        "price": 15.00,
    },
    "MIXED-MANIFEST": {
        "ean": "5012345000012",
        "name": "Mixed Delivery Cage Manifest",
    },
    "ORANGE-SODA-8PK": {
        "ean": "5012345678948",
        "name": "Orange Soda 8pk",
        "price": 2.25,
    },
}


def get_sku_profile(sku: str) -> SkuCatalogEntry:
    return SIMULATION_SKU_POOL.get(
        sku,
        {"ean": "5012300000000", "name": sku.replace("-", " ").title()},
    )


def get_unit_price(sku: str, sku_price: Optional[float] = None) -> float:
    """Resolve unit price from SKU state or catalog (0.0 if unknown)."""
    if sku_price is not None:
        return sku_price
    return get_sku_profile(sku).get("price", 0.0)
