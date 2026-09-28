"""Retail SKU catalog with 13-digit EAN barcodes for simulation and telemetry."""

from typing import Dict, TypedDict


class SkuCatalogEntry(TypedDict):
    ean: str
    name: str


# Standard UK retail-style prefixes (501...) mapped to active mock SKUs.
SIMULATION_SKU_POOL: Dict[str, SkuCatalogEntry] = {
    "BAKED-BEANS-6PK": {
        "ean": "5012345678901",
        "name": "Heinz Baked Beans 6pk",
    },
    "CHOCO-BISCUITS-6PK": {
        "ean": "5012345678918",
        "name": "McVitie's Chocolate Biscuits 6pk",
    },
    "PERONI-12PK": {
        "ean": "5012345678925",
        "name": "Peroni Nastro Azzurro 12pk",
    },
    "MIXED-MANIFEST": {
        "ean": "5012345000012",
        "name": "Mixed Delivery Cage Manifest",
    },
}


def get_sku_profile(sku: str) -> SkuCatalogEntry:
    return SIMULATION_SKU_POOL.get(
        sku,
        {"ean": "5012300000000", "name": sku.replace("-", " ").title()},
    )
